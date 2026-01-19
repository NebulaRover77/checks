# sso.py
import json, os, time, webbrowser
from pathlib import Path
from urllib.parse import quote_plus
import boto3
from botocore.session import get_session
from botocore.credentials import Credentials

import configurations

KEYRING_SERVICE = "checks-app-sso"
SKEW = 60  # seconds of safety around expirations
DEVICE_GRANT = "urn:ietf:params:oauth:grant-type:device_code"
REFRESH_GRANT = "refresh_token"
SSO_CACHE_BACKEND = os.getenv("SSO_CACHE_BACKEND", "file").strip().lower()
SSO_CACHE_FILENAME = os.getenv("SSO_CACHE_FILENAME", "sso_cache.json")

# populated at runtime by _register_client()
_register_cache = None

def _is_invalid_client(e: Exception) -> bool:
    # botocore-style
    resp = getattr(e, "response", None)
    if isinstance(resp, dict):
        code = resp.get("Error", {}).get("Code")
        if code == "InvalidClientException":
            return True
    # errorfactory-style / fallback
    if e.__class__.__name__ == "InvalidClientException":
        return True
    return "InvalidClientException" in str(e)

def _client_expired(client: dict, now: int) -> bool:
    exp = int(client.get("clientSecretExpiresAt", 0) or 0)
    return exp and (now + SKEW >= exp)

def _ensure_client(oidc, cache, cache_key, force: bool = False):
    global _register_cache
    now = int(time.time())

    client = None if force else cache.get("client")
    if (not client) or _client_expired(client, now):
        client = _register_client(oidc)
        cache["client"] = client
        # tokens are tied to the client; if we re-register, drop old tokens
        for k in ("accessToken","accessTokenExpiresAt","refreshToken","refreshTokenExpiresAt"):
            cache.pop(k, None)
        _save_cache(cache_key, cache)

    _register_cache = client
    return client

def _dbg(*a):
    if os.getenv("SSO_DEBUG"):
        print("[SSO]", *a)


def _norm_start_url(u: str) -> str:
    u = (u or "").strip()
    if u.endswith("/"):
        u = u[:-1]
    return u.lower()


def _cache_key(start_url, sso_region, account_id, role_name):
    return f"{_norm_start_url(start_url)}|{sso_region}|{account_id}|{role_name}"

def _cache_path() -> Path:
    override = os.getenv("SSO_CACHE_PATH")
    if override:
        return Path(override)
    settings_dir = os.getenv("SETTINGS_DIR")
    if settings_dir:
        return Path(settings_dir) / SSO_CACHE_FILENAME
    cfg_path = configurations.get_config_path()
    return cfg_path.with_name(SSO_CACHE_FILENAME)

def _cache_use_keyring() -> bool:
    return SSO_CACHE_BACKEND in ("keyring", "auto")

def _cache_use_file() -> bool:
    return SSO_CACHE_BACKEND in ("file", "auto")

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


def _keyring_client():
    import keyring
    import keyring.errors as ke

    return keyring, ke


def _load_cache(start_url, sso_region, account_id, role_name):
    key = _cache_key(start_url, sso_region, account_id, role_name)
    if _cache_use_keyring():
        keyring, ke = _keyring_client()
        try:
            raw = keyring.get_password(KEYRING_SERVICE, key)
        except ke.KeyringError as exc:
            _dbg("load_cache keyring failed:", exc)
            raw = None
        _dbg("load_cache", key, "present:", bool(raw))
        if raw:
            return (key, json.loads(raw))
    if _cache_use_file():
        data = _load_file_cache().get(key)
        _dbg("load_cache file present:", bool(data))
        if isinstance(data, dict):
            return (key, data)
    return (key, {})


def _save_cache(cache_key, data):
    payload = json.dumps(data)
    success = False
    if _cache_use_keyring():
        keyring, ke = _keyring_client()
        try:
            keyring.set_password(KEYRING_SERVICE, cache_key, payload)
            if keyring.get_password(KEYRING_SERVICE, cache_key) != payload:
                raise ke.KeyringError("Keychain round-trip verification failed")
            _dbg("save_cache ok:", cache_key)
            success = True
        except ke.KeyringError as e:
            _dbg("save_cache keyring FAILED:", e, "backend:", keyring.get_keyring())
    if _cache_use_file():
        file_cache = _load_file_cache()
        file_cache[cache_key] = data
        success = _write_file_cache(file_cache) or success
    return success


