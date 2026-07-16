"""
Floating always-on-top widget.
Compact: small pill showing %.
Click: expands to full usage details.
Drag: move anywhere on screen.
Right-click: menu.
"""

import tkinter as tk
from tkinter import ttk
import time
import threading
import webbrowser
import os
import sys


def _resource(filename: str) -> str:
    """Return absolute path to a bundled resource (works from source or exe)."""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, filename)

BG       = "#1e1e1e"
BG2      = "#2a2a2a"
BG3      = "#333333"
FG       = "#e8e8e8"
FG_DIM   = "#888888"
GREEN    = "#3ab56b"
YELLOW   = "#e6a020"
RED      = "#e05252"
BLUE     = "#4a90d9"

BAR_W      = 160   # compact bar width
BAR_H      = 10    # compact bar height (the thin line)
EXPANDED_W = 360


def _pct_color(pct, warn, crit):
    if pct >= crit:  return RED
    if pct >= warn:  return YELLOW
    return GREEN


CORNER_MARGIN = 6
MIN_DIM       = 1

_CORNER_CURSOR = {
    "nw": "size_nw_se",
    "se": "size_nw_se",
    "ne": "size_ne_sw",
    "sw": "size_ne_sw",
}


def _corner_at(x, y, w, h, margin=CORNER_MARGIN):
    """Which corner ('nw'/'ne'/'sw'/'se') the point (x, y) is within `margin`
    px of, inside a (w, h)-sized canvas. None if not near any corner."""
    near_left   = x <= margin
    near_right  = x >= w - margin
    near_top    = y <= margin
    near_bottom = y >= h - margin
    if near_top and near_left:
        return "nw"
    if near_top and near_right:
        return "ne"
    if near_bottom and near_left:
        return "sw"
    if near_bottom and near_right:
        return "se"
    return None


def _resize_dims(corner, sw, sh, swx, swy, dx, dy):
    """New (width, height, x, y) for dragging `corner` by (dx, dy), starting
    from bar size (sw, sh) at window position (swx, swy). Clamps each
    dimension to MIN_DIM while keeping the corner opposite `corner` fixed in
    place, so the window never drifts once a dimension bottoms out."""
    if corner == "se":
        new_w = max(MIN_DIM, sw + dx)
        new_h = max(MIN_DIM, sh + dy)
        return new_w, new_h, swx, swy
    if corner == "ne":
        new_w = max(MIN_DIM, sw + dx)
        new_h = max(MIN_DIM, sh - dy)
        return new_w, new_h, swx, swy + (sh - new_h)
    if corner == "sw":
        new_w = max(MIN_DIM, sw - dx)
        new_h = max(MIN_DIM, sh + dy)
        return new_w, new_h, swx + (sw - new_w), swy
    if corner == "nw":
        new_w = max(MIN_DIM, sw - dx)
        new_h = max(MIN_DIM, sh - dy)
        return new_w, new_h, swx + (sw - new_w), swy + (sh - new_h)
    raise ValueError(f"unknown corner: {corner!r}")


def _font_pt_for_height(h):
    return max(6, round(h * 0.7))


