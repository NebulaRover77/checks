# dsql_auth.py
import json, time, os
from pathlib import Path

import keyring
from keyring.errors import KeyringError

import configurations

# ---- Tunables (env-overridable) ----
TOKEN_TTL = int(os.getenv("DSQL_TOKEN_TTL", str(15 * 60)))  # seconds
TOKEN_SAFETY = int(os.getenv("DSQL_TOKEN_SAFETY", "60"))    # refresh N sec early
KEYRING_SERVICE = os.getenv("DSQL_KEYRING_SERVICE", "checks-app-dsql")
CACHE_BACKEND = os.getenv("DSQL_CACHE_BACKEND", "auto").strip().lower()
CACHE_FILE_NAME = os.getenv("DSQL_CACHE_FILENAME", "dsql_token_cache.json")

# Simple in-process cache so the app keeps working even if Keychain is fussy
# { (host, user, region): {"token": "...", "exp": epoch_seconds} }
_MEM_CACHE = {}

def _debug() -> bool:
    return os.getenv("DSQL_DEBUG") not in (None, "", "0", "false", "False")

def _now() -> float:
    return time.time()

def _not_expired(exp: float) -> bool:
    return _now() < (exp - TOKEN_SAFETY)

def _token_key(host, db_user, region) -> str:
    return f"{host}|{db_user}|{region}"

def _cache_path() -> Path:
    override = os.getenv("DSQL_CACHE_PATH")
    if override:
        return Path(override)
    settings_dir = os.getenv("SETTINGS_DIR")
    if settings_dir:
        return Path(settings_dir) / CACHE_FILE_NAME
    cfg_path = configurations.get_config_path()
    return cfg_path.with_name(CACHE_FILE_NAME)

def _load_file_cache() -> dict:
    path = _cache_path()
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}

def _write_file_cache(data: dict) -> bool:
    path = _cache_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    try:
        tmp.write_text(json.dumps(data), encoding="utf-8")
        tmp.replace(path)
        return True
    except Exception:
        return False

def _cache_use_keyring() -> bool:
    return CACHE_BACKEND in ("keyring", "auto")

def _cache_use_file() -> bool:
    return CACHE_BACKEND in ("file", "auto")

def load_cached_token(host, db_user, region):
    k = (host, db_user, region)

    # 1) Memory cache
    m = _MEM_CACHE.get(k)
    if m and _not_expired(m["exp"]):
        if _debug():
            print("[DSQL] mem cache hit", host, db_user, region)
        return m["token"]
    elif m and not _not_expired(m["exp"]):
        # drop stale
        _MEM_CACHE.pop(k, None)

    # 2) Keyring
    if _cache_use_keyring():
        try:
            item = keyring.get_password(KEYRING_SERVICE, _token_key(host, db_user, region))
        except KeyringError:
            item = None

        if item:
            try:
                data = json.loads(item)
                if _not_expired(data.get("exp", 0)):
                    # refresh mem cache to avoid repeated keychain hits
                    _MEM_CACHE[k] = {"token": data["token"], "exp": data["exp"]}
                    if _debug():
                        print("[DSQL] keyring cache hit", host, db_user, region)
                    return data["token"]
            except Exception:
                pass

    # 3) File cache
    if _cache_use_file():
        payload = _load_file_cache().get(_token_key(host, db_user, region))
        if isinstance(payload, dict) and _not_expired(payload.get("exp", 0)):
            _MEM_CACHE[k] = {"token": payload["token"], "exp": payload["exp"]}
            if _debug():
                print("[DSQL] file cache hit", host, db_user, region)
            return payload["token"]

    return None

def _save_mem(host, db_user, region, token):
    _MEM_CACHE[(host, db_user, region)] = {"token": token, "exp": _now() + TOKEN_TTL}

def save_cached_token(host, db_user, region, token) -> bool:
    payload = {"token": token, "exp": _now() + TOKEN_TTL}
    secret = json.dumps(payload)

    # always update memory cache
    _save_mem(host, db_user, region, token)

    key = _token_key(host, db_user, region)
    success = False

    # write to Keychain with verification
    if _cache_use_keyring():
        try:
            keyring.set_password(KEYRING_SERVICE, key, secret)  # None on success
            roundtrip = keyring.get_password(KEYRING_SERVICE, key)
            if roundtrip != secret:
                raise KeyringError("Round-trip verification failed")
            success = True
        except KeyringError:
            success = False

    # fall back to file cache
    if _cache_use_file():
        data = _load_file_cache()
        data[key] = payload
        success = _write_file_cache(data) or success

    return success

def clear_cached_token(host, db_user, region):
    """Best-effort purge from mem + keyring (handy for debugging)."""
    _MEM_CACHE.pop((host, db_user, region), None)
    key = _token_key(host, db_user, region)
    if _cache_use_keyring():
        try:
            keyring.delete_password(KEYRING_SERVICE, key)
        except KeyringError:
            pass
    if _cache_use_file():
        data = _load_file_cache()
        if key in data:
            data.pop(key, None)
            _write_file_cache(data)

def get_dsql_token(session, host, db_user, region):
    # 1) Try caches
    cached = load_cached_token(host, db_user, region)
    if cached:
        return cached

    # 2) Mint new token via DSQL
    dsql = session.client("dsql", region_name=region)
    if str(db_user).lower() == "admin":
        token = dsql.generate_db_connect_admin_auth_token(Hostname=host, Region=region)
    else:
        token = dsql.generate_db_connect_auth_token(Hostname=host, Region=region)

    # 3) Save (best-effort) then return
    save_cached_token(host, db_user, region, token)
    if _debug():
        print("[DSQL] minted NEW token", host, db_user, region)
    return token
