"""The A.T.L.A.S. HUD: frameless, always-on-top, transparent tkinter overlay.

Black & violet theme. All widgets live on the main thread; everything arriving
from workers comes through EventBus.drain() on a 33 ms tick — that tick also
drives the orb animation and the character-by-character typewriter.

Orb states: idle (slow breathe) · listening (fast pulse) · thinking (violet
arcs spin) · tool (arcs spin amber) · speaking (ripples).
"""
from __future__ import annotations

import math
import tkinter as tk
import tkinter.font as tkfont
from collections import deque

# black & violet palette
VOID = "#050308"          # near-black with violet cast (panel color)
ACCENT = "#a855f7"        # violet
ACCENT_HOT = "#d8b4fe"    # hot edge for the orb core
ACCENT_DIM = "#6d28d9"
GHOST = "#190d25"         # rgba(168,85,247,.12) pre-blended over VOID
SCAN = "#0b0613"          # scanline stripe
AMBER = "#f59e0b"         # tool-execution state (contrast against violet)
CHROMA = "#010203"        # magic transparent color (Windows -transparentcolor)

EYEBROW = "A.T.L.A.S. · v0.1"
BACKRONYM = "AUTONOMOUS TASK & LOGIC ASSISTANCE SYSTEM"

W, H = 460, 580
ORB = 190                 # orb square size
TICK_MS = 33


