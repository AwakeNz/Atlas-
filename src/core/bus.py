"""EventBus: the only bridge between worker threads and the UI thread (tkinter
or pywebview). Workers post immutable event tuples; the UI drains the queue on
its own tick. Confirmations are the one synchronous path: the worker parks on a
threading.Event that the UI thread sets after the modal closes.
"""
from __future__ import annotations

import itertools
import queue
import threading
from dataclasses import dataclass, field


@dataclass
class ConfirmRequest:
    title: str
    detail: str
    id: int = 0
    done: threading.Event = field(default_factory=threading.Event)
    approved: bool = False

    def resolve(self, approved: bool) -> None:
        self.approved = approved
        self.done.set()


class EventBus:
    def __init__(self):
        self._q: queue.Queue = queue.Queue()
        self._ids = itertools.count(1)
        self._pending: dict[int, ConfirmRequest] = {}
        self._lock = threading.Lock()

    # ---- worker-side API ----
    def state(self, name: str) -> None:            # idle|listening|thinking|tool|speaking
        self._q.put(("state", name))

    def stream(self, text: str) -> None:           # streamed model tokens
        self._q.put(("stream", text))

    def tool(self, label: str) -> None:            # "EXECUTING: tool_name"
        self._q.put(("tool", label))

    def notify(self, text: str) -> None:           # one-off status line
        self._q.put(("notify", text))

    def speak(self, text: str) -> None:            # final answer → TTS
        self._q.put(("speak", text))

    def provider(self, name: str) -> None:         # active LLM provider changed
        self._q.put(("provider", name))

    def progress(self, label: str, pct: float) -> None:   # model download etc.
        self._q.put(("progress", (label, pct)))

    def boot(self, stage: str) -> None:            # boot-animation stage text
        self._q.put(("boot", stage))

    def stat(self, cpu: float, ram: float, tokens: int, provider: str) -> None:
        self._q.put(("stat", (cpu, ram, tokens, provider)))

    def mic(self, muted: bool) -> None:            # mic mute state changed
        self._q.put(("mic", muted))

    def update(self, version: str, url: str) -> None:      # update available
        self._q.put(("update", (version, url)))

    def toggle(self) -> None:                      # hotkey pressed
        self._q.put(("toggle", None))

    def show(self) -> None:                        # force-show the HUD (tray)
        self._q.put(("show", None))

    def quit(self) -> None:                        # tray → shut the app down
        self._q.put(("quit", None))

    def confirm(self, title: str, detail: str, timeout: float = 60.0) -> bool:
        """Block the calling worker until the user answers the modal.
        Timeout or app shutdown = deny (fail closed)."""
        req = ConfirmRequest(title, detail, id=next(self._ids))
        with self._lock:
            self._pending[req.id] = req
        self._q.put(("confirm", req))
        req.done.wait(timeout)
        with self._lock:
            self._pending.pop(req.id, None)
        return req.approved

    def resolve_confirm(self, req_id: int, approved: bool) -> None:
        """Called from the UI thread (e.g. a JS bridge callback) to answer a
        confirmation by id."""
        with self._lock:
            req = self._pending.get(req_id)
        if req is not None:
            req.resolve(approved)

    # ---- UI-side API ----
    def drain(self, limit: int = 200):
        events = []
        try:
            for _ in range(limit):
                events.append(self._q.get_nowait())
        except queue.Empty:
            pass
        return events
