"""Local speech-to-text via faster-whisper (CTranslate2, CPU int8).

Fully offline after the model downloads on first run. Lazy: the model is only
constructed when first needed, and cached in models/whisper.
"""
from __future__ import annotations

import threading

import numpy as np

from core.config import models_dir
from core.log import get_logger

log = get_logger("atlas.whisper")


class WhisperSTT:
    _instances: dict[str, "WhisperSTT"] = {}
    _lock = threading.Lock()

    def __new__(cls, size: str = "base"):
        # one shared model per size — it is thread-safe for sequential calls
        with cls._lock:
            inst = cls._instances.get(size)
            if inst is None:
                inst = super().__new__(cls)
                inst.size = size
                inst._model = None
                inst._mlock = threading.Lock()
                cls._instances[size] = inst
            return inst

    def ensure_loaded(self, bus=None):
        with self._mlock:
            if self._model is not None:
                return self._model
            if bus:
                bus.progress("LOADING SPEECH RECOGNITION", 50.0)
            from faster_whisper import WhisperModel
            self._model = WhisperModel(
                self.size, device="cpu", compute_type="int8",
                download_root=str(models_dir() / "whisper"))
            log.info("faster-whisper '%s' loaded", self.size)
            if bus:
                bus.progress("SPEECH RECOGNITION READY", 100.0)
            return self._model

    def transcribe_pcm(self, pcm16: bytes, rate: int = 16000) -> str:
        """Transcribe 16-bit mono PCM."""
        model = self.ensure_loaded()
        audio = np.frombuffer(pcm16, dtype=np.int16).astype(np.float32) / 32768.0
        segments, _ = model.transcribe(audio, language="en", beam_size=1,
                                       vad_filter=False)
        return " ".join(s.text for s in segments).strip()
