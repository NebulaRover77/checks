# configurations.py
from pathlib import Path
import json, os
from platformdirs import user_config_dir

_APP_NAME = "Checks"

def _config_dir() -> Path:
    return Path(user_config_dir(_APP_NAME))

def get_config_path() -> Path:
    """Public helper so other modules can show a friendly path in errors."""
    return _config_dir() / "config.json"

def load_cfg():
    cfg_path = get_config_path()
    cfg_path.parent.mkdir(parents=True, exist_ok=True)

    # Bootstrap empty file if missing
    if not cfg_path.exists():
        cfg_path.write_text("{}", encoding="utf-8")
        try:
            # Best-effort POSIX perms; harmless on Windows
            os.chmod(cfg_path, 0o600)
        except Exception:
            pass

    try:
        txt = cfg_path.read_text(encoding="utf-8") or "{}"
        return json.loads(txt)
    except Exception:
        # Corrupt file? return empty to keep callers resilient
        return {}

def save_cfg(cfg: dict):
    cfg_path = get_config_path()
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = cfg_path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(cfg, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(cfg_path)
    try:
        os.chmod(cfg_path, 0o600)
    except Exception:
        pass
