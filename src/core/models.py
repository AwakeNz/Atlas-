"""First-run model bootstrap for the local voice pipeline.

To keep the .exe small, the wake-word and Whisper models are NOT bundled; they
download once into models/ next to the exe, with a HUD progress bar, and every
run after that is fully offline. Downloads are resumable (HTTP Range), so a
dropped connection continues instead of restarting.

This module only *fetches* files. The wake/whisper engines load them lazily in
voice/. If a download fails, voice is disabled gracefully — text input and the
hotkey keep working.
"""
from __future__ import annotations

import hashlib
import threading
from pathlib import Path

from .config import models_dir
from .log import get_logger

log = get_logger("atlas.models")

# openWakeWord shared feature models (needed by every wake model) + the custom
# "atlas" phrase model. URLs are overridable via settings for private mirrors.
_OWW_BASE = "https://github.com/dscripka/openWakeWord/releases/download/v0.5.1"
_WAKE_ASSETS = {
    "melspectrogram.onnx": f"{_OWW_BASE}/melspectrogram.onnx",
    "embedding_model.onnx": f"{_OWW_BASE}/embedding_model.onnx",
}


def download(url: str, dest: Path, progress_cb=None, chunk: int = 65536) -> bool:
    """Resumable download. Returns True on success. `.part` file holds partial
    bytes; we send a Range header to continue it."""
    import requests

    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_suffix(dest.suffix + ".part")
    have = part.stat().st_size if part.exists() else 0
    headers = {"Range": f"bytes={have}-"} if have else {}
    try:
        with requests.get(url, headers=headers, stream=True, timeout=(10, 60)) as r:
            if r.status_code == 416:                 # already complete
                part.replace(dest)
                return True
            if r.status_code not in (200, 206):
                log.warning("download %s: HTTP %s", url, r.status_code)
                return False
            if r.status_code == 200:                 # server ignored Range
                have = 0
            total = int(r.headers.get("Content-Length", 0)) + have
            mode = "ab" if have and r.status_code == 206 else "wb"
            done = have
            with open(part, mode) as f:
                for block in r.iter_content(chunk):
                    if not block:
                        continue
                    f.write(block)
                    done += len(block)
                    if progress_cb and total:
                        progress_cb(min(100.0, done * 100.0 / total))
        part.replace(dest)
        return True
    except Exception as e:                            # noqa: BLE001 — never fatal
        log.warning("download failed %s: %s", url, e)
        return False


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def ensure_voice_models_async(config, bus, on_ready=None) -> None:
    """Kick model setup on a daemon thread AFTER the UI is up (cold-start safe)."""
    if not (config.get("voice_enabled", True) and config.get("wake_word_enabled", True)):
        return
    threading.Thread(target=_ensure, args=(config, bus, on_ready),
                     name="models", daemon=True).start()


def _ensure(config, bus, on_ready) -> None:
    root = models_dir()
    ok = True

    # 1) openWakeWord shared feature extractors
    for i, (name, url) in enumerate(_WAKE_ASSETS.items()):
        dest = root / name
        if dest.exists():
            continue
        bus.progress(f"INITIALIZING VOICE SYSTEMS · {name}", 0.0)
        got = download(url, dest,
                       progress_cb=lambda p, n=name: bus.progress(
                           f"INITIALIZING VOICE SYSTEMS · {n}", p))
        ok = ok and got

    # 2) the custom "atlas" wake model — prefer a bundled/overridden copy
    wake_dest = root / "atlas.onnx"
    if not wake_dest.exists():
        bundled = _bundled_wake_model()
        if bundled and bundled.exists():
            wake_dest.write_bytes(bundled.read_bytes())
        else:
            url = config.get("wake_model_url", "")
            if url:
                download(url, wake_dest,
                         progress_cb=lambda p: bus.progress("WAKE MODEL", p))
            else:
                log.info("no atlas.onnx and no wake_model_url — will fall back "
                         "to an openWakeWord pretrained phrase at load time")

    # 3) faster-whisper model — its runtime downloads into models/whisper on
    #    first construction; we surface a coarse status while it warms.
    bus.progress("LOADING SPEECH RECOGNITION", 0.0)
    try:
        from voice.whisper_stt import WhisperSTT
        WhisperSTT(config.get("whisper_model", "base")).ensure_loaded(bus)
    except Exception as e:                            # noqa: BLE001
        log.warning("whisper warmup failed (voice degraded): %s", e)
        ok = False

    bus.progress("VOICE SYSTEMS ONLINE" if ok else "VOICE UNAVAILABLE", 100.0)
    if ok and on_ready:
        on_ready()


def _bundled_wake_model() -> Path | None:
    from .config import bundle_dir
    p = bundle_dir() / "wake" / "atlas.onnx"
    return p if p.exists() else None
