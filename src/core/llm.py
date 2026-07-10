"""LLM provider abstraction. Groq today; Gemini/Ollama are one subclass away.

Raw HTTPS via `requests` (no vendor SDK) keeps the dependency budget flat and
makes the OpenAI-compatible wire format explicit.
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


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict


@dataclass
class ChatResult:
    content: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)


class LLMError(RuntimeError):
    pass


class LLMProvider(ABC):
    """Contract the agent loop programs against. Nothing outside this module
    may assume Groq."""

    @abstractmethod
    def chat(self, messages: list[dict], tools: list[dict] | None = None,
             stream_cb: StreamCB = None) -> ChatResult: ...

    def transcribe(self, wav_bytes: bytes) -> str:
        raise NotImplementedError("This provider has no STT.")


class GroqProvider(LLMProvider):
    BASE = "https://api.groq.com/openai/v1"

    def __init__(self, api_key: str, model: str, stt_model: str = "whisper-large-v3"):
        if not api_key:
            raise LLMError("No Groq API key. Put one in settings.json → groq_api_key "
                           "(free at console.groq.com).")
        self.model = model
        self.stt_model = stt_model
        self._session = requests.Session()
        self._session.headers["Authorization"] = f"Bearer {api_key}"

    def chat(self, messages, tools=None, stream_cb=None) -> ChatResult:
        payload: dict = {"model": self.model, "messages": messages, "stream": True,
                         "temperature": 0.4}
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"
        try:
            resp = self._session.post(f"{self.BASE}/chat/completions",
                                      json=payload, stream=True, timeout=(10, 120))
        except requests.RequestException as e:
            raise LLMError(f"Network error talking to Groq: {e}") from e
        if resp.status_code != 200:
            raise LLMError(f"Groq HTTP {resp.status_code}: {resp.text[:300]}")
        return self._read_sse(resp, stream_cb)

    def _read_sse(self, resp, stream_cb) -> ChatResult:
        result = ChatResult()
        # tool-call deltas arrive fragmented, keyed by index
        pending: dict[int, dict] = {}
        for raw in resp.iter_lines(decode_unicode=True):
            if not raw or not raw.startswith("data:"):
                continue
            data = raw[5:].strip()
            if data == "[DONE]":
                break
            try:
                delta = json.loads(data)["choices"][0]["delta"]
            except (json.JSONDecodeError, KeyError, IndexError):
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
                log.warning("dropping malformed tool args for %s: %r",
                            slot["name"], slot["args"][:200])
                args = {"__malformed__": slot["args"][:500]}
            result.tool_calls.append(ToolCall(slot["id"] or f"call_{i}",
                                              slot["name"], args))
        return result

    def transcribe(self, wav_bytes: bytes) -> str:
        try:
            resp = self._session.post(
                f"{self.BASE}/audio/transcriptions",
                files={"file": ("speech.wav", wav_bytes, "audio/wav")},
                data={"model": self.stt_model, "response_format": "text"},
                timeout=(10, 60),
            )
        except requests.RequestException as e:
            raise LLMError(f"STT network error: {e}") from e
        if resp.status_code != 200:
            raise LLMError(f"STT HTTP {resp.status_code}: {resp.text[:200]}")
        return resp.text.strip()


def make_provider(config) -> LLMProvider:
    """Factory — the only place that maps settings.json → a concrete provider."""
    name = (config.get("provider") or "groq").lower()
    if name == "groq":
        return GroqProvider(config.get("groq_api_key", ""),
                            config.get("model", "llama-3.3-70b-versatile"),
                            config.get("stt_model", "whisper-large-v3"))
    raise LLMError(f"Unknown provider '{name}'. Available: groq")
