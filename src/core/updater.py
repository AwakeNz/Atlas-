"""GitHub release update checker + verified one-click install.

Flow:
  check  → GET /repos/<repo>/releases/latest, compare semver, reject downgrades
  install→ download ATLAS.exe asset (HTTPS only) with progress,
           verify SHA-256 against the published checksum file,
           spawn update.bat which waits for this process to exit, swaps the
           exe, and relaunches. A running exe cannot overwrite itself on
           Windows, hence the detached .bat.

User data (plugins/, skills/, settings.json, memory.db, models/) is never
touched — the swap only replaces the exe. We never install silently.
"""
from __future__ import annotations

import os
import subprocess
import sys
import threading
from pathlib import Path

from .config import __version__, app_dir
from .log import get_logger

log = get_logger("atlas.updater")

ASSET_EXE = "ATLAS.exe"
ASSET_SUM = "ATLAS.exe.sha256"


def _semver(v: str) -> tuple:
    parts = v.strip().lstrip("vV").split("-")[0].split(".")
    return tuple(int(p) if p.isdigit() else 0 for p in (parts + ["0", "0", "0"])[:3])


def check_async(config, bus, notify_only: bool = False) -> None:
    if not config.get("auto_check_updates", True):
        return
    threading.Thread(target=check, args=(config, bus, notify_only),
                     name="updater", daemon=True).start()


def check(config, bus, notify_only: bool = False) -> dict | None:
    """Return release info dict if a newer version exists, else None."""
    repo = config.get("update_repo", "")
    if not repo:
        return None
    try:
        import requests
        r = requests.get(f"https://api.github.com/repos/{repo}/releases/latest",
                         headers={"Accept": "application/vnd.github+json"}, timeout=10)
        if r.status_code != 200:
            log.info("update check: HTTP %s", r.status_code)
            return None
        data = r.json()
        latest = data.get("tag_name", "")
        if _semver(latest) <= _semver(__version__):        # reject same/downgrade
            log.info("up to date (v%s, latest %s)", __version__, latest or "?")
            return None
        url = data.get("html_url", f"https://github.com/{repo}/releases")
        bus.update(latest, url)
        bus.notify(f"UPDATE AVAILABLE — {latest}")
        log.info("update available: %s", latest)
        return data
    except Exception as e:                                 # noqa: BLE001
        log.info("update check failed: %s", e)
        return None


def install(config, bus) -> bool:
    """Download + verify + swap. Returns True if the swap was launched (the app
    should then quit so the .bat can replace the exe)."""
    if not getattr(sys, "frozen", False):
        bus.notify("Updates only apply to the built .exe, not a dev checkout.")
        return False
    data = check(config, bus)
    if not data:
        bus.notify("No newer release to install.")
        return False

    assets = {a.get("name"): a.get("browser_download_url")
              for a in data.get("assets", [])}
    exe_url, sum_url = assets.get(ASSET_EXE), assets.get(ASSET_SUM)
    if not exe_url or not sum_url:
        bus.notify("Release is missing ATLAS.exe or its checksum — aborting.")
        return False
    if not (exe_url.startswith("https://") and sum_url.startswith("https://")):
        bus.notify("Refusing non-HTTPS update URL.")
        return False

    from . import models
    updir = app_dir() / "update"
    updir.mkdir(exist_ok=True)
    new_exe = updir / "ATLAS_new.exe"

    bus.notify("Downloading update…")
    if not models.download(exe_url, new_exe,
                           progress_cb=lambda p: bus.progress("DOWNLOADING UPDATE", p)):
        bus.notify("Update download failed.")
        return False

    # fetch + parse the checksum ("<sha256>  ATLAS.exe")
    try:
        import requests
        want = requests.get(sum_url, timeout=15).text.strip().split()[0].lower()
    except Exception as e:                                 # noqa: BLE001
        bus.notify(f"Couldn't fetch checksum: {e}")
        return False
    got = models.sha256(new_exe).lower()
    if got != want:
        log.error("checksum mismatch: want %s got %s", want, got)
        bus.notify("Checksum mismatch — update rejected.")
        new_exe.unlink(missing_ok=True)
        return False
    log.info("update verified (sha256 ok)")

    _spawn_swap(new_exe)
    bus.notify("Update verified. Restarting to apply…")
    bus.quit()
    return True


def _spawn_swap(new_exe: Path) -> None:
    """Write and launch a detached update.bat that waits for this exe to exit,
    swaps it, and relaunches. Handles the 'exe still locked' case with retries."""
    cur = Path(sys.executable).resolve()
    bat = app_dir() / "update.bat"
    pid = os.getpid()
    bat.write_text(f"""@echo off
setlocal
rem A.T.L.A.S. self-update swap. Waits for the old process to exit before
rem replacing the locked exe, then relaunches.
echo Applying A.T.L.A.S. update...
:waitloop
tasklist /FI "PID eq {pid}" 2>NUL | find "{pid}" >NUL
if not errorlevel 1 (
    timeout /t 1 /nobreak >NUL
    goto waitloop
)
set /a tries=0
:swap
copy /Y "{new_exe}" "{cur}" >NUL
if errorlevel 1 (
    set /a tries+=1
    if %tries% GEQ 15 (
        echo Update failed: "{cur}" is still locked after 15 tries.
        goto done
    )
    timeout /t 1 /nobreak >NUL
    goto swap
)
del /Q "{new_exe}" >NUL 2>&1
start "" "{cur}"
:done
del "%~f0"
""", encoding="utf-8")
    subprocess.Popen(["cmd", "/c", str(bat)], shell=False,
                     creationflags=getattr(subprocess, "DETACHED_PROCESS", 0)
                     | getattr(subprocess, "CREATE_NO_WINDOW", 0))
    log.info("update.bat spawned for pid %s", pid)
