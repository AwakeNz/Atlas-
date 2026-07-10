"""Full action log to atlas.log (next to the exe) + in-memory ring for the HUD."""
from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler

from .config import app_dir

_configured = False


def get_logger(name: str = "atlas") -> logging.Logger:
    global _configured
    logger = logging.getLogger(name)
    if not _configured:
        root = logging.getLogger("atlas")
        root.setLevel(logging.INFO)
        handler = RotatingFileHandler(
            app_dir() / "atlas.log", maxBytes=1_000_000, backupCount=2, encoding="utf-8"
        )
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
        )
        root.addHandler(handler)
        _configured = True
    return logger