class Hud:
    def __init__(self, bus, on_submit, on_ptt_hint: str = "F8"):
        self.bus = bus
        self.on_submit = on_submit
        self.state = "idle"
        self.phase = 0.0
        self.ripples: list[float] = []
        self.typewriter: deque[str] = deque()
        self._confirm_open = False
        self._pending_confirms: deque = deque()

        self.root = tk.Tk()
        self.root.title("A.T.L.A.S.")
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        try:
            self.root.attributes("-alpha", 0.94)
            self.root.attributes("-transparentcolor", CHROMA)
        except tk.TclError:
            pass  # non-Windows dev box: solid window is fine
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        self.root.geometry(f"{W}x{H}+{(sw - W) // 2}+{max(40, (sh - H) // 3)}")
        self.root.configure(bg=CHROMA)

        thin = tkfont.Font(family="Segoe UI Light", size=10)
        tiny = tkfont.Font(family="Segoe UI Light", size=7)
        mono = tkfont.Font(family="Consolas", size=10)

        self.canvas = tk.Canvas(self.root, width=W, height=ORB + 40, bg=CHROMA,
                                highlightthickness=0)
        self.canvas.pack()
        # drag the whole window by the orb area
        self.canvas.bind("<Button-1>", self._drag_start)
        self.canvas.bind("<B1-Motion>", self._drag_move)

        panel = tk.Frame(self.root, bg=VOID, highlightthickness=1,
                         highlightbackground=GHOST)
        panel.pack(fill="both", expand=True, padx=6)

        # eyebrow: name·version, backronym beneath it
        tk.Label(panel, text=EYEBROW, fg=ACCENT, bg=VOID,
                 font=("Segoe UI Light", 11), anchor="w").pack(fill="x",
                                                               padx=10, pady=(8, 0))
        tk.Label(panel, text=BACKRONYM, fg=ACCENT_DIM, bg=VOID,
                 font=tiny, anchor="w").pack(fill="x", padx=10)

        self.status = tk.Label(panel, text="ONLINE", fg=ACCENT_DIM, bg=VOID,
                               font=thin, anchor="w")
        self.status.pack(fill="x", padx=10, pady=(4, 0))

        self.out = tk.Text(panel, bg=VOID, fg=ACCENT, insertbackground=ACCENT,
                           font=mono, wrap="word", relief="flat", height=12,
                           state="disabled", padx=10, pady=6)
        self.out.pack(fill="both", expand=True)
        self.out.tag_configure("dim", foreground=ACCENT_DIM)
        self.out.tag_configure("scan", background=SCAN)
        self._scan_flip = False

        entry_row = tk.Frame(panel, bg=VOID)
        entry_row.pack(fill="x", padx=10, pady=(0, 8))
        tk.Label(entry_row, text="❯", fg=ACCENT_HOT, bg=VOID,
                 font=mono).pack(side="left")
        self.entry = tk.Entry(entry_row, bg=GHOST, fg=ACCENT_HOT,
                              insertbackground=ACCENT, relief="flat", font=mono)
        self.entry.pack(side="left", fill="x", expand=True, padx=(6, 0), ipady=4)
        self.entry.bind("<Return>", self._submit)
        self.root.bind("<Escape>", lambda e: self.hide())

        self._append(f"Atlas online. Type below, or hold {on_ptt_hint} to speak.\n",
                     dim=True)
        self.root.after(TICK_MS, self._tick)

    # ---- window plumbing -----------------------------------------------

    def _drag_start(self, e):
        self._dx, self._dy = e.x, e.y

    def _drag_move(self, e):
        self.root.geometry(f"+{e.x_root - self._dx}+{e.y_root - self._dy}")

    def toggle(self):
        if self.root.state() == "withdrawn":
            self.show()
        else:
            self.hide()

    def show(self):
        self.root.deiconify()
        self.root.attributes("-topmost", True)
        self.root.focus_force()
        self.entry.focus_set()

    def hide(self):
        if not self._confirm_open:
            self.root.withdraw()

    def _quit(self):
        # deny any parked confirmations (fail closed), then leave mainloop
        while self._pending_confirms:
            self._pending_confirms.popleft().resolve(False)
        self.root.destroy()

    def _submit(self, _e=None):
        text = self.entry.get().strip()
        if not text:
            return
        self.entry.delete(0, "end")
        self._append(f"\n❯ {text}\n", dim=True)
        self.on_submit(text)

    # ---- output ----------------------------------------------------------

    def _append(self, text: str, dim: bool = False):
        self.out.configure(state="normal")
        # subtle scanlines: alternate line background tags
        self._scan_flip = not self._scan_flip
        tags = ("dim",) if dim else ()
        if self._scan_flip:
            tags = tags + ("scan",)
        self.out.insert("end", text, tags)
        self.out.see("end")
        self.out.configure(state="disabled")

    # ---- main tick: events + typewriter + orb -----------------------------

    def _tick(self):
        for kind, payload in self.bus.drain():
            if kind == "state":
                self.state = payload
                self.status.configure(text=payload.upper(), fg=ACCENT_DIM)
            elif kind == "stream":
                self.typewriter.extend(payload)
            elif kind == "tool":
                self.state = "tool"
                self.typewriter.extend(f"\n[{payload}]\n")
                self.status.configure(text=payload, fg=AMBER)
            elif kind == "notify":
                self._append(f"\n{payload}\n", dim=True)
            elif kind == "speak":
                self.typewriter.append("\n")
                if self._on_speak:
                    self._on_speak(payload)
            elif kind == "toggle":
                self.toggle()
            elif kind == "show":
                self.show()
            elif kind == "quit":
                self._quit()
                return
            elif kind == "confirm":
                self._pending_confirms.append(payload)

        # typewriter: a few chars per frame → streamed look even on burst input
        n = min(len(self.typewriter), 4)
        if n:
            self._append("".join(self.typewriter.popleft() for _ in range(n)))

        if self._pending_confirms and not self._confirm_open:
            self._open_confirm(self._pending_confirms.popleft())

        self.phase += 0.09
        self._draw_orb()
        self.root.after(TICK_MS, self._tick)

    _on_speak = None

    def set_speaker(self, fn):
        self._on_speak = fn

    # ---- orb ---------------------------------------------------------------

    def _draw_orb(self):
        c = self.canvas
        c.delete("all")
        cx, cy, base = W / 2, (ORB + 40) / 2, ORB / 2 - 8

        if self.state == "listening":
            r = base * (0.72 + 0.14 * math.sin(self.phase * 2.4))  # fast pulse
        elif self.state == "speaking":
            r = base * 0.7
            if int(self.phase * 10) % 6 == 0:
                self.ripples.append(r)                             # spawn ripple
        else:
            r = base * (0.7 + 0.05 * math.sin(self.phase * 0.7))   # slow breathe

        # ripples expand and fade
        self.ripples = [rp + 2.2 for rp in self.ripples if rp < base * 1.15]
        for rp in self.ripples:
            c.create_oval(cx - rp, cy - rp, cx + rp, cy + rp,
                          outline=GHOST, width=1)

        # corner brackets framing the orb — violet, HUD-style
        for sx, sy in ((-1, -1), (1, -1), (-1, 1), (1, 1)):
            bx, by = cx + sx * (base + 6), cy + sy * (base + 6)
            c.create_line(bx, by, bx - sx * 14, by, fill=ACCENT_DIM, width=1)
            c.create_line(bx, by, bx, by - sy * 14, fill=ACCENT_DIM, width=1)

        # orb rings: dim outer glow ring, violet mid ring, hot core
        c.create_oval(cx - r, cy - r, cx + r, cy + r, outline=ACCENT_DIM, width=1)
        c.create_oval(cx - r * .55, cy - r * .55, cx + r * .55, cy + r * .55,
                      outline=ACCENT, width=2)
        c.create_oval(cx - r * .18, cy - r * .18, cx + r * .18, cy + r * .18,
                      fill=ACCENT_HOT, outline=ACCENT_HOT)

        # segmented outer arcs — spin fast when thinking/tool, drift otherwise;
        # amber while a tool executes, violet otherwise
        busy = self.state in ("thinking", "tool")
        speed = 9.0 if busy else 1.2
        arc_color = AMBER if self.state == "tool" else ACCENT
        ang = (self.phase * speed * 20) % 360
        for i in range(3):
            start = ang + i * 120
            c.create_arc(cx - r * .85, cy - r * .85, cx + r * .85, cy + r * .85,
                         start=start, extent=70, style="arc",
                         outline=arc_color, width=2)

    # ---- confirmation modal --------------------------------------------

    def _open_confirm(self, req):
        self._confirm_open = True
        self.show()
        top = tk.Toplevel(self.root)
        top.overrideredirect(True)
        top.attributes("-topmost", True)
        top.configure(bg=VOID, highlightthickness=2, highlightbackground=ACCENT)
        top.geometry(f"380x220+{self.root.winfo_x() + 40}+{self.root.winfo_y() + 140}")

        def finish(approved: bool):
            if not req.done.is_set():
                req.resolve(approved)
            self._confirm_open = False
            top.destroy()

        tk.Label(top, text="⚠ CONFIRMATION REQUIRED", fg=ACCENT_HOT, bg=VOID,
                 font=("Segoe UI", 11, "bold")).pack(pady=(14, 4))
        tk.Label(top, text=req.title, fg=ACCENT, bg=VOID,
                 font=("Segoe UI Light", 10)).pack()
        body = tk.Label(top, text=req.detail[:600], fg=ACCENT_DIM, bg=VOID,
                        font=("Consolas", 9), justify="left",
                        wraplength=340)
        body.pack(pady=6, padx=14)
        row = tk.Frame(top, bg=VOID)
        row.pack(pady=8)
        tk.Button(row, text="DENY (Esc)", command=lambda: finish(False),
                  bg="#1a0505", fg="#ff5555", relief="flat", width=12,
                  activebackground="#330a0a").pack(side="left", padx=8)
        tk.Button(row, text="ALLOW", command=lambda: finish(True),
                  bg=GHOST, fg=ACCENT_HOT, relief="flat", width=12,
                  activebackground="#2d1745").pack(side="left", padx=8)
        top.bind("<Escape>", lambda e: finish(False))
        top.protocol("WM_DELETE_WINDOW", lambda: finish(False))
        top.focus_force()

    def run(self):
        self.root.mainloop()