def _register_client(oidc):
    reg = oidc.register_client(
        clientName="checks-desktop-app",
        clientType="public",
        scopes=["sso:account:access"],
    )
    _dbg("register_client -> clientId:", reg["clientId"], "has clientSecret:", bool(reg.get("clientSecret")))
    return {
        "clientId": reg["clientId"],
        "clientSecret": reg.get("clientSecret"),
        "clientIdIssuedAt": reg.get("clientIdIssuedAt", 0),
        "clientSecretExpiresAt": reg.get("clientSecretExpiresAt", 0),
    }


def _create_token(oidc, *, client, grant_type, **kwargs):
    args = dict(clientId=client["clientId"], grantType=grant_type, **kwargs)
    if client.get("clientSecret"):
        args["clientSecret"] = client["clientSecret"]
    return oidc.create_token(**args)


def _start_device_authorization(oidc, start_url):
    return oidc.start_device_authorization(
        clientId=_register_cache["clientId"],
        clientSecret=_register_cache.get("clientSecret"),
        startUrl=_norm_start_url(start_url),
    )


def _device_flow(oidc, start_url, open_browser=True, poll_timeout_sec=300):
    auth = _start_device_authorization(oidc, start_url)
    user_code = auth["userCode"]
    verif_base = auth["verificationUri"]
    verif = auth.get("verificationUriComplete") or f"{verif_base}?user_code={quote_plus(user_code)}"

    if open_browser:
        try:
            webbrowser.open(verif, new=2)  # new tab if possible
            print(f"Opening sign-in page: {verif}")
        except Exception:
            print(f"Open this URL to sign in: {verif}")
    else:
        print(f"Open this URL to sign in: {verif}")
    print(f"Code: {user_code}")

    interval = auth.get("interval", 5)
    started = time.time()
    while True:
        try:
            tok = _create_token(
                oidc,
                client=_register_cache,
                grant_type=DEVICE_GRANT,
                deviceCode=auth["deviceCode"],
            )
            _dbg("device_flow token keys:", list(tok.keys()))
            return tok
        except oidc.exceptions.AuthorizationPendingException:
            if time.time() - started > poll_timeout_sec:
                raise TimeoutError("SSO device authorization timed out.")
            time.sleep(interval)
        except oidc.exceptions.SlowDownException:
            time.sleep(interval + 1)


def has_cached_access_token(start_url: str, sso_region: str, account_id: str, role_name: str) -> bool:
    cache_key, cache = _load_cache(start_url, sso_region, account_id, role_name)
    _dbg("has_cached_access_token", cache_key)
    now = int(time.time())
    access_token = cache.get("accessToken")
    access_exp = int(cache.get("accessTokenExpiresAt", 0))
    return bool(access_token and (now + SKEW < access_exp))


def start_device_authorization(start_url: str, sso_region: str, account_id: str, role_name: str) -> dict:
    start_url = _norm_start_url(start_url)
    oidc = boto3.client("sso-oidc", region_name=sso_region)
    cache_key, cache = _load_cache(start_url, sso_region, account_id, role_name)
    _ensure_client(oidc, cache, cache_key)
    auth = _start_device_authorization(oidc, start_url)
    return {
        "device_code": auth["deviceCode"],
        "user_code": auth["userCode"],
        "verification_uri": auth["verificationUri"],
        "verification_uri_complete": auth.get("verificationUriComplete"),
        "interval": auth.get("interval", 5),
        "expires_in": auth.get("expiresIn"),
    }


def poll_device_authorization(
    *,
    start_url: str,
    sso_region: str,
    account_id: str,
    role_name: str,
    device_code: str,
) -> dict:
    start_url = _norm_start_url(start_url)
    oidc = boto3.client("sso-oidc", region_name=sso_region)
    cache_key, cache = _load_cache(start_url, sso_region, account_id, role_name)
    _ensure_client(oidc, cache, cache_key)
    try:
        token = _create_token(
            oidc,
            client=_register_cache,
            grant_type=DEVICE_GRANT,
            deviceCode=device_code,
        )
    except oidc.exceptions.AuthorizationPendingException:
        return {"status": "pending"}
    except oidc.exceptions.SlowDownException:
        return {"status": "slow_down"}
    except oidc.exceptions.ExpiredTokenException:
        return {"status": "expired"}

    now = int(time.time())
    access_token = token["accessToken"]
    access_expires_in = int(token.get("expiresIn", 3600))
    cache["accessToken"] = access_token
    cache["accessTokenExpiresAt"] = now + access_expires_in

    refresh_token = token.get("refreshToken")
    if refresh_token:
        refresh_expires_in = int(token.get("refreshTokenExpiresIn", 0)) or (30 * 24 * 3600)
        cache["refreshToken"] = refresh_token
        cache["refreshTokenExpiresAt"] = now + refresh_expires_in
    else:
        cache.pop("refreshToken", None)
        cache.pop("refreshTokenExpiresAt", None)
        _dbg("No refreshToken returned; relying on cached accessToken lifetime")

    _save_cache(cache_key, cache)
    return {"status": "authorized"}


