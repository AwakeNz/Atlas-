"""A.T.L.A.S. entry point. Wires config → memory → provider chain → plugins →
agent → HUD, then lazily brings up voice, tray, sys-stats and the updater.

Cold-start discipline: only stdlib is imported before the UI is created; the
provider chain, requests, voice engines and model downloads all load lazily
after the window shows, so cold start stays under 2 s.
"""
from __future__ import annotations

import sys
import threading

from core.bus import EventBus
from core.config import Config, __version__, ensure_user_files
from core.log import get_logger


class LazyChain:
    """Defers building the provider chain (and importing requests) until the
    first model call. A missing key becomes a friendly runtime notice, not a
    startup crash, and cold start stays fast."""

    def __init__(self, config, bus):
        self._config = config
        self._bus = bus
        self._real = None
        self._lock = threading.Lock()

    def _chain(self):
        with self._lock:
            if self._real is None:
                from core.llm import ProviderChain, build_providers
                self._real = ProviderChain(build_providers(self._config), self._bus)
            return self._real

    def reset(self):
        if self._real is not None:
            self._real.reset()

    def current_name(self):
        return self._real.current_name() if self._real else "—"

    def chat(self, messages, tools=None, stream_cb=None, small=False):
        return self._chain().chat(messages, tools, stream_cb, small)

    def transcribe(self, wav_bytes):
        return self._chain().transcribe(wav_bytes)


def main() -> int:
    config = Config()
    ensure_user_files()
    log = get_logger()
    log.info("=== A.T.L.A.S. v%s starting (frozen=%s) ===", __version__,
             getattr(sys, "frozen", False))

    bus = EventBus()
    llm = LazyChain(config, bus)

    from core.memory import SQLiteMemoryStore
    memory = SQLiteMemoryStore()

    from core.plugins import PluginContext, PluginRegistry
    ctx = PluginContext(memory=memory, config=config, llm=llm,
                        confirm=bus.confirm, notify=bus.notify)
    registry = PluginRegistry(ctx)

    from core.skills import SkillsIndex, builtin_tools
    skills = SkillsIndex()
    for tool in builtin_tools(skills):
        registry.register_builtin(tool)
    registry.load_all()

    from core.agent import Agent
    agent = Agent(llm, registry, memory, config, bus, skills=skills)

    # -- choose UI: pywebview FUI (primary) with tkinter fallback --
    hud = _make_hud(config, bus, agent, log)

    from voice.tts import Speaker
    speaker = Speaker(bus, voice=config.get("tts_voice", "en-GB-RyanNeural"),
                      enabled=bool(config.get("voice_enabled", True)))
    hud.set_speaker(speaker.speak)

    # -- voice: wake word (hands-free) + push-to-talk fallback --
    wake = _bring_up_voice(config, bus, agent, log)

    # -- tray with mic-mute + update controls --
    from core.updater import check_async, install
    controls = {
        "check_updates": lambda: check_async(config, bus, notify_only=True),
        "install_update": lambda: install(config, bus),
    }
    if wake is not None:
        controls["mic_toggle"] = wake.toggle_mute
        controls["is_muted"] = lambda: wake._muted.is_set()
    if hasattr(hud, "wire"):
        hud.wire(mic_toggle=controls.get("mic_toggle"),
                 check_updates=controls["check_updates"],
                 install_update=controls["install_update"])

    from ui.tray import start_tray
    start_tray(bus, skills, controls)

    # -- global hotkey (post-UI, non-fatal) --
    threading.Thread(target=_wire_hotkey, args=(config, bus, agent, llm, log),
                     name="hooks", daemon=True).start()

    # -- background: sys-stat readout, model downloads, update check --
    from core.sysstat import start_reporter
    start_reporter(bus, llm, agent)

    from core import models
    models.ensure_voice_models_async(config, bus)
    check_async(config, bus)

    if not _has_any_key(config):
        bus.notify("No API key set. Add one to settings.json → providers "
                   "(free keys: aistudio.google.com, console.groq.com).")

    hud.run()
    if wake is not None:
        wake.stop()
    memory.close()
    log.info("=== A.T.L.A.S. shut down ===")
    return 0


def _make_hud(config, bus, agent, log):
    ptt = config.get("push_to_talk_key", "f8").upper()
    if config.get("ui", "webview") == "webview":
        try:
            import webview  # noqa: F401 — probe availability before committing
            from ui.webview_hud import WebHud
            log.info("UI: pywebview FUI")
            return WebHud(bus, on_submit=agent.submit, on_ptt_hint=ptt)
        except Exception as e:                # noqa: BLE001
            log.warning("pywebview unavailable (%s) — falling back to tkinter", e)
    from ui.hud import Hud
    log.info("UI: tkinter fallback")
    return Hud(bus, on_submit=agent.submit, on_ptt_hint=ptt)


def _bring_up_voice(config, bus, agent, log):
    if not (config.get("voice_enabled", True) and config.get("wake_word_enabled", True)):
        return None
    try:
        from voice.wake import WakeWord
        wake = WakeWord(config, bus, on_text=agent.submit)
        wake.start()
        return wake
    except Exception as e:                    # noqa: BLE001
        log.warning("wake word unavailable: %s", e)
        return None


def _wire_hotkey(config, bus, agent, llm, log):
    try:
        import keyboard
        keyboard.add_hotkey(config.get("hotkey", "ctrl+space"), bus.toggle)
        if config.get("voice_enabled", True):
            from voice.stt import PushToTalk
            ptt = PushToTalk(llm, bus, on_text=agent.submit,
                             key=config.get("push_to_talk_key", "f8"))
            ptt.attach(keyboard)
        log.info("hotkeys armed: %s / PTT %s", config.get("hotkey"),
                 config.get("push_to_talk_key"))
    except Exception as e:                    # noqa: BLE001
        log.error("hotkey setup failed: %s", e)
        bus.notify(f"Global hotkey unavailable ({e}). The window still works.")


def _has_any_key(config) -> bool:
    return any(p.get("api_key") for p in config.get("providers", []) or [])


if __name__ == "__main__":
    sys.exit(main())
