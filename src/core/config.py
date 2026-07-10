"""Paths and settings. Everything user-editable lives NEXT TO the exe."""
from __future__ import annotations

import json
import shutil
import sys
import threading
from pathlib import Path

APP_NAME = "A.T.L.A.S."
__version__ = "0.2.0"

_DEFAULT_SETTINGS = {
    # -- LLM provider fallback chain (tried top-to-bottom; 429/quota → next) --
    "providers": [
        {"name": "gemini",   "model": "gemini-2.5-flash",        "api_key": ""},
        {"name": "groq",     "model": "llama-3.3-70b-versatile", "api_key": ""},
        {"name": "cerebras", "model": "",                        "api_key": ""},
    ],
    # token diet: trivial one-shot commands route to the cheap tier per provider
    "small_models": {
        "gemini":   "gemini-2.5-flash-lite",
        "groq":     "llama-3.1-8b-instant",
        "cerebras": "",
    },
    "route_trivial_to_small": True,
    "history_turns": 12,

    # -- UI --
    "ui": "webview",              # "webview" (pywebview FUI) or "tkinter" fallback
    "hotkey": "ctrl+space",
    "push_to_talk_key": "f8",

    # -- voice --
    "voice_enabled": True,
    "wake_word_enabled": True,
    "wake_phrases": ["atlas", "hey atlas"],
    "wake_sensitivity": 0.5,      # 0..1, higher = more eager to trigger
    "whisper_model": "base",      # faster-whisper size (tiny|base|small|...)
    "tts_voice": "en-GB-RyanNeural",
    "stt_cloud_model": "whisper-large-v3",   # fallback STT if local models absent

    # -- agent / tools --
    "max_agent_steps": 8,
    "editor_command": "",
    "allowed_shell_commands": ["dir", "echo", "ipconfig", "ping", "whoami", "tasklist", "systeminfo"],
    "allowed_game_windows": [],
    "discord": {"webhook_url": "", "bot_token": "", "default_channel_id": ""},

    # -- updates --
    "update_repo": "AwakeNz/Atlas-",
    "auto_check_updates": True,
    "update_channel": "stable",
}

_DEFAULT_APPS = {
    "notepad": "notepad.exe",
    "calculator": "calc.exe",
    "explorer": "explorer.exe",
    "paint": "mspaint.exe",
}


def is_frozen() -> bool:
    return getattr(sys, "frozen", False)


def app_dir() -> Path:
    """Directory holding settings.json, plugins/, memory.db, atlas.log, models/."""
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]  # repo atlas/ dir in dev


def bundle_dir() -> Path:
    """Read-only resources bundled inside the exe (default plugins, web assets)."""
    if is_frozen():
        return Path(getattr(sys, "_MEIPASS", app_dir()))
    return app_dir()


def models_dir() -> Path:
    d = app_dir() / "models"
    d.mkdir(parents=True, exist_ok=True)
    return d


class Config:
    """Thread-safe view over settings.json. Reads are cheap dict lookups;
    save() rewrites the file atomically. Legacy single-provider settings are
    migrated into the providers[] chain on load."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self.path = app_dir() / "settings.json"
        self._data: dict = {}
        self.load()

    def load(self) -> None:
        with self._lock:
            data = dict(_DEFAULT_SETTINGS)
            if self.path.exists():
                try:
                    user = json.loads(self.path.read_text(encoding="utf-8"))
                    if isinstance(user, dict):
                        data.update(user)
                except (json.JSONDecodeError, OSError):
                    pass  # corrupted settings must not brick startup
            self._data = _migrate(data)
            if not self.path.exists():
                self.save()

    def save(self) -> None:
        with self._lock:
            tmp = self.path.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(self._data, indent=2), encoding="utf-8")
            tmp.replace(self.path)

    def get(self, key: str, default=None):
        with self._lock:
            return self._data.get(key, default)

    def set(self, key: str, value) -> None:
        with self._lock:
            self._data[key] = value
            self.save()


def _migrate(data: dict) -> dict:
    """Fold a pre-0.2 single-provider config (`provider`/`groq_api_key`/`model`)
    into the providers[] chain so old settings.json files keep working."""
    if data.get("groq_api_key") and isinstance(data.get("providers"), list):
        for p in data["providers"]:
            if p.get("name") == "groq" and not p.get("api_key"):
                p["api_key"] = data["groq_api_key"]
    return data


def ensure_user_files() -> None:
    """First-run self-heal: materialize plugins/, skills/ and apps.json
    beside the exe."""
    root = app_dir()
    apps = root / "apps.json"
    if not apps.exists():
        apps.write_text(json.dumps(_DEFAULT_APPS, indent=2), encoding="utf-8")

    for folder in ("plugins", "skills"):
        dst = root / folder
        if not dst.exists():
            src = bundle_dir() / folder
            if src.is_dir() and src != dst:
                shutil.copytree(src, dst)
            else:
                dst.mkdir(parents=True, exist_ok=True)