def sso_login_and_get_session(
    start_url: str,
    sso_region: str,
    account_id: str,
    role_name: str,
    aws_region: str,
    open_browser: bool = True,
):
    """
    Returns a boto3.Session authenticated for (account_id, role_name),
    using cached tokens (keyring or file-backed). Writes nothing to ~/.aws.

    Strategy:
      1) Reuse cached accessToken if still valid (no browser)
      2) Else, try refresh_token grant if we have a refreshToken
      3) Else, do device flow (auto-opens browser by default)
    """
    start_url = _norm_start_url(start_url)
    oidc = boto3.client("sso-oidc", region_name=sso_region)
    sso = boto3.client("sso", region_name=sso_region)

    cache_key, cache = _load_cache(start_url, sso_region, account_id, role_name)
    _ensure_client(oidc, cache, cache_key)

    now = int(time.time())
    access_token = cache.get("accessToken")
    access_exp = int(cache.get("accessTokenExpiresAt", 0))

    if access_token and (now + SKEW < access_exp):
        _dbg("using cached accessToken")
    else:
        token = None

        refresh = cache.get("refreshToken")
        refresh_exp = int(cache.get("refreshTokenExpiresAt", 0))
        if refresh and (now + SKEW < refresh_exp):
            try:
                token = _create_token(
                    oidc,
                    client=_register_cache,
                    grant_type=REFRESH_GRANT,
                    refreshToken=refresh,
                )
                _dbg("used refresh_token grant; keys:", list(token.keys()))
            except Exception as e:
                if _is_invalid_client(e):
                    _dbg("refresh grant invalid client; re-registering")
                    _ensure_client(oidc, cache, cache_key, force=True)
                    token = None
                else:
                    _dbg("refresh grant failed; falling back:", e)
                    token = None

        if token is None:
            try:
                token = _device_flow(oidc, start_url, open_browser=open_browser)
            except Exception as e:
                if _is_invalid_client(e):
                    _dbg("device flow invalid client; re-registering and retrying")
                    _ensure_client(oidc, cache, cache_key, force=True)
                    token = _device_flow(oidc, start_url, open_browser=open_browser)
                else:
                    raise

        # recompute now since device flow can take time
        now = int(time.time())
        access_token = token["accessToken"]
        access_expires_in = int(token.get("expiresIn", 3600))
        cache["accessToken"] = access_token
        cache["accessTokenExpiresAt"] = now + access_expires_in

        refresh_token = token.get("refreshToken")
        if refresh_token:
            refresh_expires_in = int(token.get("refreshTokenExpiresIn", 0)) or (30 * 24 * 3600)
            cache["refreshToken"] = refresh_token
            cache["refreshTokenExpiresAt"] = now + refresh_expires_in
        else:
            cache.pop("refreshToken", None)
            cache.pop("refreshTokenExpiresAt", None)
            _dbg("No refreshToken returned; relying on cached accessToken lifetime")

        _save_cache(cache_key, cache)

    role = sso.get_role_credentials(
        accessToken=access_token,
        accountId=account_id,
        roleName=role_name,
    )["roleCredentials"]

    creds = Credentials(
        access_key=role["accessKeyId"],
        secret_key=role["secretAccessKey"],
        token=role["sessionToken"],
    )
    bcs = get_session()
    bcs.set_credentials(creds.access_key, creds.secret_key, creds.token)
    return boto3.Session(botocore_session=bcs, region_name=aws_region)


def debug_dump_cache(start_url, sso_region, account_id, role_name):
    key = _cache_key(start_url, sso_region, account_id, role_name)
    data = None
    if _cache_use_keyring():
        keyring, _ = _keyring_client()
        raw = keyring.get_password(KEYRING_SERVICE, key)
        if raw:
            data = json.loads(raw)
    if data is None and _cache_use_file():
        data = _load_file_cache().get(key)
    print("Key:", key)
    print("Backend:", "keyring" if _cache_use_keyring() else "file")
    print("Present:", bool(data))
    if data:
        print("Has accessToken:", bool(data.get("accessToken")))
        if data.get("accessTokenExpiresAt"):
            print("Access expires in (s):", int(data["accessTokenExpiresAt"] - time.time()))
        print("Has refreshToken:", bool(data.get("refreshToken")))
        if data.get("refreshTokenExpiresAt"):
            print("Refresh expires in (s):", int(data["refreshTokenExpiresAt"] - time.time()))
