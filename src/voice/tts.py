"""Text-to-speech via edge-tts (calm British male by default: en-GB-RyanNeural).

edge-tts is async and network-backed; we run it on a daemon thread and play
the resulting mp3 with winmm (ctypes) — zero extra dependencies. A new
utterance cancels the previous one. Any failure degrades to text-only.
"""
from __future__ import annotations

import ctypes
import re
import sys
import tempfile
import threading
from pathlib import Path

from core.log import get_logger

log = get_logger("atlas.tts")

_MD_NOISE = re.compile(r"[*_`#>\[\]]|\(https?://\S+\)")


class Speaker:
    def __init__(self, bus, voice: str = "en-GB-RyanNeural", enabled: bool = True):
        self.bus = bus
        self.voice = voice
        self.enabled = enabled and sys.platform == "win32"
        self._gen = 0                       # generation counter cancels stale audio
        self._lock = threading.Lock()

    def speak(self, text: str) -> None:
        if not self.enabled or not text.strip():
            return
        with self._lock:
            self._gen += 1
            gen = self._gen
        self._mci("close atlas_tts")       # cut off whatever was talking
        clean = _MD_NOISE.sub("", text)[:1200]
        threading.Thread(target=self._speak, args=(clean, gen),
                         name="tts", daemon=True).start()

    def _speak(self, text: str, gen: int) -> None:
        try:
            import asyncio
            import edge_tts  # lazy import: shaves ~200ms off cold start

            path = Path(tempfile.gettempdir()) / "atlas_tts.mp3"

            async def synth():
                await edge_tts.Communicate(text, self.voice).save(str(path))

            asyncio.run(synth())
            if gen != self._gen:
                return                       # superseded while synthesizing
            self.bus.state("speaking")
            self._mci(f'open "{path}" type mpegvideo alias atlas_tts')
            self._mci("play atlas_tts wait")
            self._mci("close atlas_tts")
        except Exception as e:
            log.warning("TTS failed (text-only mode continues): %s", e)
        finally:
            if gen == self._gen:
                self.bus.state("idle")

    @staticmethod
    def _mci(cmd: str) -> None:
        if sys.platform == "win32":
            ctypes.windll.winmm.mciSendStringW(cmd, None, 0, None)
