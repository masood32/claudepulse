"""
Reads the Claude sessionKey cookie from installed browsers.
Supports Chrome, Edge, Firefox, Brave, Opera, and Comet (Perplexity).
Falls back gracefully when browsers are running (locked database).
"""

import os
import shutil
import sqlite3
import json
import base64
import tempfile
import glob

# ── Chromium cookie decryption ───────────────────────────────────────────────

def _get_chromium_key(local_state_path: str) -> bytes | None:
    try:
        with open(local_state_path, "r", encoding="utf-8") as f:
            state = json.load(f)
        b64 = state["os_crypt"]["encrypted_key"]
        encrypted = base64.b64decode(b64)[5:]  # Strip "DPAPI" prefix
        import win32crypt
        return win32crypt.CryptUnprotectData(encrypted, None, None, None, 0)[1]
    except Exception:
        return None


def _decrypt_cookie(value: bytes, key: bytes) -> str | None:
    if not value:
        return None
    try:
        from Cryptodome.Cipher import AES
        # v10/v11 prefix: 3 bytes version + 12 bytes nonce
        if value[:3] in (b"v10", b"v11"):
            nonce = value[3:15]
            payload = value[15:]
            cipher = AES.new(key, AES.MODE_GCM, nonce=nonce)
            return cipher.decrypt(payload[:-16]).decode("utf-8")
    except Exception:
        pass
    # Legacy DPAPI-encrypted cookie (no v10 prefix)
    try:
        import win32crypt
        return win32crypt.CryptUnprotectData(value, None, None, None, 0)[1].decode("utf-8")
    except Exception:
        return None


def _read_chromium_cookies(profile_dir: str, local_state_path: str) -> list[tuple[str, str]]:
    """Returns list of (name, value) for all cookies from this Chromium profile."""
    db_path = os.path.join(profile_dir, "Network", "Cookies")
    if not os.path.exists(db_path):
        db_path = os.path.join(profile_dir, "Cookies")
    if not os.path.exists(db_path):
        return []

    key = _get_chromium_key(local_state_path)

    tmp_fd, tmp = tempfile.mkstemp(suffix=".db")
    os.close(tmp_fd)
    try:
        shutil.copy2(db_path, tmp)
    except OSError:
        return []  # Browser is running with exclusive lock, or file vanished mid-read

    results = []
    try:
        conn = sqlite3.connect(tmp)
        rows = conn.execute(
            "SELECT name, encrypted_value FROM cookies "
            "WHERE host_key LIKE '%claude.ai%'"
        ).fetchall()
        conn.close()
        for name, enc_val in rows:
            val = _decrypt_cookie(enc_val, key) if key else None
            if val:
                results.append((name, val))
    except Exception:
        pass
    finally:
        try:
            os.unlink(tmp)
        except Exception:
            pass

    return results


# ── Browser profile locations ────────────────────────────────────────────────

def _chromium_profiles() -> list[tuple[str, str, str]]:
    """
    Returns list of (browser_name, profile_dir, local_state_path).
    Checks all known Chromium-based browsers on Windows.
    """
    local = os.path.expandvars("%LOCALAPPDATA%")
    roaming = os.path.expandvars("%APPDATA%")

    candidates = [
        ("Chrome",          os.path.join(local,   "Google", "Chrome", "User Data")),
        ("Edge",            os.path.join(local,   "Microsoft", "Edge", "User Data")),
        ("Brave",           os.path.join(local,   "BraveSoftware", "Brave-Browser", "User Data")),
        ("Opera",           os.path.join(roaming, "Opera Software", "Opera Stable")),
        ("Comet",           os.path.join(local,   "Perplexity", "Comet", "User Data")),
        ("Vivaldi",         os.path.join(local,   "Vivaldi", "User Data")),
        ("Arc",             os.path.join(local,   "Arc", "User Data")),
    ]

    results = []
    for name, user_data in candidates:
        if not os.path.isdir(user_data):
            continue
        local_state = os.path.join(user_data, "Local State")
        # Default profile
        default = os.path.join(user_data, "Default")
        if os.path.isdir(default):
            results.append((name, default, local_state))
        # Additional numbered profiles (Profile 1, Profile 2, …)
        for extra in glob.glob(os.path.join(user_data, "Profile *")):
            if os.path.isdir(extra):
                results.append((f"{name} ({os.path.basename(extra)})", extra, local_state))

    return results


def _firefox_profiles() -> list[tuple[str, str]]:
    """Returns list of (profile_name, cookies_sqlite_path) for Firefox."""
    base = os.path.expandvars(r"%APPDATA%\Mozilla\Firefox\Profiles")
    if not os.path.isdir(base):
        return []
    results = []
    for profile in os.listdir(base):
        db = os.path.join(base, profile, "cookies.sqlite")
        if os.path.exists(db):
            results.append(("Firefox", db))
    return results


def _read_firefox_cookie(db_path: str) -> str | None:
    tmp_fd, tmp = tempfile.mkstemp(suffix=".db")
    os.close(tmp_fd)
    try:
        shutil.copy2(db_path, tmp)
    except OSError:
        # Try immutable open while Firefox is running, or file vanished mid-read
        try:
            conn = sqlite3.connect(f"file:{db_path}?immutable=1", uri=True)
        except Exception:
            return None
    else:
        conn = sqlite3.connect(tmp)

    try:
        row = conn.execute(
            "SELECT value FROM moz_cookies WHERE name='sessionKey' AND host LIKE '%claude.ai%'"
        ).fetchone()
        conn.close()
        return row[0] if row else None
    except Exception:
        return None
    finally:
        try:
            os.unlink(tmp)
        except Exception:
            pass


# ── Public API ───────────────────────────────────────────────────────────────

def get_session_key() -> tuple[str, str] | tuple[None, None]:
    """
    Returns (session_key, browser_name) or (None, None) if not found.
    Tries Comet first (most likely), then other Chromium browsers, then Firefox.
    """
    # Comet first (user's browser), then others
    priority = ["Comet", "Edge", "Chrome", "Brave", "Vivaldi", "Opera", "Arc"]
    profiles = _chromium_profiles()
    profiles.sort(key=lambda x: priority.index(x[0].split(" ")[0])
                  if x[0].split(" ")[0] in priority else 99)

    for browser_name, profile_dir, local_state in profiles:
        cookies = _read_chromium_cookies(profile_dir, local_state)
        for name, value in cookies:
            if name == "sessionKey" and value:
                return value, browser_name

    # Firefox fallback
    for browser_name, db_path in _firefox_profiles():
        val = _read_firefox_cookie(db_path)
        if val:
            return val, browser_name

    return None, None
