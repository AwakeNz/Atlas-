"""EventBus: the only bridge between worker threads and the tkinter thread.

Workers post immutable event tuples; the UI drains the queue on a 33 ms tick.
Confirmations are the one synchronous path: the worker parks on a
threading.Event that the UI thread sets after the modal closes.
"""
from __future__ import annotations

import queue
import threading
from dataclasses import dataclass, field


@dataclass
class ConfirmRequest:
    title: str
    detail: str
    done: threading.Event = field(default_factory=threading.Event)
    approved: bool = False

    def resolve(self, approved: bool) -> None:
        self.approved = approved
        self.done.set()


class EventBus:
    def __init__(self):
        self._q: queue.Queue = queue.Queue()

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

    def toggle(self) -> None:                      # hotkey pressed
        self._q.put(("toggle", None))

    def show(self) -> None:                        # force-show the HUD (tray)
        self._q.put(("show", None))

    def quit(self) -> None:                        # tray → shut the app down
        self._q.put(("quit", None))

    def confirm(self, title: str, detail: str, timeout: float = 60.0) -> bool:
        """Block the calling worker until the user answers the modal.
        Timeout or app shutdown = deny (fail closed)."""
        req = ConfirmRequest(title, detail)
        self._q.put(("confirm", req))
        req.done.wait(timeout)
        return req.approved

    # ---- UI-side API ----
    def drain(self, limit: int = 200):
        events = []
        try:
            for _ in range(limit):
                events.append(self._q.get_nowait())
        except queue.Empty:
            pass
        return events
