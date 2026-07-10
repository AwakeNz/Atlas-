"""game_interact — send keystrokes/clicks to a game the user has EXPLICITLY
whitelisted.

Hard policy, checked on every call, in this order:
1. `target_window` must match an entry in settings.json →
   allowed_game_windows (ships EMPTY — nothing is automatable out of the box).
2. The CURRENTLY FOCUSED window must match that same entry. We never focus a
   window ourselves and never send input 'blind' — if the user alt-tabbed
   away, we refuse rather than type into whatever is in front.
3. Input volume is capped (max 25 key events / 10 clicks per call) so the
   model cannot script long unattended macro sessions through one call.

This exists so the user can automate games THEY OWN AND PLAY — not other
people's software. The whitelist is the user's explicit, per-title consent.
"""

MAX_KEYS = 25
MAX_CLICKS = 10


class Plugin:
    name = "game_interact"
    description = ("Send keyboard/mouse input to a game window the user has "
                   "whitelisted in settings.json → allowed_game_windows. "
                   "Refuses any window not on that list, and refuses if that "
                   "window is not currently focused. Actions: press (list of "
                   "keys, e.g. ['w','w','e']), hold (key + seconds<=3), click "
                   "(left/right, optional x,y).")
    parameters = {
        "type": "object",
        "properties": {
            "target_window": {"type": "string",
                              "description": "Whitelisted window title (partial match)."},
            "action": {"type": "string", "enum": ["press", "hold", "click"]},
            "keys": {"type": "array", "items": {"type": "string"},
                     "description": "Keys for 'press' (max 25)."},
            "key": {"type": "string", "description": "Key for 'hold'."},
            "seconds": {"type": "number", "description": "Hold duration, max 3."},
            "button": {"type": "string", "enum": ["left", "right"]},
            "x": {"type": "integer"}, "y": {"type": "integer"},
            "count": {"type": "integer", "description": "Clicks (max 10)."},
        },
        "required": ["target_window", "action"],
    }
    requires_confirmation = False   # gated by the whitelist + focus check instead

    def _authorize(self, ctx, target_window: str):
        """Returns (ok, message). Both whitelist AND focus must match."""
        want = target_window.strip().lower()
        if not want:
            return False, "[denied] target_window is required."
        allowed = [str(t).lower() for t in ctx.config.get("allowed_game_windows", [])]
        entry = next((a for a in allowed if a in want or want in a), None)
        if entry is None:
            return False, ("[denied] That window is not whitelisted. The user must "
                           "add its title to allowed_game_windows in settings.json "
                           "themselves — do not offer to edit it for them.")
        import pygetwindow as gw  # lazy
        active = gw.getActiveWindow()
        active_title = (active.title if active else "").lower()
        if entry not in active_title:
            return False, (f"[denied] The whitelisted window is not focused "
                           f"(focused: '{active_title or 'nothing'}'). Ask the "
                           "user to click into the game first.")
        return True, entry

    def execute(self, ctx, target_window: str, action: str, keys=None,
                key: str = "", seconds: float = 0.5, button: str = "left",
                x: int = -1, y: int = -1, count: int = 1) -> str:
        ok, msg = self._authorize(ctx, target_window)
        if not ok:
            return msg

        import time
        import pydirectinput  # lazy; DirectInput-level events games can see
        pydirectinput.PAUSE = 0.05

        action = action.strip().lower()
        if action == "press":
            keys = [str(k) for k in (keys or []) if k][:MAX_KEYS]
            if not keys:
                return "[plugin error] 'press' needs a keys list."
            for k in keys:
                pydirectinput.press(k)
            return f"Pressed {len(keys)} key(s) in '{target_window}'."

        if action == "hold":
            if not key:
                return "[plugin error] 'hold' needs a key."
            seconds = max(0.05, min(float(seconds), 3.0))
            pydirectinput.keyDown(key)
            time.sleep(seconds)
            pydirectinput.keyUp(key)
            return f"Held '{key}' for {seconds:.2f}s."

        if action == "click":
            count = max(1, min(int(count), MAX_CLICKS))
            kwargs = {"button": "right" if button == "right" else "left"}
            if x >= 0 and y >= 0:
                kwargs.update(x=int(x), y=int(y))
            for _ in range(count):
                pydirectinput.click(**kwargs)
            return f"Clicked {kwargs['button']} ×{count}."

        return f"[plugin error] unknown action '{action}'."
