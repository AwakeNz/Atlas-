"""Version check against GitHub releases. Notify-only: we never auto-replace
the running exe (that is how assistants become malware). Runs on a daemon
thread at startup; any failure is silent-but-logged."""
from __future__ import annotations

import threading

from .config import __version__
from .log import get_logger

log = get_logger("atlas.updater")


def _parse(v: str) -> tuple:
    return tuple(int(p) for p in v.strip().lstrip("vV").split(".") if p.isdigit())


def check_async(config, bus) -> None:
    if not config.get("check_updates", True):
        return
    threading.Thread(target=_check, args=(config, bus),
                     name="updater", daemon=True).start()


def _check(config, bus) -> None:
    repo = config.get("update_repo", "")
    if not repo:
        return
    try:
        import requests  # lazy: not needed for cold start
        resp = requests.get(f"https://api.github.com/repos/{repo}/releases/latest",
                            headers={"Accept": "application/vnd.github+json"},
                            timeout=10)
        if resp.status_code != 200:
            log.info("update check: HTTP %s", resp.status_code)
            return
        data = resp.json()
        latest = data.get("tag_name", "")
        if _parse(latest) > _parse(__version__):
            url = data.get("html_url", f"https://github.com/{repo}/releases")
            bus.notify(f"Update available: {latest} (running v{__version__}) — {url}")
            log.info("update available: %s", latest)
        else:
            log.info("up to date (v%s, latest %s)", __version__, latest or "?")
    except Exception as e:
        log.info("update check failed: %s", e)
