"""
Fetches Claude.ai usage data using curl_cffi to impersonate Chrome's TLS fingerprint,
bypassing Cloudflare bot detection.

Real API:
  GET /api/account                          → returns org uuid
  GET /api/organizations/{org_uuid}/usage   → returns usage limits
"""

from curl_cffi import requests as cf_requests
from datetime import datetime, timezone
import json

HEADERS = {
    "Accept": "application/json",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://claude.ai/settings",
    "anthropic-client-type": "web",
}


def _session(session_key: str) -> cf_requests.Session:
    s = cf_requests.Session(impersonate="chrome124")
    s.cookies.set("sessionKey", session_key, domain="claude.ai")
    s.headers.update(HEADERS)
    return s


def _get_org_uuid(session_key: str) -> str | None:
    try:
        s = _session(session_key)
        r = s.get("https://claude.ai/api/account", timeout=10)
        if r.status_code == 200:
            memberships = r.json().get("memberships", [])
            if memberships:
                return memberships[0]["organization"]["uuid"]
    except Exception:
        pass
    return None


def _resets_in(resets_at_str: str) -> str:
    """Convert ISO timestamp to human-readable 'Xh Ym' string."""
    try:
        ts = datetime.fromisoformat(resets_at_str.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        delta = int((ts - now).total_seconds())
        if delta <= 0:
            return "soon"
        h = delta // 3600
        m = (delta % 3600) // 60
        return f"{h}h {m}m" if h else f"{m}m"
    except Exception:
        return ""


def _normalize_real(raw: dict) -> dict:
    """Convert the real API response into our standard display format."""
    result = {"plan": "Pro", "session": None, "weekly": [], "daily": []}

    five_hour = raw.get("five_hour")
    if five_hour and five_hour.get("utilization") is not None:
        result["session"] = {
            "label": "Current session",
            "used_pct": round(five_hour["utilization"]),
            "resets_in": _resets_in(five_hour.get("resets_at", "")),
        }

    seven_day = raw.get("seven_day")
    if seven_day and seven_day.get("utilization") is not None:
        result["weekly"].append({
            "label": "All models",
            "used_pct": round(seven_day["utilization"]),
            "resets_in": _resets_in(seven_day.get("resets_at", "")),
        })

    # Named model buckets → weekly
    MODEL_LABELS = {
        "seven_day_opus":     "Claude Opus",
        "seven_day_sonnet":   "Claude Sonnet",
        "seven_day_omelette": "Claude Design",
        "seven_day_cowork":   "Claude Cowork",
    }
    for key, label in MODEL_LABELS.items():
        bucket = raw.get(key)
        if bucket and bucket.get("utilization") is not None:
            result["weekly"].append({
                "label": label,
                "used_pct": round(bucket["utilization"]),
                "resets_in": _resets_in(bucket.get("resets_at", "")),
            })

    # Extra (paid) usage credits
    extra = raw.get("extra_usage")
    if extra and extra.get("is_enabled"):
        used = extra.get("used_credits", 0)
        limit = extra.get("monthly_limit", 0)
        pct = round(extra.get("utilization") or 0)
        result["daily"].append({
            "label": "Extra credits",
            "used": round(used),
            "total": limit,
            "used_pct": pct,
            "note": f"${used:.0f} / ${limit:.0f} used this month",
        })

    return result


# Cache org UUID so we don't hit /api/account every refresh
_cached_org_uuid: str | None = None


def fetch_usage_data(session_key: str) -> dict | None:
    global _cached_org_uuid

    if not session_key:
        return None

    try:
        if not _cached_org_uuid:
            _cached_org_uuid = _get_org_uuid(session_key)
        if not _cached_org_uuid:
            return None

        s = _session(session_key)
        url = f"https://claude.ai/api/organizations/{_cached_org_uuid}/usage"
        r = s.get(url, timeout=10)

        if r.status_code == 401:
            _cached_org_uuid = None  # Session expired
            return None
        if r.status_code == 200:
            return _normalize_real(r.json())
    except Exception as e:
        print(f"[fetcher] {e}")

    return None


def _normalize(raw: dict) -> dict:
    """Normalize unknown API response shape — used when extension sends raw data."""
    # Check if it matches our known real API format
    if "five_hour" in raw or "seven_day" in raw:
        return _normalize_real(raw)

    # Legacy / unknown shape fallback
    result = {"plan": raw.get("plan", "Pro"), "session": None, "weekly": [], "daily": []}

    if "limits" in raw and isinstance(raw["limits"], list):
        for lim in raw["limits"]:
            ltype = lim.get("type", "")
            pct = round(lim.get("used_pct") or lim.get("utilization") or 0)
            resets = lim.get("resets_in", "")
            label = lim.get("label", lim.get("name", ltype))
            if ltype in ("session", "current", "five_hour"):
                result["session"] = {"label": label, "used_pct": pct, "resets_in": resets}
            else:
                result["weekly"].append({"label": label, "used_pct": pct, "resets_in": resets})

    return result


def demo_data() -> dict:
    return {
        "plan": "Pro",
        "session": {"label": "Current session", "used_pct": 25, "resets_in": "4h 17m"},
        "weekly": [
            {"label": "All models",    "used_pct": 23, "resets_in": "6h 57m"},
            {"label": "Claude Design", "used_pct": 32, "resets_in": "6h 57m"},
        ],
        "daily": [],
    }
