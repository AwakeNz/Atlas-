"""LLM provider abstraction + fallback chain.

All three supported providers speak the OpenAI wire format, so one generic
`OpenAICompatProvider` (raw HTTPS via requests, no vendor SDK) covers Gemini,
Groq and Cerebras — only base URL, key and model differ. `ProviderChain` tries
them in order and falls to the next on quota/429, emitting a HUD notice.

Endpoints:
  gemini   → https://generativelanguage.googleapis.com/v1beta/openai/
  groq     → https://api.groq.com/openai/v1
  cerebras → https://api.cerebras.ai/v1   (model list queried live at startup)
"""
from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Callable, Optional

import requests

from .log import get_logger

log = get_logger("atlas.llm")

StreamCB = Optional[Callable[[str], None]]

_ENDPOINTS = {
    "gemini":   "https://generativelanguage.googleapis.com/v1beta/openai",
    "groq":     "https://api.groq.com/openai/v1",
    "cerebras": "https://api.cerebras.ai/v1",
}


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict


@dataclass
class ChatResult:
    content: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    prompt_tokens: int = 0
    completion_tokens: int = 0


class LLMError(RuntimeError):
    pass


class QuotaError(LLMError):
    """Rate limit / quota exhausted — the chain should fall to the next
    provider rather than surface this to the user."""


class LLMProvider(ABC):
    @abstractmethod
    def chat(self, messages: list[dict], tools: list[dict] | None = None,
             stream_cb: StreamCB = None, small: bool = False) -> ChatResult: ...

    def transcribe(self, wav_bytes: bytes) -> str:
        raise NotImplementedError("This provider has no STT.")


def _read_sse(resp, stream_cb) -> ChatResult:
    """Parse an OpenAI-style streaming chat completion. Tool-call deltas arrive
    fragmented and keyed by index; reassemble them."""
    result = ChatResult()
    pending: dict[int, dict] = {}
    for raw in resp.iter_lines(decode_unicode=True):
        if not raw or not raw.startswith("data:"):
            continue
        data = raw[5:].strip()
        if data == "[DONE]":
            break
        try:
            obj = json.loads(data)
        except json.JSONDecodeError:
            continue
        usage = obj.get("usage")
        if usage:
            result.prompt_tokens = usage.get("prompt_tokens", result.prompt_tokens)
            result.completion_tokens = usage.get("completion_tokens",
                                                 result.completion_tokens)
        try:
            delta = obj["choices"][0]["delta"]
        except (KeyError, IndexError):
            continue
        piece = delta.get("content")
        if piece:
            result.content += piece
            if stream_cb:
                stream_cb(piece)
        for tc in delta.get("tool_calls") or []:
            slot = pending.setdefault(tc.get("index", 0),
                                      {"id": "", "name": "", "args": ""})
            if tc.get("id"):
                slot["id"] = tc["id"]
            fn = tc.get("function") or {}
            if fn.get("name"):
                slot["name"] += fn["name"]
            if fn.get("arguments"):
                slot["args"] += fn["arguments"]
    for i in sorted(pending):
        slot = pending[i]
        try:
            args = json.loads(slot["args"]) if slot["args"] else {}
            if not isinstance(args, dict):
                raise ValueError("arguments not an object")
        except (json.JSONDecodeError, ValueError):
            log.warning("dropping malformed tool args for %s", slot["name"])
            args = {"__malformed__": slot["args"][:500]}
        result.tool_calls.append(ToolCall(slot["id"] or f"call_{i}",
                                          slot["name"], args))
    return result


class OpenAICompatProvider(LLMProvider):
    def __init__(self, name: str, base_url: str, api_key: str, model: str,
                 small_model: str = ""):
        self.name = name
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.small_model = small_model or model
        self._session = requests.Session()
        self._session.headers["Authorization"] = f"Bearer {api_key}"

    def chat(self, messages, tools=None, stream_cb=None, small=False) -> ChatResult:
        model = self.small_model if small else self.model
        payload: dict = {"model": model, "messages": messages, "stream": True,
                         "temperature": 0.4, "stream_options": {"include_usage": True}}
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"
        try:
            resp = self._session.post(f"{self.base_url}/chat/completions",
                                      json=payload, stream=True, timeout=(10, 120))
        except requests.RequestException as e:
            # network failures are treated as retryable → next provider
            raise QuotaError(f"{self.name} network error: {e}") from e
        if resp.status_code == 429:
            raise QuotaError(f"{self.name} rate-limited (HTTP 429)")
        if resp.status_code in (402, 403) and _is_quota(resp.text):
            raise QuotaError(f"{self.name} quota exhausted (HTTP {resp.status_code})")
        if resp.status_code >= 500:
            raise QuotaError(f"{self.name} server error (HTTP {resp.status_code})")
        if resp.status_code != 200:
            # a real, non-retryable error (bad key, bad request) — do NOT
            # silently fall through the whole chain on it
            raise LLMError(f"{self.name} HTTP {resp.status_code}: {resp.text[:300]}")
        return _read_sse(resp, stream_cb)

    def transcribe(self, wav_bytes: bytes) -> str:
        resp = self._session.post(
            f"{self.base_url}/audio/transcriptions",
            files={"file": ("speech.wav", wav_bytes, "audio/wav")},
            data={"model": "whisper-large-v3", "response_format": "text"},
            timeout=(10, 60))
        if resp.status_code != 200:
            raise LLMError(f"{self.name} STT HTTP {resp.status_code}")
        return resp.text.strip()


