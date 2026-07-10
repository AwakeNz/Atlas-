"""system_control — volume, brightness, lock, screenshot. Windows-only.

Volume uses virtual-key injection (no COM dependency); brightness uses the
WMI monitor interface via PowerShell; lock is a single user32 call;
screenshots go to Pictures with a timestamp.
"""
import ctypes
import datetime
import subprocess
import sys
from pathlib import Path

VK = {"volume_up": 0xAF, "volume_down": 0xAE, "volume_mute": 0xAD}
ACTIONS = ["volume_up", "volume_down", "volume_mute", "brightness", "lock",
           "screenshot"]


class Plugin:
    name = "system_control"
    description = ("Control this Windows PC: volume_up/volume_down (pass "
                   "`amount` for repeated steps), volume_mute, brightness "
                   "(pass `amount` 0-100), lock the workstation, or take a "
                   "screenshot (saved to Pictures).")
    parameters = {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ACTIONS},
            "amount": {"type": "integer",
                       "description": "Volume steps (1-50) or brightness percent (0-100)."},
        },
        "required": ["action"],
    }
    requires_confirmation = False

    def execute(self, ctx, action: str, amount: int = 5) -> str:
        if sys.platform != "win32":
            return "[plugin error] system_control only works on Windows."
        action = action.strip().lower()

        if action in VK:
            steps = 1 if action == "volume_mute" else max(1, min(int(amount), 50))
            for _ in range(steps):
                ctypes.windll.user32.keybd_event(VK[action], 0, 0, 0)
                ctypes.windll.user32.keybd_event(VK[action], 0, 2, 0)  # key up
            return f"Done: {action} ×{steps}."

        if action == "brightness":
            level = max(0, min(int(amount), 100))
            # WMI call is fixed text; only the integer level is interpolated.
            cmd = ("(Get-WmiObject -Namespace root/WMI -Class WmiMonitorBrightnessMethods)"
                   f".WmiSetBrightness(1,{level})")
            r = subprocess.run(["powershell", "-NoProfile", "-Command", cmd],
                               capture_output=True, timeout=10)
            if r.returncode != 0:
                return ("[plugin error] brightness control unsupported on this "
                        "display (external monitors often are).")
            return f"Brightness set to {level}%."

        if action == "lock":
            ctypes.windll.user32.LockWorkStation()
            return "Workstation locked."

        if action == "screenshot":
            from PIL import ImageGrab  # lazy: Pillow is heavy
            pictures = Path.home() / "Pictures"
            pictures.mkdir(exist_ok=True)
            path = pictures / f"atlas_{datetime.datetime.now():%Y%m%d_%H%M%S}.png"
            ImageGrab.grab().save(path)
            return f"Screenshot saved to {path}"

        return f"[plugin error] unknown action '{action}'. Valid: {', '.join(ACTIONS)}"