class FloatingWidget:
    def __init__(self, get_data_fn, get_config_fn, on_settings_fn, on_quit_fn):
        self.get_data     = get_data_fn
        self.get_config   = get_config_fn
        self.on_settings  = on_settings_fn
        self.on_quit      = on_quit_fn

        self.expanded   = False
        self.win        = None
        self._drag_start_x = 0
        self._drag_start_y = 0
        self._win_start_x  = 0
        self._win_start_y  = 0
        self._dragging     = False
        self._pos_x        = None   # remembered position
        self._pos_y        = None

        # Compact-pill corner resize (never persisted — resets every launch)
        self._bar_w             = BAR_W
        self._bar_h             = BAR_H
        self._compact_canvas    = None
        self._resizing          = False
        self._resize_corner     = None
        self._resize_start_dims = (BAR_W, BAR_H)
        self._resize_start_pos  = (0, 0)

    # ── Lifecycle ────────────────────────────────────────────────────────────

    def start(self):
        """Run the widget (blocks — call in main thread or dedicated thread)."""
        self.win = tk.Tk()
        self.win.overrideredirect(True)
        self.win.attributes("-topmost", True)
        self.win.attributes("-alpha", 0.96)
        self.win.configure(bg=BG)
        self.win.resizable(False, False)

        # Restore saved position, or default to bottom-right
        self.win.update_idletasks()
        sw = self.win.winfo_screenwidth()
        sh = self.win.winfo_screenheight()
        cfg = self.get_config()
        self._pos_x = cfg.get("widget_x", sw - BAR_W - 24)
        self._pos_y = cfg.get("widget_y", sh - BAR_H - 60)

        self._render()
        self.win.mainloop()

    def refresh(self):
        """Re-render with fresh data (call from any thread)."""
        if self.win:
            self.win.after(0, self._render)

    # ── Rendering ────────────────────────────────────────────────────────────

    def _render(self):
        for w in self.win.winfo_children():
            w.destroy()

        if self.expanded:
            self._build_expanded()
        else:
            self._build_compact()

        self.win.update_idletasks()
        w = self.win.winfo_reqwidth()
        h = self.win.winfo_reqheight()
        self.win.geometry(f"{w}x{h}+{self._pos_x}+{self._pos_y}")

    def _build_compact(self):
        canvas = tk.Canvas(self.win, bg="#111111", highlightthickness=0)
        canvas.pack()
        self._compact_canvas = canvas
        self._draw_compact_canvas(canvas)
        self._bind_resizable_drag(canvas)

    def _draw_compact_canvas(self, canvas):
        """(Re)draw the compact bar at its current self._bar_w/self._bar_h.
        Resizes the existing canvas in place rather than recreating it, so
        this is safe to call mid-drag without losing event bindings."""
        cfg  = self.get_config()
        data = self.get_data()
        warn = cfg.get("warning_threshold", 70)
        crit = cfg.get("critical_threshold", 85)

        pct = 0
        if data and data.get("session"):
            pct = data["session"]["used_pct"]
        elif data and data.get("weekly"):
            pct = data["weekly"][0]["used_pct"]

        color = _pct_color(pct, warn, crit)
        w, h = self._bar_w, self._bar_h

        canvas.configure(width=w, height=h)
        canvas.delete("all")

        # Track (dark background)
        canvas.create_rectangle(0, 0, w, h, fill="#222222", outline="")

        # Filled portion
        fill_w = max(2, int(pct / 100 * w))
        canvas.create_rectangle(0, 0, fill_w, h, fill=color, outline="")

        # % label on the right side of the bar
        canvas.create_text(w - 3, h // 2, text=f"{pct}%",
                           anchor="e", fill=color,
                           font=("Segoe UI", _font_pt_for_height(h), "bold"))

    def _build_expanded(self):
        cfg  = self.get_config()
        data = self.get_data()
        warn = cfg.get("warning_threshold", 70)
        crit = cfg.get("critical_threshold", 85)

        outer = tk.Frame(self.win, bg=BG, padx=0, pady=0)
        outer.pack(fill="both", expand=True)

        # ── Title bar ────────────────────────────────────────────────────────
        title_bar = tk.Frame(outer, bg=BG2, padx=12, pady=8)
        title_bar.pack(fill="x")

        tk.Label(title_bar, text="Claude Usage", font=("Segoe UI", 11, "bold"),
                 bg=BG2, fg=FG).pack(side="left")

        if data:
            plan = data.get("plan", "Pro")
            tk.Label(title_bar, text=plan, font=("Segoe UI", 9),
                     bg=BG2, fg=FG_DIM).pack(side="left", padx=8)

        close_btn = tk.Label(title_bar, text="✕", font=("Segoe UI", 10),
                             bg=BG2, fg=FG_DIM, cursor="hand2")
        close_btn.pack(side="right")
        close_btn.bind("<Button-1>", self._on_click)

        self._bind_drag(title_bar)
        self._bind_drag(close_btn)

        # ── Content ───────────────────────────────────────────────────────────
        content = tk.Frame(outer, bg=BG, padx=14, pady=10, width=EXPANDED_W)
        content.pack(fill="x")
        content.pack_propagate(False)

        if not data:
            tk.Label(content, text="No data — loading…", bg=BG, fg=FG_DIM,
                     font=("Segoe UI", 9)).pack(pady=20)
        else:
            session = data.get("session")
            if session:
                self._section(content, "Current session")
                self._metric(content, session["label"], session["used_pct"],
                             session.get("resets_in", ""), warn, crit)
                self._sep(content)

            weekly = data.get("weekly", [])
            if weekly:
                self._section(content, "Weekly limits")
                for item in weekly:
                    self._metric(content, item["label"], item["used_pct"],
                                 item.get("resets_in", ""), warn, crit)
                self._sep(content)

            daily = data.get("daily", [])
            if daily:
                self._section(content, "Additional")
                for item in daily:
                    used  = item.get("used", 0)
                    total = item.get("total", 0)
                    note  = item.get("note") or (f"{used} / {total}" if total else "")
                    self._metric(content, item["label"], item["used_pct"],
                                 note, warn, crit,
                                 fraction=f"{used} / {total}" if total else None)

        # ── Footer ────────────────────────────────────────────────────────────
        footer = tk.Frame(outer, bg=BG2, padx=12, pady=6)
        footer.pack(fill="x")

        if hasattr(self, "_last_update") and self._last_update:
            age = int(time.time() - self._last_update)
            ago = f"{age}s ago" if age < 60 else f"{age//60}m ago"
            tk.Label(footer, text=f"Updated {ago}", bg=BG2, fg=FG_DIM,
                     font=("Segoe UI", 7)).pack(side="left")

        tk.Label(footer, text="⚙", font=("Segoe UI", 10), bg=BG2, fg=FG_DIM,
                 cursor="hand2").pack(side="right", padx=4) \
            .bind("<Button-1>", lambda e: threading.Thread(
                target=self.on_settings, daemon=True).start())

        self._bind_drag(footer)
        self._bind_drag(content)

    # ── Helpers ──────────────────────────────────────────────────────────────

    def _section(self, parent, text):
        tk.Label(parent, text=text, font=("Segoe UI", 9, "bold"),
                 bg=BG, fg=FG, anchor="w").pack(fill="x", pady=(6, 2))

    def _sep(self, parent):
        tk.Frame(parent, bg=BG3, height=1).pack(fill="x", pady=4)

    def _metric(self, parent, label, pct, sub, warn, crit, fraction=None):
        color = _pct_color(pct, warn, crit)
        row = tk.Frame(parent, bg=BG)
        row.pack(fill="x", pady=2)

        left = tk.Frame(row, bg=BG, width=130)
        left.pack(side="left", fill="y")
        left.pack_propagate(False)
        tk.Label(left, text=label, font=("Segoe UI", 9),
                 bg=BG, fg=FG, anchor="w").pack(anchor="w")
        if sub:
            tk.Label(left, text=sub, font=("Segoe UI", 7),
                     bg=BG, fg=FG_DIM, anchor="w").pack(anchor="w")

        right = tk.Frame(row, bg=BG)
        right.pack(side="right", fill="y")

        pct_text = fraction if fraction else f"{pct}%"
        tk.Label(right, text=pct_text, font=("Segoe UI", 9, "bold"),
                 bg=BG, fg=color, width=9, anchor="e").pack(anchor="e")

        bar_w = 190
        canvas = tk.Canvas(right, width=bar_w, height=6,
                            bg=BG3, highlightthickness=0)
        canvas.pack(anchor="e", pady=1)
        fill_w = max(4, int(pct / 100 * bar_w)) if pct else 2
        canvas.create_rectangle(0, 0, fill_w, 6, fill=color, outline="")

    # ── Details window ───────────────────────────────────────────────────────

    def _show_details_window(self):
        data = self.get_data()

        win = tk.Toplevel(self.win)
        win.title("Claude Usage Details")
        win.configure(bg="#1a1a1a")
        win.resizable(False, False)
        win.attributes("-topmost", True)
        try:
            win.iconbitmap(_resource("app.ico"))
        except Exception:
            pass

        DBG    = "#1a1a1a"
        DSEP   = "#333333"
        DTRACK = "#3a3a3a"
        DFILL  = "#4a9eff"
        DFG    = "#e8e8e8"
        DDIM   = "#888888"
        PAD    = 28
        BAR_W  = 320

        frame = tk.Frame(win, bg=DBG, padx=PAD, pady=20)
        frame.pack(fill="both", expand=True)

        def _sep():
            tk.Frame(frame, bg=DSEP, height=1).pack(fill="x", pady=(6, 4))

        def _header(text, badge=None):
            r = tk.Frame(frame, bg=DBG)
            r.pack(fill="x", pady=(14, 4))
            tk.Label(r, text=text, font=("Segoe UI", 13, "bold"),
                     bg=DBG, fg=DFG).pack(side="left")
            if badge:
                tk.Label(r, text=badge, font=("Segoe UI", 10),
                         bg=DBG, fg=DDIM).pack(side="right")

        def _row(name, sub, pct, label_right):
            r = tk.Frame(frame, bg=DBG)
            r.pack(fill="x", pady=5)
            r.columnconfigure(1, weight=1)

            tk.Label(r, text=name, font=("Segoe UI", 10, "bold"),
                     bg=DBG, fg=DFG, anchor="w").grid(
                         row=0, column=0, sticky="w", padx=(0, 20))
            if sub:
                tk.Label(r, text=sub, font=("Segoe UI", 8),
                         bg=DBG, fg=DDIM, anchor="w").grid(
                             row=1, column=0, sticky="w", padx=(0, 20))

            c = tk.Canvas(r, width=BAR_W, height=10,
                          bg=DTRACK, highlightthickness=0)
            c.grid(row=0, column=1, rowspan=2, sticky="ew", padx=(0, 16), pady=4)
            fill_w = max(4, int(pct / 100 * BAR_W)) if pct else 2
            c.create_rectangle(0, 0, fill_w, 10, fill=DFILL, outline="")

            tk.Label(r, text=label_right, font=("Segoe UI", 9),
                     bg=DBG, fg=DDIM, anchor="e").grid(
                         row=0, column=2, rowspan=2, sticky="e")

        if not data:
            tk.Label(frame, text="No data available — still loading.",
                     bg=DBG, fg=DDIM, font=("Segoe UI", 11)).pack(pady=40)
        else:
            plan = data.get("plan", "Pro")
            _header("Plan usage limits", plan)
            _sep()

            session = data.get("session")
            if session:
                sub = f"Resets in {session['resets_in']}" if session.get("resets_in") else ""
                _row(session["label"], sub, session["used_pct"],
                     f"{session['used_pct']}% used")

            weekly = data.get("weekly", [])
            if weekly:
                _sep()
                _header("Weekly limits")
                lnk = tk.Label(frame, text="Learn more about usage limits",
                               font=("Segoe UI", 8), bg=DBG, fg=DFILL,
                               cursor="hand2", anchor="w")
                lnk.pack(anchor="w")
                lnk.bind("<Button-1>",
                         lambda e: webbrowser.open("https://claude.ai/settings"))
                for item in weekly:
                    sub = f"Resets in {item['resets_in']}" if item.get("resets_in") else ""
                    _row(item["label"], sub, item["used_pct"],
                         f"{item['used_pct']}% used")

            if hasattr(self, "_last_update") and self._last_update:
                age = int(time.time() - self._last_update)
                ago = ("just now" if age < 10
                       else f"{age}s ago" if age < 60
                       else f"{age // 60}m ago")
                tk.Label(frame, text=f"Last updated: {ago}",
                         font=("Segoe UI", 8), bg=DBG, fg=DDIM,
                         anchor="w").pack(anchor="w", pady=(10, 2))

            daily = data.get("daily", [])
            if daily:
                _sep()
                _header("Additional features")
                for item in daily:
                    used  = item.get("used", 0)
                    total = item.get("total", 0)
                    note  = item.get("note") or ("You haven't used any yet" if used == 0 else "")
                    right = f"{used} / {total}" if total else f"{item['used_pct']}% used"
                    _row(item["label"], note, item["used_pct"], right)

        win.update_idletasks()
        w = win.winfo_reqwidth()
        h = win.winfo_reqheight()
        sw = win.winfo_screenwidth()
        sh = win.winfo_screenheight()
        win.geometry(f"{w}x{h}+{(sw - w) // 2}+{(sh - h) // 2}")

    def _rounded_rect(self, canvas, x1, y1, x2, y2, r, **kw):
        canvas.create_arc(x1,    y1,    x1+2*r, y1+2*r, start= 90, extent=90, style="pieslice", **kw)
        canvas.create_arc(x2-2*r,y1,    x2,     y1+2*r, start=  0, extent=90, style="pieslice", **kw)
        canvas.create_arc(x1,    y2-2*r,x1+2*r, y2,     start=180, extent=90, style="pieslice", **kw)
        canvas.create_arc(x2-2*r,y2-2*r,x2,     y2,     start=270, extent=90, style="pieslice", **kw)
        canvas.create_rectangle(x1+r, y1, x2-r, y2, **kw)
        canvas.create_rectangle(x1, y1+r, x2, y2-r, **kw)

    # ── Drag ─────────────────────────────────────────────────────────────────

    def _bind_resizable_drag(self, canvas):
        """Like _bind_drag, but corner zones resize the compact bar instead
        of moving the window. Used only by the compact canvas."""
        canvas.bind("<Motion>",          self._compact_motion)
        canvas.bind("<ButtonPress-1>",   self._compact_press)
        canvas.bind("<B1-Motion>",       self._compact_drag)
        canvas.bind("<ButtonRelease-1>", self._compact_release)
        canvas.bind("<Button-3>",        self._show_menu)

    def _compact_motion(self, e):
        corner = _corner_at(e.x, e.y, self._bar_w, self._bar_h)
        e.widget.configure(cursor=_CORNER_CURSOR.get(corner, ""))

    def _compact_press(self, e):
        self._drag_start_x = e.x_root
        self._drag_start_y = e.y_root
        self._win_start_x  = self._pos_x
        self._win_start_y  = self._pos_y
        self._dragging      = False

        corner = _corner_at(e.x, e.y, self._bar_w, self._bar_h)
        self._resize_corner = corner
        self._resizing       = corner is not None
        if self._resizing:
            self._resize_start_dims = (self._bar_w, self._bar_h)
            self._resize_start_pos  = (self._pos_x, self._pos_y)

    def _compact_drag(self, e):
        dx = e.x_root - self._drag_start_x
        dy = e.y_root - self._drag_start_y
        if abs(dx) > 3 or abs(dy) > 3:
            self._dragging = True
        if not self._dragging:
            return

        if self._resizing:
            sw, sh = self._resize_start_dims
            swx, swy = self._resize_start_pos
            self._bar_w, self._bar_h, self._pos_x, self._pos_y = _resize_dims(
                self._resize_corner, sw, sh, swx, swy, dx, dy)
            self._draw_compact_canvas(self._compact_canvas)
            self.win.geometry(
                f"{self._bar_w}x{self._bar_h}+{self._pos_x}+{self._pos_y}")
        else:
            self._pos_x = self._win_start_x + dx
            self._pos_y = self._win_start_y + dy
            self.win.geometry(f"+{self._pos_x}+{self._pos_y}")

    def _compact_release(self, e):
        if not self._dragging:
            self._toggle()
        elif not self._resizing:
            # Moved (not resized) — persist position, same as before.
            cfg = self.get_config()
            cfg["widget_x"] = self._pos_x
            cfg["widget_y"] = self._pos_y
            from config import save_config
            save_config(cfg)
        self._dragging = False
        self._resizing  = False
        self._resize_corner = None

    def _bind_drag(self, widget):
        widget.bind("<ButtonPress-1>",   self._drag_start)
        widget.bind("<B1-Motion>",       self._drag_motion)
        widget.bind("<ButtonRelease-1>", self._drag_end)
        # Right-click for menu on any draggable surface
        widget.bind("<Button-3>",        self._show_menu)

    def _drag_start(self, e):
        self._drag_start_x = e.x_root
        self._drag_start_y = e.y_root
        self._win_start_x  = self._pos_x
        self._win_start_y  = self._pos_y
        self._dragging     = False

    def _drag_motion(self, e):
        dx = e.x_root - self._drag_start_x
        dy = e.y_root - self._drag_start_y
        if abs(dx) > 3 or abs(dy) > 3:
            self._dragging = True
        if self._dragging:
            self._pos_x = self._win_start_x + dx
            self._pos_y = self._win_start_y + dy
            self.win.geometry(f"+{self._pos_x}+{self._pos_y}")

    def _drag_end(self, e):
        if not self._dragging:
            # It was a click, not a drag — toggle expand
            self._toggle()
        else:
            # Save final position to config so it persists after restart
            cfg = self.get_config()
            cfg["widget_x"] = self._pos_x
            cfg["widget_y"] = self._pos_y
            from config import save_config
            save_config(cfg)
        self._dragging = False

    # ── Click / Menu ─────────────────────────────────────────────────────────

    def _toggle(self):
        self.expanded = not self.expanded
        self._render()

    def _on_click(self, e=None):
        """Legacy — kept for close button in expanded view."""
        self._toggle()

    def _show_menu(self, e):
        menu = tk.Menu(self.win, tearoff=0, bg=BG2, fg=FG,
                       activebackground=BG3, activeforeground=FG,
                       font=("Segoe UI", 9))
        menu.add_command(label="Show Details",
                         command=self._show_details_window)
        menu.add_command(label="Settings",
                         command=lambda: threading.Thread(
                             target=self.on_settings, daemon=True).start())
        menu.add_separator()
        menu.add_command(label="Quit", command=self.on_quit)
        try:
            menu.tk_popup(e.x_root, e.y_root)
        finally:
            menu.grab_release()
