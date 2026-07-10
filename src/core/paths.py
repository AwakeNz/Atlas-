"""Single source of truth for every filesystem location A.T.L.A.S. touches.

The installer puts program files in Program Files (read-only for a standard
user), so ALL user data lives in %APPDATA%\\ATLAS instead of next to the exe:

    program_dir()   ← where ATLAS.exe / the dev checkout lives (read-only)
    bundle_dir()    ← PyInstaller _MEIPASS (bundled plugins/skills/web/wake)
    data_dir()      ← %APPDATA%\\ATLAS  (settings, plugins, skills, memory, models, log)

Everything else in the app imports its paths from here. `migrate_legacy()`
moves data written next to the exe by pre-0.3 builds into data_dir on first run.
"""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

APP_NAME = "ATLAS"

# user-data entries that pre-0.3 builds wrote next to the exe
_MIGRATABLE = ("settings.json", "apps.json", "memory.db", "memory.db-wal",
               "memory.db-shm", "atlas.log", "plugins", "skills", "models")


def is_frozen() -> bool:
    return getattr(sys, "frozen", False)


def program_dir() -> Path:
    """Read-only install location (or the repo root in dev)."""
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


def bundle_dir() -> Path:
    """Read-only resources bundled inside the exe."""
    if is_frozen():
        return Path(getattr(sys, "_MEIPASS", program_dir()))
    return program_dir()


def data_dir() -> Path:
    """Writable per-user data root, created on demand."""
    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or (Path.home() / "AppData" / "Roaming")
    else:  # dev boxes: respect XDG, keep it out of the repo
        base = os.environ.get("XDG_DATA_HOME") or (Path.home() / ".local" / "share")
    d = Path(base) / APP_NAME
    d.mkdir(parents=True, exist_ok=True)
    return d


# -- concrete file/dir helpers (use these everywhere) --

def settings_path() -> Path: return data_dir() / "settings.json"
def apps_path() -> Path:     return data_dir() / "apps.json"
def memory_db() -> Path:     return data_dir() / "memory.db"
def log_path() -> Path:      return data_dir() / "atlas.log"
def plugins_dir() -> Path:   return data_dir() / "plugins"
def skills_dir() -> Path:    return data_dir() / "skills"


def models_dir() -> Path:
    d = data_dir() / "models"
    d.mkdir(parents=True, exist_ok=True)
    return d


def assets_dir() -> Path:
    """Bundled read-only assets (the app icon)."""
    return bundle_dir() / "assets"


def icon_path() -> Path | None:
    p = assets_dir() / "atlas.ico"
    return p if p.exists() else None


def migrate_legacy() -> None:
    """Move data a pre-0.3 build left beside the exe into data_dir. Only runs
    for an installed (frozen) exe; a dev checkout keeps its repo files intact.
    Never overwrites data that already exists in data_dir."""
    if not is_frozen():
        return
    src_root = program_dir()
    dst_root = data_dir()
    for name in _MIGRATABLE:
        src, dst = src_root / name, dst_root / name
        if src.exists() and not dst.exists():
            try:
                shutil.move(str(src), str(dst))
            except OSError:
                pass  # a locked/again-in-use legacy file must not block startup
