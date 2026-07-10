"""Dependency-free CPU/RAM readout for the HUD side panels.

Windows uses ctypes (GetSystemTimes + GlobalMemoryStatusEx). Linux (dev boxes)
reads /proc. Anything else returns zeros. No psutil — keeps the dep budget and
cold start honest.
"""
from __future__ import annotations

import sys
import time


class SysStat:
    def __init__(self):
        self._prev = None   # (idle, total) for CPU delta

    def sample(self) -> tuple[float, float]:
        """Return (cpu_percent, ram_percent), each 0..100."""
        if sys.platform == "win32":
            return self._win()
        if sys.platform.startswith("linux"):
            return self._linux()
        return 0.0, 0.0

    # -- Windows --
    def _win(self):
        import ctypes
        from ctypes import wintypes

        idle = wintypes.FILETIME()
        kernel = wintypes.FILETIME()
        user = wintypes.FILETIME()
        cpu = 0.0
        if ctypes.windll.kernel32.GetSystemTimes(ctypes.byref(idle),
                                                 ctypes.byref(kernel),
                                                 ctypes.byref(user)):
            def q(ft):
                return (ft.dwHighDateTime << 32) | ft.dwLowDateTime
            idle_t, kern_t, user_t = q(idle), q(kernel), q(user)
            total = kern_t + user_t
            if self._prev is not None:
                dt = total - self._prev[1]
                di = idle_t - self._prev[0]
                if dt > 0:
                    cpu = max(0.0, min(100.0, (1 - di / dt) * 100))
            self._prev = (idle_t, total)

        class MEMSTAT(ctypes.Structure):
            _fields_ = [("dwLength", ctypes.c_ulong),
                        ("dwMemoryLoad", ctypes.c_ulong),
                        ("ullTotalPhys", ctypes.c_ulonglong),
                        ("ullAvailPhys", ctypes.c_ulonglong),
                        ("ullTotalPageFile", ctypes.c_ulonglong),
                        ("ullAvailPageFile", ctypes.c_ulonglong),
                        ("ullTotalVirtual", ctypes.c_ulonglong),
                        ("ullAvailVirtual", ctypes.c_ulonglong),
                        ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
        m = MEMSTAT()
        m.dwLength = ctypes.sizeof(MEMSTAT)
        ram = 0.0
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m)):
            ram = float(m.dwMemoryLoad)
        return round(cpu, 1), round(ram, 1)

    # -- Linux (dev) --
    def _linux(self):
        cpu = 0.0
        try:
            with open("/proc/stat") as f:
                parts = [float(x) for x in f.readline().split()[1:]]
            idle_t = parts[3] + (parts[4] if len(parts) > 4 else 0)
            total = sum(parts)
            if self._prev is not None:
                dt = total - self._prev[1]
                di = idle_t - self._prev[0]
                if dt > 0:
                    cpu = max(0.0, min(100.0, (1 - di / dt) * 100))
            self._prev = (idle_t, total)
        except OSError:
            pass
        ram = 0.0
        try:
            info = {}
            with open("/proc/meminfo") as f:
                for line in f:
                    k, _, v = line.partition(":")
                    info[k] = float(v.strip().split()[0])
            total = info.get("MemTotal", 0)
            avail = info.get("MemAvailable", 0)
            if total:
                ram = (1 - avail / total) * 100
        except OSError:
            pass
        return round(cpu, 1), round(ram, 1)


def start_reporter(bus, chain, agent, interval: float = 1.5):
    """Daemon thread that pushes (cpu, ram, tokens, provider) to the HUD."""
    import threading

    stat = SysStat()
    stat.sample()  # prime CPU delta

    def loop():
        while True:
            cpu, ram = stat.sample()
            provider = getattr(chain, "current_name", lambda: "—")()
            tokens = getattr(agent, "session_tokens", 0)
            bus.stat(cpu, ram, tokens, provider)
            time.sleep(interval)

    threading.Thread(target=loop, name="sysstat", daemon=True).start()
