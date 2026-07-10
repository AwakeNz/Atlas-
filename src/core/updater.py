"""GitHub release update checker + verified installer-based upgrade.

v0.3 replaces the old download-exe-and-swap-with-a-.bat mechanism (which failed
during upgrades — see docs/CODE_REVIEW.md §13 for the root cause) with the real
Inno Setup installer:

  check   → GET /repos/<repo>/releases/latest, compare semver, reject downgrades
  install → download ATLAS-Setup-v<new>.exe to %TEMP% (HTTPS only, progress),
            verify SHA-256 against the release's checksum file,
            run it with /SILENT /CLOSEAPPLICATIONS /RESTARTAPPLICATIONS.

Inno owns the close-swap-relaunch and never touches %APPDATA%\\ATLAS, so user
data survives. Nothing installs without explicit user confirmation in the HUD.
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

from .config import __version__
from .log import get_logger

log = get_logger("atlas.updater")


def _semver(v: str) -> tuple:
    parts = v.strip().lstrip("vV").split("-")[0].split(".")
    return tuple(int(p) if p.isdigit() else 0 for p in (parts + ["0", "0", "0"])[:3])


def check_async(config, bus, notify_only: bool = False) -> None:
    if not config.get("auto_check_updates", True):
        return
    threading.Thread(target=check, args=(config, bus, notify_only),
                     name="updater", daemon=True).start()


def check(config, bus, notify_only: bool = False) -> dict | None:
    """Return the release dict if a strictly newer version exists, else None."""
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
        if _semver(latest) <= _semver(__version__):     # same or older → refuse
            log.info("up to date (v%s, latest %s)", __version__, latest or "?")
            if notify_only:
                bus.notify(f"You're on the latest version (v{__version__}).")
            return None
        url = data.get("html_url", f"https://github.com/{repo}/releases")
        bus.update(latest, url)
        bus.notify(f"UPDATE AVAILABLE — {latest}")
        log.info("update available: %s", latest)
        return data
    except Exception as e:                               # noqa: BLE001
        log.info("update check failed: %s", e)
        return None


def _find_setup_asset(data: dict) -> tuple[str, str] | None:
    """Locate the (setup_url, checksum_url) pair in a release's assets. The
    setup is 'ATLAS-Setup-*.exe'; its checksum is that name + '.sha256'."""
    assets = {a.get("name", ""): a.get("browser_download_url", "")
              for a in data.get("assets", [])}
    for name, url in assets.items():
        low = name.lower()
        if low.startswith("atlas-setup") and low.endswith(".exe"):
            checksum = assets.get(name + ".sha256")
            if checksum:
                return url, checksum
    return None


def install(config, bus) -> bool:
    """Download + verify + launch the installer silently. Returns True if the
    installer was launched (the app then quits so Inno can swap it)."""
    if not getattr(sys, "frozen", False):
        bus.notify("Updates only apply to the installed app, not a dev checkout.")
        return False
    data = check(config, bus)
    if not data:
        bus.notify("No newer release to install.")
        return False
    pair = _find_setup_asset(data)
    if not pair:
        bus.notify("Release has no ATLAS-Setup installer + checksum — aborting.")
        return False
    setup_url, sum_url = pair
    if not (setup_url.startswith("https://") and sum_url.startswith("https://")):
        bus.notify("Refusing non-HTTPS update URL.")
        return False

    from . import models
    dest = Path(tempfile.gettempdir()) / Path(setup_url).name

    bus.notify("Downloading update…")
    if not models.download(setup_url, dest,
                           progress_cb=lambda p: bus.progress("DOWNLOADING UPDATE", p)):
        bus.notify("Update download failed.")
        return False

    try:
        import requests
        want = requests.get(sum_url, timeout=15).text.strip().split()[0].lower()
    except Exception as e:                               # noqa: BLE001
        bus.notify(f"Couldn't fetch checksum: {e}")
        return False
    got = models.sha256(dest).lower()
    if got != want:
        log.error("checksum mismatch: want %s got %s", want, got)
        bus.notify("Checksum mismatch — update rejected.")
        try:
            dest.unlink()
        except OSError:
            pass
        return False
    log.info("installer verified (sha256 ok)")

    # Inno silent upgrade: closes the running app, swaps program files,
    # relaunches. /SILENT shows only a progress bar (no wizard); user data in
    # %APPDATA%\ATLAS is never touched.
    try:
        subprocess.Popen(
            [str(dest), "/SILENT", "/CLOSEAPPLICATIONS", "/RESTARTAPPLICATIONS",
             "/NOCANCEL", "/SUPPRESSMSGBOXES"],
            shell=False,
            creationflags=getattr(subprocess, "DETACHED_PROCESS", 0))
    except OSError as e:
        bus.notify(f"Couldn't launch installer: {e}")
        return False
    bus.notify("Update verified. The installer will restart A.T.L.A.S.…")
    bus.quit()
    return True
