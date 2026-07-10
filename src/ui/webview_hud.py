"""pywebview HUD host — the primary UI. Renders the FUI in a frameless,
always-on-top, transparent window (vanilla HTML/CSS/JS, no frameworks).

Thread model mirrors the tkinter HUD: the EventBus is drained on a pump thread
that pushes batched events into JS via `window.evaluate_js`. JS calls back into
Python through the `Api` bridge (pywebview `js_api`). No provider/agent/voice
code ever touches the DOM; it only posts to the bus.
"""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path

from core.config import __version__
from core.log import get_logger

log = get_logger("atlas.webhud")

PUMP_MS = 33


class Api:
    """Exposed to JS as `pywebview.api`. Every method is a thin, safe shim."""

    def __init__(self, bus, on_submit):
        self._bus = bus
        self._on_submit = on_submit
        self.mic_toggle_cb = None
        self.check_updates_cb = None
        self.install_update_cb = None
        self.save_key_cb = None
        self.restart_cb = None
        self.has_key_cb = None
        self._ready = threading.Event()

    def ready(self):
        self._ready.set()
        has_key = bool(self.has_key_cb()) if self.has_key_cb else True
        return {"version": __version__, "has_key": has_key}

    def save_api_key(self, key, provider="gemini"):
        """Persist an API key into settings.json (via the wired callback)."""
        if self.save_key_cb and key and key.strip():
            self.save_key_cb(key.strip(), provider)
            return True
        return False

    def restart_app(self):
        """Relaunch the app so it re-reads settings.json (new API key)."""
        if self.restart_cb:
            self.restart_cb()
        else:
            self._bus.quit()
        return True

    def submit(self, text):
        if text and text.strip():
            self._on_submit(text.strip())
        return True

    def toggle(self):
        self._bus.toggle(); return True

    def confirm(self, req_id, approved):
        self._bus.resolve_confirm(int(req_id), bool(approved)); return True

    def mic_toggle(self):
        return bool(self.mic_toggle_cb()) if self.mic_toggle_cb else False

    def check_updates(self):
        if self.check_updates_cb:
            threading.Thread(target=self.check_updates_cb, daemon=True).start()
        return True

    def install_update(self):
        if self.install_update_cb:
            threading.Thread(target=self.install_update_cb, daemon=True).start()
        return True

    def quit(self):
        self._bus.quit(); return True


class WebHud:
    def __init__(self, bus, on_submit, on_ptt_hint="F8"):
        self.bus = bus
        self.api = Api(bus, on_submit)
        self._on_speak = None
        self._window = None
        self._visible = True
        self._stop = threading.Event()
        self._ptt = on_ptt_hint

    def set_speaker(self, fn):
        self._on_speak = fn

    # tray/main wire these so JS buttons reach the real subsystems
    def wire(self, mic_toggle=None, check_updates=None, install_update=None,
             save_key=None, restart=None, has_key=None):
        self.api.mic_toggle_cb = mic_toggle
        self.api.check_updates_cb = check_updates
        self.api.install_update_cb = install_update
        self.api.save_key_cb = save_key
        self.api.restart_cb = restart
        self.api.has_key_cb = has_key

    def run(self):
        import webview

        html_path = Path(__file__).resolve().parent / "web" / "index.html"
        # easy_drag=False: with easy_drag the ENTIRE window is a drag surface,
        # which swallows clicks/taps (buttons like the confirm modal's ALLOW /
        # DENY never fire, badly so on touch screens). Instead we mark only the
        # eyebrow header draggable via the `pywebview-drag-region` CSS class, so
        # every button and input stays tappable.
        # transparent=False: on Windows/WebView2 a transparent frameless window
        # frequently refuses keyboard focus, so text input silently does nothing.
        # A solid dark window keeps the HUD look while making typing reliable.
        self._window = webview.create_window(
            "A.T.L.A.S.", url=html_path.as_uri(), js_api=self.api,
            width=520, height=680, frameless=True, easy_drag=False,
            on_top=True, transparent=False, background_color="#050308",
            resizable=False)
        webview.start(self._pump, private_mode=False)   # blocks until window closed
        self._stop.set()

    # -- pump: bus → JS --

    def _pump(self):
        # wait until the page has called api.ready() so evaluate_js has a target
        self.api._ready.wait(timeout=10)
        self._push([("boot", "A.T.L.A.S. ONLINE")])
        while not self._stop.is_set():
            events = self.bus.drain()
            if events:
                forward = []
                for kind, payload in events:
                    if kind == "speak":
                        if self._on_speak:
                            self._on_speak(payload)
                        forward.append(("speak", ""))
                    elif kind == "toggle":
                        self._toggle_window()
                    elif kind == "show":
                        self._show_window()
                    elif kind == "quit":
                        self._destroy()
                        return
                    elif kind == "confirm":
                        forward.append(("confirm", {
                            "id": payload.id, "title": payload.title,
                            "detail": payload.detail}))
                    else:
                        forward.append((kind, payload))
                if forward:
                    self._push(forward)
            time.sleep(PUMP_MS / 1000)

    def _push(self, events):
        if not self._window:
            return
        try:
            payload = json.dumps([{"kind": k, "payload": p} for k, p in events])
            self._window.evaluate_js(f"window.atlas && window.atlas.push({payload})")
        except Exception as e:                       # noqa: BLE001
            log.debug("evaluate_js failed: %s", e)

    # -- window controls --

    def _toggle_window(self):
        self._hide_window() if self._visible else self._show_window()

    def _show_window(self):
        try:
            self._window.show()
            self._visible = True
            self._push([("focus_input", "")])
        except Exception:                            # noqa: BLE001
            pass

    def _hide_window(self):
        try:
            self._window.hide()
            self._visible = False
        except Exception:                            # noqa: BLE001
            pass

    def _destroy(self):
        try:
            self._window.destroy()
        except Exception:                            # noqa: BLE001
            pass
