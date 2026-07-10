"""Push-to-talk speech-to-text. Hold the PTT key → record mic → release →
WAV goes to the provider's transcribe() (Groq whisper-large-v3).

Voice is strictly optional: if sounddevice or the mic is missing, we log it,
tell the HUD once, and text input carries on unaffected.
"""
from __future__ import annotations

import io
import threading
import wave

from core.log import get_logger

log = get_logger("atlas.stt")

RATE = 16000


class PushToTalk:
    def __init__(self, llm, bus, on_text, key: str = "f8"):
        self.llm = llm
        self.bus = bus
        self.on_text = on_text
        self.key = key
        self._frames: list[bytes] = []
        self._stream = None
        self._lock = threading.Lock()
        self._warned = False

    def attach(self, keyboard_module) -> None:
        keyboard_module.on_press_key(self.key, lambda e: self._start(), suppress=False)
        keyboard_module.on_release_key(self.key, lambda e: self._stop(), suppress=False)

    def _start(self) -> None:
        with self._lock:
            if self._stream is not None:
                return
            try:
                import sounddevice as sd  # lazy: keeps cold start fast
            except Exception as e:
                self._warn(f"Voice input unavailable ({e}). Text still works.")
                return
            self._frames = []

            def cb(indata, frames, time_info, status):
                self._frames.append(bytes(indata))

            try:
                self._stream = sd.RawInputStream(samplerate=RATE, channels=1,
                                                 dtype="int16", callback=cb)
                self._stream.start()
                self.bus.state("listening")
            except Exception as e:
                self._stream = None
                self._warn(f"Microphone error: {e}")

    def _stop(self) -> None:
        with self._lock:
            stream, self._stream = self._stream, None
            frames, self._frames = self._frames, []
        if stream is None:
            return
        try:
            stream.stop()
            stream.close()
        except Exception:
            pass
        self.bus.state("thinking")
        if sum(len(f) for f in frames) < RATE // 2:  # <0.25 s: ignore key taps
            self.bus.state("idle")
            return
        threading.Thread(target=self._transcribe, args=(b"".join(frames),),
                         name="stt", daemon=True).start()

    def _transcribe(self, pcm: bytes) -> None:
        buf = io.BytesIO()
        with wave.open(buf, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(RATE)
            w.writeframes(pcm)
        try:
            text = self.llm.transcribe(buf.getvalue())
        except Exception as e:
            log.warning("transcription failed: %s", e)
            self.bus.notify(f"Couldn't transcribe that: {e}")
            self.bus.state("idle")
            return
        if text:
            self.bus.notify(f"❯ {text}")
            self.on_text(text)
        else:
            self.bus.state("idle")

    def _warn(self, msg: str) -> None:
        log.warning(msg)
        if not self._warned:
            self._warned = True
            self.bus.notify(msg)
