"""window_control — list / focus / minimize windows via pygetwindow."""


class Plugin:
    name = "window_control"
    description = ("Manage open windows: 'list' returns visible window titles; "
                   "'focus' brings a window to the front; 'minimize' minimizes "
                   "it. Match by (partial, case-insensitive) title.")
    parameters = {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["list", "focus", "minimize"]},
            "title": {"type": "string",
                      "description": "Partial window title (focus/minimize)."},
        },
        "required": ["action"],
    }
    requires_confirmation = False

    def _find(self, gw, title: str):
        want = title.strip().lower()
        for w in gw.getAllWindows():
            if w.title and want in w.title.lower():
                return w
        return None

    def execute(self, ctx, action: str, title: str = "") -> str:
        import pygetwindow as gw  # lazy

        action = action.strip().lower()
        if action == "list":
            titles = [w.title for w in gw.getAllWindows() if w.title and w.visible]
            return "Open windows:\n" + "\n".join(f"- {t}" for t in titles[:40])

        if not title:
            return "[plugin error] 'title' is required for focus/minimize."
        win = self._find(gw, title)
        if win is None:
            return f"[plugin error] no window matching '{title}'."
        try:
            if action == "focus":
                if win.isMinimized:
                    win.restore()
                win.activate()
                return f"Focused '{win.title}'."
            if action == "minimize":
                win.minimize()
                return f"Minimized '{win.title}'."
        except Exception as e:
            return f"[plugin error] window operation failed: {e}"
        return f"[plugin error] unknown action '{action}'."
