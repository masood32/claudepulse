"""
Claude Usage Tracker
Floating always-on-top widget + system tray background process.
"""

import sys
import threading
import time
import socket

import pystray
from pystray import MenuItem as Item, Menu

from config import load_config, save_config
from fetcher import fetch_usage_data, demo_data
from icon_builder import build_icon
from cookie_reader import get_session_key
from floating_widget import FloatingWidget
import key_server

# ── Single-instance lock ─────────────────────────────────────────────────────
_LOCK_PORT = 47291

def _acquire_instance_lock():
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 0)
    try:
        sock.bind(("127.0.0.1", _LOCK_PORT))
        return sock
    except OSError:
        print("Already running.")
        sys.exit(0)


class ClaudeUsageTracker:
    def __init__(self):
        self.config = load_config()
        self.usage_data = None
        self.last_update: float | None = None
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._auto_detected_browser: str | None = None
        self._widget: FloatingWidget | None = None
        self._tray_icon: pystray.Icon | None = None
        self._ensure_session_key()

    # ── Session key ──────────────────────────────────────────────────────────

    def _ensure_session_key(self):
        if self.config.get("session_key", "").strip():
            return
        key, browser = get_session_key()
        if key:
            self.config["session_key"] = key
            self._auto_detected_browser = browser
            save_config(self.config)
            print(f"[auto] Found sessionKey in {browser}")
        else:
            print("[auto] No sessionKey — demo mode")

    def _re_detect_session_key(self) -> str:
        key, browser = get_session_key()
        if key:
            self._auto_detected_browser = browser
            self.config["session_key"] = key
            save_config(self.config)
        return self.config.get("session_key", "")

    # ── Data fetching ────────────────────────────────────────────────────────

    def _do_refresh(self):
        session_key = self.config.get("session_key", "").strip()
        try:
            if session_key:
                result = fetch_usage_data(session_key)
                if result is None:
                    session_key = self._re_detect_session_key()
                    result = fetch_usage_data(session_key) if session_key else None
                if result is None:
                    result = demo_data()
                    result["_api_error"] = True
            else:
                self._ensure_session_key()
                session_key = self.config.get("session_key", "").strip()
                result = fetch_usage_data(session_key) if session_key else demo_data()

            with self._lock:
                self.usage_data = result
            self.last_update = time.time()
            self._on_data_updated()
        except Exception as e:
            print(f"[refresh] {e}")

    def _refresh_loop(self):
        self._do_refresh()
        while not self._stop.wait(self.config.get("refresh_interval", 60)):
            self._do_refresh()

    def _on_data_updated(self):
        """Called after usage_data changes — update tray icon and widget."""
        with self._lock:
            data = self.usage_data

        # Update tray icon
        pct, err = self._primary_pct(data)
        warn = self.config.get("warning_threshold", 70)
        crit = self.config.get("critical_threshold", 85)
        img = build_icon(pct, warn, crit, error=err)
        if self._tray_icon:
            self._tray_icon.icon = img
            self._tray_icon.title = f"Claude  {pct}% used"

        # Update floating widget
        if self._widget:
            self._widget._last_update = self.last_update
            self._widget.refresh()

    def _primary_pct(self, data) -> tuple[int, bool]:
        if not data:
            return 0, True
        session = data.get("session")
        if session:
            return int(session.get("used_pct", 0)), False
        weekly = data.get("weekly", [])
        if weekly:
            return int(weekly[0].get("used_pct", 0)), False
        return 0, True

    # ── Extension callback ───────────────────────────────────────────────────

    def _on_key_from_extension(self, key: str, usage: dict | None):
        changed = False
        if key and key != self.config.get("session_key"):
            print(f"[ext] New sessionKey ({key[:12]}...)")
            self.config["session_key"] = key
            save_config(self.config)
            changed = True

        if usage is not None:
            from fetcher import _normalize
            with self._lock:
                self.usage_data = _normalize(usage)
            self.last_update = time.time()
            self._on_data_updated()
        elif changed:
            threading.Thread(target=self._do_refresh, daemon=True).start()

    # ── Settings / quit ──────────────────────────────────────────────────────

    def _open_settings(self, icon=None, item=None):
        if self._widget and self._widget.win:
            self._widget.win.after(0, self._open_settings_dialog)

    def _open_settings_dialog(self):
        from settings_dialog import show_settings
        show_settings(self.config, parent=self._widget.win if self._widget else None)
        self.config = load_config()
        self._do_refresh()

    def _quit(self, icon=None, item=None):
        self._stop.set()
        if self._tray_icon:
            self._tray_icon.stop()
        if self._widget and self._widget.win:
            self._widget.win.after(0, self._widget.win.destroy)

    # ── Run ──────────────────────────────────────────────────────────────────

    def run(self):
        # Start key receiver
        key_server.start(self._on_key_from_extension)

        # Start refresh loop
        threading.Thread(target=self._refresh_loop, daemon=True).start()

        # System tray (background, minimal)
        img = build_icon(0, error=True)
        menu = Menu(
            Item("Refresh", lambda i, it: threading.Thread(
                target=self._do_refresh, daemon=True).start()),
            Item("Settings", self._open_settings),
            Menu.SEPARATOR,
            Item("Quit", self._quit),
        )
        self._tray_icon = pystray.Icon("claude_usage", img, "Claude Usage Tracker", menu)
        threading.Thread(target=self._tray_icon.run, daemon=True).start()

        # Floating widget runs on main thread
        self._widget = FloatingWidget(
            get_data_fn    = lambda: self.usage_data,
            get_config_fn  = lambda: self.config,
            on_settings_fn = self._open_settings_dialog,
            on_quit_fn     = self._quit,
        )
        self._widget.start()   # blocks


if __name__ == "__main__":
    _lock_sock = _acquire_instance_lock()
    app = ClaudeUsageTracker()
    app.run()
