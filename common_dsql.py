# common_dsql.py
from __future__ import annotations
from typing import Optional, Tuple
import os

from psycopg2 import connect as _pg_connect
from psycopg2.extras import RealDictCursor

import configurations
import dsql_auth
import sso


# ------- settings helpers (no baked defaults) -------
_REQUIRED_KEYS = (
    "START_URL",
    "SSO_REGION",
    "ACCOUNT_ID",
    "ROLE_NAME",
    "AWS_REGION",
    "DB_NAME",
    "DB_USER",
    "TAG_KEY",
    "TAG_VALUE",
)

def _config_path_str() -> str:
    try:
        return str(configurations.get_config_path())
    except Exception:
        return "<user config file>"

def _require(key: str) -> str:
    """Return key from env or user config; raise if missing."""
    v = os.environ.get(key)
    if v not in (None, ""):
        return v
    cfg = configurations.load_cfg()
    v = cfg.get(key)
    if isinstance(v, str) and v:
        return v
    raise RuntimeError(
        f"Missing required setting {key}. Set it as an environment variable "
        f"or add it to { _config_path_str() }."
    )

def _is_debug() -> bool:
    return os.environ.get("DSQL_DEBUG") not in (None, "", "0", "false", "False")

def _truthy_env(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() not in ("0", "false", "no", "")

def _cfg_namespace(account_id: Optional[str] = None, region: Optional[str] = None) -> str:
    """Namespace for cached items in config.json (ACCOUNT_ID:AWS_REGION)."""
    aid = account_id or _require("ACCOUNT_ID")
    reg = region or _require("AWS_REGION")
    return f"{aid}:{reg}"


# ---------- tiny helpers ----------
def _db_host_from_id(db_id: str, region: str) -> str:
    return f"{db_id}.dsql.{region}.on.aws"

def _load_cached_db_id(*, account_id: Optional[str] = None, region: Optional[str] = None) -> Optional[str]:
    cfg = configurations.load_cfg()
    return cfg.get(_cfg_namespace(account_id, region), {}).get("db_id")

def _save_cached_db_id(db_id: str, *, account_id: Optional[str] = None, region: Optional[str] = None) -> None:
    cfg = configurations.load_cfg()
    cfg.setdefault(_cfg_namespace(account_id, region), {})["db_id"] = db_id
    configurations.save_cfg(cfg)

def _best_effort_db_id(*, account_id: Optional[str] = None, region: Optional[str] = None) -> Optional[str]:
    return os.environ.get("DB_ID") or _load_cached_db_id(account_id=account_id, region=region)

def _best_effort_db_host(*, region: str) -> Optional[str]:
    env_host = os.environ.get("DB_HOST")
    if env_host:
        return env_host
    dbid = _best_effort_db_id(region=region)
    return _db_host_from_id(dbid, region) if dbid else None


# ---------- public API ----------
def resolve_db_id_by_tag(
    session,
    *,
    region: Optional[str] = None,
    tag_key: Optional[str] = None,
    tag_value: Optional[str] = None,
) -> str:
    """
    Scan Aurora DSQL clusters and return the single identifier
    whose tag matches key=value.
    """
    region = region or _require("AWS_REGION")
    tag_key = tag_key or _require("TAG_KEY")
    tag_value = tag_value or _require("TAG_VALUE")

    dsql_client = session.client("dsql", region_name=region)

    clusters, token = [], None
    while True:
        page = dsql_client.list_clusters(**({"nextToken": token} if token else {}))
        clusters.extend(page.get("clusters", []))
        token = page.get("nextToken")
        if not token:
            break
    if not clusters:
        raise RuntimeError("No Aurora DSQL clusters found in this account/region.")

    matches = []
    for c in clusters:
        arn = c["arn"]
        tags = dsql_client.list_tags_for_resource(resourceArn=arn)["tags"]  # dict[str,str]
        if tags.get(tag_key) == tag_value:
            matches.append(c)

    if not matches:
        raise RuntimeError(f"No DSQL cluster has tag {tag_key}={tag_value!r}.")
    if len(matches) > 1:
        ids = ", ".join(m["identifier"] for m in matches)
        raise RuntimeError(f"Tag {tag_key}={tag_value!r} matched multiple clusters: {ids}")

    return matches[0]["identifier"]


def sso_login_session(
    *,
    start_url: Optional[str] = None,
    sso_region: Optional[str] = None,
    account_id: Optional[str] = None,
    role_name: Optional[str] = None,
    aws_region: Optional[str] = None,
    open_browser: Optional[bool] = None,
):
    """Thin wrapper around your sso.sso_login_and_get_session for consistency."""
    return sso.sso_login_and_get_session(
        start_url=start_url or _require("START_URL"),
        sso_region=sso_region or _require("SSO_REGION"),
        account_id=account_id or _require("ACCOUNT_ID"),
        role_name=role_name or _require("ROLE_NAME"),
        aws_region=aws_region or _require("AWS_REGION"),
        # default: open browser unless explicitly disabled via env or arg
        open_browser=_truthy_env("SSO_OPEN_BROWSER", True) if open_browser is None else open_browser,
    )


def get_token_and_host(
    user: str,
    *,
    region: Optional[str] = None,
    force_refresh: bool = False,
    host_override: Optional[str] = None,
    dbid_override: Optional[str] = None,
    tag_override: Optional[Tuple[str, str]] = None,
) -> Tuple[str, str]:
    """
    Returns (token, host). Respects env/overrides, cached token, and resolves by tag if needed.
    """
    region = region or _require("AWS_REGION")

    # Prefer explicit overrides/env
    host = host_override or _best_effort_db_host(region=region)
    dbid = dbid_override or _best_effort_db_id(region=region)

    # Try cached token first unless told to force refresh
    if host and not force_refresh:
        cached = dsql_auth.load_cached_token(host, user, region)
        if cached:
            if _is_debug():
                print("[DSQL] using cached token for", host, user, region)
            return cached, host

    # Need SSO either to resolve ID or mint fresh token
    if _is_debug():
        print("[DSQL] establishing SSO session")
    session = sso_login_session(aws_region=region)

    # Resolve DB id if unknown and we don't already have an explicit host
    if not dbid and not host:
        if _is_debug():
            print("[DSQL] resolving cluster by tag...")
        if tag_override:
            key, val = tag_override
        else:
            key, val = _require("TAG_KEY"), _require("TAG_VALUE")
        dbid = resolve_db_id_by_tag(session, region=region, tag_key=key, tag_value=val)
        _save_cached_db_id(dbid, region=region)

    # Compute host if we still don't have one
    if not host:
        host = _db_host_from_id(dbid, region)

    # Mint a fresh token via your helper (admin vs non-admin handled by username)
    token = dsql_auth.get_dsql_token(session, host, user, region)

    # Best-effort set env for scripts that expect these later
    os.environ["DB_TOKEN"] = token
    os.environ["DB_HOST"] = host
    if dbid:
        os.environ["DB_ID"] = dbid

    return token, host


def connect_db(
    *,
    dbname: Optional[str] = None,
    user: Optional[str] = None,
    region: Optional[str] = None,
    token: Optional[str] = None,
    host: Optional[str] = None,
):
    """
    psycopg2 connection with RealDictCursor; mints/uses cached token as needed.
    """
    dbname = dbname or _require("DB_NAME")
    user = user or _require("DB_USER")
    region = region or _require("AWS_REGION")

    token = token or os.environ.get("DB_TOKEN")
    host = host or os.environ.get("DB_HOST") or _best_effort_db_host(region=region)
    if not token or not host:
        token, host = get_token_and_host(user=user, region=region)

    return _pg_connect(
        host=host,
        user=user,
        password=token,
        dbname=dbname,
        sslmode="require",
        cursor_factory=RealDictCursor,
    )
