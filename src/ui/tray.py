"""System tray icon for A.T.L.A.S. — violet orb glyph, backronym tooltip, and a
menu for show/hide, mic mute, skills, updates, and quit.

pystray runs its own message loop on a daemon thread; every menu action only
posts to the EventBus or calls a thread-safe callback — never the UI toolkit.
Tray failure degrades silently: the hotkey and HUD stay primary.
"""
from __future__ import annotations

import threading

from core.log import get_logger

log = get_logger("atlas.tray")

TOOLTIP = "A.T.L.A.S. — Autonomous Task & Logic Assistance System"


def _make_icon_image(muted: bool = False):
    """Orb glyph: violet ring + hot core. A muted mic shows an amber slash."""
    from PIL import Image, ImageDraw

    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse((4, 4, 60, 60), outline=(109, 40, 217, 255), width=3)
    d.ellipse((14, 14, 50, 50), outline=(168, 85, 247, 255), width=4)
    d.ellipse((26, 26, 38, 38), fill=(216, 180, 254, 255))
    if muted:
        d.line((12, 52, 52, 12), fill=(255, 179, 71, 255), width=4)
    return img


def start_tray(bus, skills, controls=None) -> None:
    """controls: optional dict with callables — mic_toggle() -> bool (muted),
    is_muted() -> bool, check_updates(), install_update()."""
    threading.Thread(target=_run, args=(bus, skills, controls or {}),
                     name="tray", daemon=True).start()


def _run(bus, skills, controls) -> None:
    try:
        import pystray
    except Exception as e:                    # noqa: BLE001
        log.warning("tray unavailable (%s) — hotkey/HUD only", e)
        return

    state = {"icon": None}

    def refresh_icon():
        if state["icon"] is not None and controls.get("is_muted"):
            state["icon"].icon = _make_icon_image(controls["is_muted"]())

    def on_mic(icon, item):
        cb = controls.get("mic_toggle")
        if cb:
            cb()
            refresh_icon()

    def mic_checked(item):
        fn = controls.get("is_muted")
        return bool(fn()) if fn else False

    def on_list(icon, item):
        names = skills.names()
        bus.notify("Installed skills: " +
                   (", ".join(names) if names else "(none — drop folders into skills/)"))
        bus.show()

    def on_reload(icon, item):
        bus.notify(skills.reload()); bus.show()

    def on_check(icon, item):
        cb = controls.get("check_updates")
        if cb:
            threading.Thread(target=cb, daemon=True).start()

    def on_quit(icon, item):
        icon.stop(); bus.quit()

    items = [
        pystray.MenuItem("Show / Hide", lambda icon, item: bus.toggle(), default=True),
    ]
    if controls.get("mic_toggle"):
        items.append(pystray.MenuItem("Mute microphone", on_mic, checked=mic_checked))
    items += [
        pystray.MenuItem("Skills: list", on_list),
        pystray.MenuItem("Skills: reload", on_reload),
        pystray.MenuItem("Check for updates", on_check),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Quit A.T.L.A.S.", on_quit),
    ]
    try:
        icon = pystray.Icon("atlas", _make_icon_image(), TOOLTIP, pystray.Menu(*items))
        state["icon"] = icon
        log.info("tray icon running")
        icon.run()
    except Exception as e:                    # noqa: BLE001
        log.warning("tray failed (%s) — hotkey/HUD only", e)
