"""A.T.L.A.S. entry point. Wires config → memory → LLM → plugins → agent → HUD.

Cold-start discipline: only stdlib + tkinter are imported before the window is
on screen. requests/edge-tts/sounddevice/keyboard all load lazily afterwards.
"""
from __future__ import annotations

import sys
import threading

from core.bus import EventBus
from core.config import Config, __version__, ensure_user_files
from core.log import get_logger


class LazyProvider:
    """Defers building the real provider (and importing requests) until the
    first model call, so a missing API key is a friendly runtime message, not
    a startup crash — and cold start stays sub-2s."""

    def __init__(self, config):
        self._config = config
        self._real = None
        self._lock = threading.Lock()

    def _provider(self):
        with self._lock:
            if self._real is None:
                from core.llm import make_provider
                self._real = make_provider(self._config)
            return self._real

    def chat(self, messages, tools=None, stream_cb=None):
        return self._provider().chat(messages, tools, stream_cb)

    def transcribe(self, wav_bytes):
        return self._provider().transcribe(wav_bytes)


def main() -> int:
    config = Config()
    ensure_user_files()
    log = get_logger()
    log.info("=== A.T.L.A.S. v%s starting (frozen=%s) ===", __version__,
             getattr(sys, "frozen", False))

    bus = EventBus()
    llm = LazyProvider(config)

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

    from ui.hud import Hud
    hud = Hud(bus, on_submit=agent.submit,
              on_ptt_hint=config.get("push_to_talk_key", "f8").upper())

    from voice.tts import Speaker
    speaker = Speaker(bus, voice=config.get("tts_voice", "en-GB-RyanNeural"),
                      enabled=bool(config.get("voice_enabled", True)))
    hud.set_speaker(speaker.speak)

    def wire_input_hooks():
        """Global hotkey + push-to-talk. Runs after the window is up; failure
        (e.g. `keyboard` needs elevation) degrades to a visible message."""
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
        except Exception as e:
            log.error("hotkey setup failed: %s", e)
            bus.notify(f"Global hotkey unavailable ({e}). The window still works.")

    threading.Thread(target=wire_input_hooks, name="hooks", daemon=True).start()

    from ui.tray import start_tray
    start_tray(bus, skills)

    from core import updater
    updater.check_async(config, bus)

    if not config.get("groq_api_key"):
        bus.notify("No API key set. Edit settings.json → groq_api_key "
                   "(free key at console.groq.com), then restart.")

    hud.run()
    memory.close()
    log.info("=== A.T.L.A.S. shut down ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
