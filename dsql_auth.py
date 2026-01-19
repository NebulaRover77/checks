# dsql_auth.py
import json, time, os
import keyring
from keyring.errors import KeyringError

# ---- Tunables (env-overridable) ----
TOKEN_TTL = int(os.getenv("DSQL_TOKEN_TTL", str(15 * 60)))  # seconds
TOKEN_SAFETY = int(os.getenv("DSQL_TOKEN_SAFETY", "60"))    # refresh N sec early
KEYRING_SERVICE = os.getenv("DSQL_KEYRING_SERVICE", "checks-app-dsql")

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
    try:
        item = keyring.get_password(KEYRING_SERVICE, _token_key(host, db_user, region))
    except KeyringError:
        item = None

    if not item:
        return None
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
    return None

def _save_mem(host, db_user, region, token):
    _MEM_CACHE[(host, db_user, region)] = {"token": token, "exp": _now() + TOKEN_TTL}

def save_cached_token(host, db_user, region, token) -> bool:
    payload = {"token": token, "exp": _now() + TOKEN_TTL}
    secret = json.dumps(payload)

    # always update memory cache
    _save_mem(host, db_user, region, token)

    # write to Keychain with verification
    key = _token_key(host, db_user, region)
    try:
        keyring.set_password(KEYRING_SERVICE, key, secret)  # None on success
        roundtrip = keyring.get_password(KEYRING_SERVICE, key)
        if roundtrip != secret:
            raise KeyringError("Round-trip verification failed")
        return True
    except KeyringError:
        return False

def clear_cached_token(host, db_user, region):
    """Best-effort purge from mem + keyring (handy for debugging)."""
    _MEM_CACHE.pop((host, db_user, region), None)
    try:
        keyring.delete_password(KEYRING_SERVICE, _token_key(host, db_user, region))
    except KeyringError:
        pass

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
