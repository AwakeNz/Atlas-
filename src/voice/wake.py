"""Hands-free wake word: "atlas" / "hey atlas".

Pipeline (all local, all CPU):
  continuous 16 kHz mic  →  openWakeWord (ONNX) scores each 80 ms frame
  score > sensitivity    →  soft chime, orb → listening
  record (RMS energy gate)→ stop after 1.2 s of trailing silence (cap 15 s)
  faster-whisper         →  text  →  agent.submit()

CPU discipline: the sounddevice callback only enqueues raw frames; all ONNX
inference happens on one worker thread that blocks on the queue, so idle cost
is ~the melspectrogram+embedding pass every 80 ms (well under 3%).

Mute genuinely stops capture: the input stream is closed, not just ignored.
"""
from __future__ import annotations

import collections
import queue
import sys
import threading
import time

from core.log import get_logger

log = get_logger("atlas.wake")

RATE = 16000
FRAME_MS = 80
FRAME = RATE * FRAME_MS // 1000          # 1280 samples (openWakeWord frame)
VAD_FRAME_MS = 30
VAD_FRAME = RATE * VAD_FRAME_MS // 1000  # 480 samples
SILENCE_HANG_S = 1.2
MAX_UTTERANCE_S = 15


class WakeWord:
    def __init__(self, config, bus, on_text):
        self.config = config
        self.bus = bus
        self.on_text = on_text
        self._muted = threading.Event()
        self._stop = threading.Event()
        self._frames: queue.Queue = queue.Queue(maxsize=64)
        self._stream = None
        self._oww = None
        self._thread = None
        self._phrase = "atlas"

    # -- lifecycle --

    def start(self) -> None:
        if sys.platform != "win32":
            log.info("wake word: non-Windows dev box — not starting live capture")
        self._thread = threading.Thread(target=self._run, name="wake", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._close_stream()

    # -- mute (tray toggle) --

    def set_muted(self, muted: bool) -> None:
        if muted:
            self._muted.set()
            self._close_stream()             # actually stop capturing
        else:
            self._muted.clear()
            self._open_stream()
        self.bus.mic(muted)
        log.info("microphone %s", "muted" if muted else "live")

    def toggle_mute(self) -> bool:
        muted = not self._muted.is_set()
        self.set_muted(muted)
        return muted

    # -- audio stream --

    def _open_stream(self) -> None:
        if self._stream is not None or self._muted.is_set() or self._stop.is_set():
            return
        try:
            import sounddevice as sd
        except Exception as e:                # noqa: BLE001
            log.warning("wake: sounddevice unavailable: %s", e)
            return

        def cb(indata, frames, t, status):
            if self._muted.is_set():
                return
            try:
                self._frames.put_nowait(bytes(indata))
            except queue.Full:
                pass                          # drop under load; never block audio

        try:
            self._stream = sd.RawInputStream(samplerate=RATE, channels=1,
                                             dtype="int16", blocksize=FRAME,
                                             callback=cb)
            self._stream.start()
        except Exception as e:                # noqa: BLE001
            self._stream = None
            log.warning("wake: cannot open mic: %s", e)

    def _close_stream(self) -> None:
        stream, self._stream = self._stream, None
        if stream is not None:
            try:
                stream.stop(); stream.close()
            except Exception:                 # noqa: BLE001
                pass
        # flush queued frames so a resumed stream starts clean
        try:
            while True:
                self._frames.get_nowait()
        except queue.Empty:
            pass

    # -- detection loop --

    def _load_oww(self):
        from core.paths import models_dir
        import openwakeword
        from openwakeword.model import Model

        oww_dir = models_dir()
        atlas = oww_dir / "atlas.onnx"
        kwargs = {"inference_framework": "onnx",
                  "melspec_model_path": str(oww_dir / "melspectrogram.onnx"),
                  "embedding_model_path": str(oww_dir / "embedding_model.onnx")}
        if atlas.exists():
            kwargs["wakeword_models"] = [str(atlas)]
            self._phrase = "atlas"
        else:
            # graceful fallback: use a bundled openWakeWord pretrained phrase so
            # hands-free still works before a custom atlas.onnx is trained.
            log.warning("atlas.onnx missing — falling back to 'hey_jarvis' phrase")
            try:
                openwakeword.utils.download_models(["hey_jarvis"])
            except Exception:                 # noqa: BLE001
                pass
            kwargs["wakeword_models"] = ["hey_jarvis"]
            self._phrase = "hey jarvis"
        return Model(**kwargs)

    def _run(self) -> None:
        if not self.config.get("wake_word_enabled", True):
            return
        self._phrase = "atlas"
        # wait for model files (downloaded post-boot) before starting inference
        from core.paths import models_dir
        needed = ["melspectrogram.onnx", "embedding_model.onnx"]
        for _ in range(600):                  # up to ~5 min for first-run download
            if self._stop.is_set():
                return
            if all((models_dir() / n).exists() for n in needed):
                break
            time.sleep(0.5)
        if not all((models_dir() / n).exists() for n in needed):
            self.bus.notify("Voice models didn't download — hands-free is off. "
                            "Push-to-talk and text still work.")
            log.warning("wake models missing after wait — voice disabled")
            return
        try:
            self._oww = self._load_oww()
        except Exception as e:                # noqa: BLE001
            log.warning("wake word disabled (load failed): %s", e)
            self.bus.notify(f"Voice unavailable ({e}). See atlas.log.")
            return

        self._open_stream()
        sens = float(self.config.get("wake_sensitivity", 0.5))
        threshold = 0.5 + (0.5 - sens) * 0.6  # higher sensitivity → lower threshold
        log.info("wake word armed (threshold %.2f, phrase '%s')", threshold, self._phrase)
        if self._stream is not None:
            self.bus.notify(f"Voice ready — say “{self._phrase}”.")
        else:
            self.bus.notify("Voice loaded but no microphone was opened. "
                            "Check Windows mic permissions.")

        while not self._stop.is_set():
            try:
                frame = self._frames.get(timeout=0.5)
            except queue.Empty:
                if self._stream is None and not self._muted.is_set():
                    self._open_stream()       # try to recover a dropped stream
                continue
            import numpy as np
            samples = np.frombuffer(frame, dtype=np.int16)
            try:
                scores = self._oww.predict(samples)
            except Exception as e:            # noqa: BLE001
                log.debug("predict error: %s", e)
                continue
            if any(s >= threshold for s in scores.values()):
                self._oww.reset()
                self._on_wake()

    # -- capture the command after a wake trigger --

    def _on_wake(self) -> None:
        log.info("wake word detected")
        self._chime()
        self.bus.state("listening")
        pcm = self._record_until_silence()
        if not pcm:
            self.bus.state("idle")
            return
        self.bus.state("thinking")
        try:
            from voice.whisper_stt import WhisperSTT
            text = WhisperSTT(self.config.get("whisper_model", "base")).transcribe_pcm(pcm)
        except Exception as e:                # noqa: BLE001
            log.warning("transcription failed: %s", e)
            self.bus.notify(f"Couldn't transcribe that: {e}")
            self.bus.state("idle")
            return
        if text:
            self.bus.notify(f"❯ {text}")
            self.on_text(text)
        else:
            self.bus.state("idle")

    def _record_until_silence(self) -> bytes:
        """Record until ~SILENCE_HANG_S of trailing silence, using a pure-stdlib
        RMS energy gate (audioop). No webrtcvad: it needs a C compiler and its
        PyInstaller hook is fragile, and this is plenty for end-of-utterance
        detection. Falls back to a fixed cap if audioop is somehow unavailable."""
        try:
            import audioop
        except Exception as e:                # noqa: BLE001
            log.warning("audioop unavailable, fixed 4s capture: %s", e)
            audioop = None

        collected = bytearray()
        carry = bytearray()
        silence = 0.0
        voiced_total = 0.0
        noise_floor = 250.0                   # adapts up from ambient level
        started = time.time()
        while time.time() - started < MAX_UTTERANCE_S:
            try:
                frame = self._frames.get(timeout=1.0)
            except queue.Empty:
                break
            collected.extend(frame)
            if audioop is None:
                if time.time() - started > 4:
                    break
                continue
            carry.extend(frame)
            # evaluate in exact 30 ms frames
            while len(carry) >= VAD_FRAME * 2:
                chunk = bytes(carry[:VAD_FRAME * 2])
                del carry[:VAD_FRAME * 2]
                rms = audioop.rms(chunk, 2)   # 0..32767 for 16-bit mono
                # voiced if clearly above the running noise floor
                if rms > max(500.0, noise_floor * 2.2):
                    silence = 0.0
                    voiced_total += VAD_FRAME_MS / 1000
                else:
                    silence += VAD_FRAME_MS / 1000
                    noise_floor = 0.95 * noise_floor + 0.05 * rms   # track ambient
            # only stop once we've heard real speech, then a silence tail
            if voiced_total >= 0.3 and silence >= SILENCE_HANG_S:
                break
        return bytes(collected)

    @staticmethod
    def _chime() -> None:
        if sys.platform == "win32":
            try:
                import winsound
                winsound.Beep(880, 90)
            except Exception:                 # noqa: BLE001
                pass