def _is_quota(text: str) -> bool:
    t = (text or "").lower()
    return any(k in t for k in ("quota", "rate limit", "resource_exhausted",
                                "exhausted", "insufficient"))


def _discover_cerebras_model(api_key: str) -> str:
    """Cerebras' free catalog changes; query the live model list and pick the
    first chat-capable one instead of hardcoding a name."""
    try:
        r = requests.get(f"{_ENDPOINTS['cerebras']}/models",
                         headers={"Authorization": f"Bearer {api_key}"}, timeout=10)
        if r.status_code == 200:
            models = [m.get("id", "") for m in r.json().get("data", [])]
            # prefer instruct/chat models; skip embeddings/whisper
            for m in models:
                low = m.lower()
                if m and not any(x in low for x in ("embed", "whisper", "tts")):
                    log.info("cerebras model discovered: %s", m)
                    return m
    except requests.RequestException as e:
        log.info("cerebras model discovery failed: %s", e)
    return "llama3.1-8b"   # reasonable last resort


def build_providers(config) -> list[OpenAICompatProvider]:
    """settings.json providers[] → concrete providers (only those with a key)."""
    smalls = config.get("small_models", {}) or {}
    out: list[OpenAICompatProvider] = []
    for spec in config.get("providers", []) or []:
        name = (spec.get("name") or "").lower()
        key = spec.get("api_key") or ""
        if not name or not key or name not in _ENDPOINTS:
            continue
        model = spec.get("model") or ""
        if name == "cerebras" and not model:
            model = _discover_cerebras_model(key)
        elif not model:
            log.warning("provider %s has no model set — skipped", name)
            continue
        out.append(OpenAICompatProvider(name, _ENDPOINTS[name], key, model,
                                        smalls.get(name, "")))
    return out


class ProviderChain(LLMProvider):
    """Ordered providers with quota fallback. Sticky within one user request
    (so multi-step loops don't re-hit an exhausted provider each step); reset()
    returns to the top of the chain for the next request."""

    def __init__(self, providers: list[OpenAICompatProvider], bus=None):
        if not providers:
            raise LLMError("No usable providers. Add an api_key to at least one "
                           "entry in settings.json → providers.")
        self._providers = providers
        self._bus = bus
        self._idx = 0

    def reset(self) -> None:
        self._idx = 0

    def current_name(self) -> str:
        return self._providers[self._idx].name if self._providers else "—"

    def chat(self, messages, tools=None, stream_cb=None, small=False) -> ChatResult:
        errors = []
        # try each provider once, starting from the sticky index; never loop back
        for offset in range(len(self._providers)):
            idx = (self._idx + offset) % len(self._providers)
            provider = self._providers[idx]
            try:
                result = provider.chat(messages, tools, stream_cb, small)
                if idx != self._idx:                       # we moved
                    self._idx = idx
                    if self._bus:
                        self._bus.provider(provider.name)
                        self._bus.notify(f"PROVIDER → {provider.name.upper()}")
                    log.info("switched to provider %s", provider.name)
                return result
            except QuotaError as e:
                log.info("provider %s unavailable: %s", provider.name, e)
                errors.append(str(e))
                continue
            # LLMError (non-quota) propagates immediately — it won't fix itself
            # by trying a different provider (usually a malformed request).
        raise LLMError("All providers exhausted: " + " | ".join(errors))

    def transcribe(self, wav_bytes: bytes) -> str:
        for provider in self._providers:
            try:
                return provider.transcribe(wav_bytes)
            except (LLMError, requests.RequestException):
                continue
        raise LLMError("No provider could transcribe audio.")
