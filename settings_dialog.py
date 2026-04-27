"""
Settings dialog for configuring session key and thresholds.
"""

import tkinter as tk
from tkinter import ttk, messagebox
import webbrowser
import threading
from config import save_config

BG = "#1a1a1a"
BG2 = "#252525"
BG3 = "#2e2e2e"
FG = "#e0e0e0"
FG_DIM = "#888888"
ACCENT = "#4a90d9"
GREEN = "#3ab56b"


def show_settings(config: dict, parent=None):
    win = tk.Toplevel(parent) if parent else tk.Tk()
    win.title("Claude Usage Tracker — Settings")
    win.configure(bg=BG)
    win.resizable(False, False)
    win.attributes("-topmost", True)

    w, h = 520, 500
    win.update_idletasks()
    sw = win.winfo_screenwidth()
    sh = win.winfo_screenheight()
    win.geometry(f"{w}x{h}+{(sw-w)//2}+{(sh-h)//2}")

    # ─── Session Key ────────────────────────────────────────────────────────
    _section(win, "Session Key", pady_top=16)

    key_var = tk.StringVar(value=config.get("session_key", ""))

    # ── Extension install card ──────────────────────────────────────────────
    ext_frame = tk.Frame(win, bg=BG3, padx=14, pady=10)
    ext_frame.pack(fill="x", padx=20, pady=(4, 0))

    ext_info = tk.Frame(ext_frame, bg=BG3)
    ext_info.pack(side="left", fill="x", expand=True)

    tk.Label(ext_info, text="Recommended: Install the browser extension",
             bg=BG3, fg=FG, font=("Segoe UI", 9, "bold"), anchor="w").pack(anchor="w")
    tk.Label(ext_info,
             text="Auto-sends your key to this app whenever it changes. One-time setup.",
             bg=BG3, fg=FG_DIM, font=("Segoe UI", 8), anchor="w", wraplength=300).pack(anchor="w", pady=(2, 0))

    def open_extension_guide():
        import os, subprocess
        ext_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "extension"))
        msg = (
            "3-step setup:\n\n"
            "1. Open your browser's Extensions page:\n"
            "   Comet:  comet://extensions\n"
            "   Edge:   edge://extensions\n"
            "   Chrome: chrome://extensions\n\n"
            "2. Enable 'Developer mode' (toggle, top-right)\n\n"
            "3. Click 'Load unpacked' → select this folder:\n"
            f"   {ext_path}\n\n"
            "Done — the app gets your session key automatically from now on."
        )
        messagebox.showinfo("Install Extension", msg, parent=win)
        # Open extension folder in Explorer
        os.startfile(ext_path)
        # Try to open Comet's extensions page directly
        try:
            subprocess.Popen(["cmd", "/c", "start", "comet://extensions"])
        except Exception:
            pass

    tk.Button(ext_frame, text="How to install →", command=open_extension_guide,
              bg=ACCENT, fg="white", relief="flat", font=("Segoe UI", 9, "bold"),
              padx=10, pady=4, cursor="hand2", activebackground="#357abd").pack(side="right")

    # ── Auto-detect fallback ────────────────────────────────────────────────
    auto_frame = tk.Frame(win, bg=BG)
    auto_frame.pack(fill="x", padx=20, pady=(8, 0))

    status_var = tk.StringVar(value="")
    status_label = tk.Label(auto_frame, textvariable=status_var, bg=BG, fg=FG_DIM,
                            font=("Segoe UI", 8), justify="left", anchor="w", wraplength=360)
    status_label.pack(side="left", fill="x", expand=True)

    def do_auto_detect():
        detect_btn.config(state="disabled", text="Detecting…")
        status_var.set("Searching browsers…")
        status_label.config(fg=FG_DIM)

        def _detect():
            from cookie_reader import get_session_key
            key, browser = get_session_key()
            if key:
                key_var.set(key)
                status_var.set(f"Found in {browser}  ✓")
                status_label.config(fg=GREEN)
            else:
                status_var.set("Not found in browser cookies. Use the extension above.")
                status_label.config(fg="#dc3232")
            detect_btn.config(state="normal", text="Try auto-detect")

        threading.Thread(target=_detect, daemon=True).start()

    detect_btn = tk.Button(auto_frame, text="Try auto-detect",
                           command=do_auto_detect, bg=BG2, fg=FG_DIM,
                           relief="flat", font=("Segoe UI", 9),
                           padx=10, pady=3, cursor="hand2")
    detect_btn.pack(side="right")

    # Manual entry
    manual_frame = tk.Frame(win, bg=BG)
    manual_frame.pack(fill="x", padx=20, pady=(8, 0))

    tk.Label(manual_frame, text="Or paste manually:", bg=BG, fg=FG_DIM,
             font=("Segoe UI", 8)).pack(anchor="w")

    key_entry = tk.Entry(manual_frame, textvariable=key_var, show="•",
                         bg=BG2, fg=FG, insertbackground=FG,
                         relief="flat", font=("Segoe UI Mono", 9),
                         width=62)
    key_entry.pack(fill="x", pady=4, ipady=6)

    bottom_row = tk.Frame(manual_frame, bg=BG)
    bottom_row.pack(fill="x")

    show_var = tk.BooleanVar(value=False)

    def toggle_show():
        key_entry.config(show="" if show_var.get() else "•")

    tk.Checkbutton(bottom_row, text="Show key", variable=show_var, command=toggle_show,
                   bg=BG, fg=FG_DIM, selectcolor=BG2, activebackground=BG,
                   font=("Segoe UI", 8)).pack(side="left")

    link = tk.Label(bottom_row, text="Open claude.ai →", bg=BG, fg=ACCENT,
                    font=("Segoe UI", 8, "underline"), cursor="hand2")
    link.pack(side="right")
    link.bind("<Button-1>", lambda e: webbrowser.open("https://claude.ai/settings"))

    # ─── Thresholds ─────────────────────────────────────────────────────────
    _section(win, "Alert Thresholds", pady_top=14)

    thresh_frame = tk.Frame(win, bg=BG)
    thresh_frame.pack(fill="x", padx=20, pady=4)

    warn_var = tk.IntVar(value=config.get("warning_threshold", 70))
    crit_var = tk.IntVar(value=config.get("critical_threshold", 85))

    _slider_row(thresh_frame, "Warning (yellow)", warn_var, 0, 100, ACCENT)
    _slider_row(thresh_frame, "Critical  (red)", crit_var, 0, 100, "#dc3232")

    # ─── Refresh Interval ───────────────────────────────────────────────────
    _section(win, "Refresh Interval", pady_top=8)

    interval_frame = tk.Frame(win, bg=BG)
    interval_frame.pack(fill="x", padx=20)

    interval_var = tk.IntVar(value=config.get("refresh_interval", 60))
    _slider_row(interval_frame, "Seconds between refreshes", interval_var, 15, 300, FG_DIM)

    # ─── Buttons ────────────────────────────────────────────────────────────
    btn_frame = tk.Frame(win, bg=BG, pady=16)
    btn_frame.pack(side="bottom", fill="x")

    def on_save():
        new_cfg = {
            **config,
            "session_key": key_var.get().strip(),
            "warning_threshold": warn_var.get(),
            "critical_threshold": crit_var.get(),
            "refresh_interval": interval_var.get(),
        }
        save_config(new_cfg)
        config.update(new_cfg)
        messagebox.showinfo("Saved", "Settings saved. Changes take effect on next refresh.",
                            parent=win)
        win.destroy()

    tk.Button(btn_frame, text="Save", command=on_save, bg=ACCENT, fg="white",
              relief="flat", font=("Segoe UI", 10, "bold"), padx=20, pady=6,
              cursor="hand2", activebackground="#357abd").pack(side="right", padx=20)

    tk.Button(btn_frame, text="Cancel", command=win.destroy, bg=BG2, fg=FG_DIM,
              relief="flat", font=("Segoe UI", 10), padx=16, pady=6,
              cursor="hand2").pack(side="right")

    win.mainloop()
    return config


def _section(parent, text, pady_top=12):
    tk.Label(parent, text=text, font=("Segoe UI", 10, "bold"),
             bg=BG, fg=FG, anchor="w").pack(fill="x", padx=20, pady=(pady_top, 2))
    ttk.Separator(parent, orient="horizontal").pack(fill="x", padx=20, pady=2)


def _slider_row(parent, label, var, from_, to, color):
    row = tk.Frame(parent, bg=BG)
    row.pack(fill="x", pady=4)

    tk.Label(row, text=label, bg=BG, fg=FG_DIM, font=("Segoe UI", 9),
             width=28, anchor="w").pack(side="left")

    val_label = tk.Label(row, text=str(var.get()), bg=BG, fg=color,
                         font=("Segoe UI", 9, "bold"), width=4)
    val_label.pack(side="right")

    slider = tk.Scale(row, from_=from_, to=to, orient="horizontal", variable=var,
                      bg=BG, fg=FG_DIM, troughcolor=BG2, activebackground=color,
                      highlightthickness=0, length=220, showvalue=False,
                      command=lambda v: val_label.config(text=str(int(float(v)))))
    slider.pack(side="right", padx=8)
