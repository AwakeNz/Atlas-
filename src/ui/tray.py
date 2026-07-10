"""System tray icon for A.T.L.A.S. — violet orb glyph, tooltip with the
backronym, and a menu for show/hide, skills list/reload, and quit.

pystray runs its own message loop on a daemon thread; every menu action only
posts to the EventBus or calls the thread-safe SkillsIndex — never tkinter.
Tray failure (unsupported shell, missing backend) degrades silently: the
hotkey and HUD are the primary interface.
"""
from __future__ import annotations

import threading

from core.log import get_logger

log = get_logger("atlas.tray")

TOOLTIP = "A.T.L.A.S. — Autonomous Task & Logic Assistance System"


def _make_icon_image():
    """Draw the orb: violet ring + hot core on transparent ground."""
    from PIL import Image, ImageDraw

    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse((4, 4, 60, 60), outline=(109, 40, 217, 255), width=3)    # dim ring
    d.ellipse((14, 14, 50, 50), outline=(168, 85, 247, 255), width=4)  # accent
    d.ellipse((26, 26, 38, 38), fill=(216, 180, 254, 255))             # hot core
    return img


def start_tray(bus, skills) -> None:
    threading.Thread(target=_run, args=(bus, skills), name="tray",
                     daemon=True).start()


def _run(bus, skills) -> None:
    try:
        import pystray
    except Exception as e:
        log.warning("tray unavailable (%s) — hotkey/HUD only", e)
        return

    def on_list(icon, item):
        names = skills.names()
        bus.notify("Installed skills: " +
                   (", ".join(names) if names else "(none — drop folders into skills/)"))
        bus.show()

    def on_reload(icon, item):
        bus.notify(skills.reload())
        bus.show()

    def on_quit(icon, item):
        icon.stop()
        bus.quit()

    menu = pystray.Menu(
        pystray.MenuItem("Show / Hide", lambda icon, item: bus.toggle(),
                         default=True),
        pystray.MenuItem("Skills: list", on_list),
        pystray.MenuItem("Skills: reload", on_reload),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Quit A.T.L.A.S.", on_quit),
    )
    try:
        icon = pystray.Icon("atlas", _make_icon_image(), TOOLTIP, menu)
        log.info("tray icon running")
        icon.run()
    except Exception as e:
        log.warning("tray failed (%s) — hotkey/HUD only", e)
