"""Paths and settings. Everything user-editable lives NEXT TO the exe."""
from __future__ import annotations

import json
import shutil
import sys
import threading
from pathlib import Path

APP_NAME = "A.T.L.A.S."
__version__ = "0.1.0"

_DEFAULT_SETTINGS = {
    "provider": "groq",
    "groq_api_key": "",
    "model": "llama-3.3-70b-versatile",
    "stt_model": "whisper-large-v3",
    "tts_voice": "en-GB-RyanNeural",
    "voice_enabled": True,
    "hotkey": "ctrl+space",
    "push_to_talk_key": "f8",
    "max_agent_steps": 8,
    "editor_command": "",
    "allowed_shell_commands": ["dir", "echo", "ipconfig", "ping", "whoami", "tasklist", "systeminfo"],
    "allowed_game_windows": [],
    "discord": {"webhook_url": "", "bot_token": "", "default_channel_id": ""},
    "update_repo": "AwakeNz/Atlas-",
    "check_updates": True,
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
    """Directory holding settings.json, plugins/, memory.db, atlas.log."""
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]  # repo atlas/ dir in dev


def bundle_dir() -> Path:
    """Read-only resources bundled inside the exe (default plugins)."""
    if is_frozen():
        return Path(getattr(sys, "_MEIPASS", app_dir()))
    return app_dir()


class Config:
    """Thread-safe view over settings.json. Reads are cheap dict lookups;
    save() rewrites the file atomically."""

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
                    data.update(json.loads(self.path.read_text(encoding="utf-8")))
                except (json.JSONDecodeError, OSError):
                    pass  # corrupted settings must not brick startup
            self._data = data
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
