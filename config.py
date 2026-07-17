import json
import os

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.json")

DEFAULTS = {
    "session_key": "",
    "refresh_interval": 60,
    "warning_threshold": 70,
    "critical_threshold": 85,
    "primary_metric": "session",
}


def load_config():
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH) as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            return DEFAULTS.copy()
        for k, v in DEFAULTS.items():
            data.setdefault(k, v)
        return data
    return DEFAULTS.copy()


def save_config(cfg):
    tmp_path = CONFIG_PATH + ".tmp"
    with open(tmp_path, "w") as f:
        json.dump(cfg, f, indent=2)
    os.replace(tmp_path, CONFIG_PATH)
