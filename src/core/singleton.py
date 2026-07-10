"""Named Windows mutex so the Inno Setup installer can detect a running
A.T.L.A.S. instance (Inno `AppMutex`) and close it gracefully before an
upgrade. The name MUST match `AppMutex` in installer/atlas.iss.

Held for the process lifetime; released automatically on exit. No-op off
Windows. Never fatal — a mutex failure must not stop the app launching.
"""
from __future__ import annotations

import sys

from .log import get_logger

log = get_logger("atlas.singleton")

# Must equal AppMutex in installer/atlas.iss.
MUTEX_NAME = "Global\\ATLAS_Running_Mutex"

_handle = None


def create_mutex() -> None:
    global _handle
    if sys.platform != "win32":
        return
    try:
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.windll.kernel32
        kernel32.CreateMutexW.restype = wintypes.HANDLE
        kernel32.CreateMutexW.argtypes = [wintypes.LPVOID, wintypes.BOOL,
                                          wintypes.LPCWSTR]
        _handle = kernel32.CreateMutexW(None, False, MUTEX_NAME)
        if not _handle:
            log.warning("CreateMutex failed (err %s)", kernel32.GetLastError())
        else:
            log.info("app mutex created: %s", MUTEX_NAME)
    except Exception as e:                    # noqa: BLE001
        log.warning("mutex unavailable: %s", e)
