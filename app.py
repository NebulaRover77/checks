from __future__ import annotations

import importlib.util
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Tuple

from flask import Flask, after_this_request, jsonify, redirect, request, send_file

from utilities import create_blank_checks, create_check
import configurations

app = Flask(__name__, static_folder="site", static_url_path="")

os.environ.setdefault("SSO_CACHE_BACKEND", "file")

PAGE_SIZES = {
    "single": (8.5, 4.0),
    "double": (8.5, 7.5),
    "triple": (8.5, 11.0),
}

DSQL_ACCOUNT_FIELDS = (
    "bank_account_id",
    "routing",
    "account",
    "name",
    "company_name_1",
    "company_name_2",
    "company_address_1",
    "company_address_2",
    "next_check_number",
    "bank_name_1",
    "bank_name_2",
    "bank_address_1",
    "bank_address_2",
    "bank_fractional",
)


def _sync_global_settings(settings: dict) -> None:
    global_settings = settings.get("global", {})
    mapping = {
        "START_URL": "sso_url",
        "SSO_REGION": "sso_region",
        "ACCOUNT_ID": "account_id",
        "ROLE_NAME": "role_name",
        "AWS_REGION": "aws_region",
        "DB_NAME": "db_name",
        "DB_USER": "db_user",
        "TAG_KEY": "tag_key",
        "TAG_VALUE": "tag_value",
    }
    cfg = configurations.load_cfg()
    changed = False
    for cfg_key, setting_key in mapping.items():
        value = (global_settings.get(setting_key) or "").strip()
        if value and cfg.get(cfg_key) != value:
            cfg[cfg_key] = value
            changed = True
    if changed:
        configurations.save_cfg(cfg)


def _dsql_required_settings(settings: dict) -> dict:
    import common_dsql

    _sync_global_settings(settings)
    return common_dsql.get_settings(
        ("START_URL", "SSO_REGION", "ACCOUNT_ID", "ROLE_NAME", "AWS_REGION", "DB_NAME", "DB_USER")
    )


def _resolve_start_url(settings: dict, fallback: dict) -> str:
    return settings.get("global", {}).get("sso_url") or fallback["START_URL"]


def _keyring_available() -> bool:
    return importlib.util.find_spec("keyring") is not None


def _boto3_available() -> bool:
    return importlib.util.find_spec("boto3") is not None


def _psycopg2_available() -> bool:
    return importlib.util.find_spec("psycopg2") is not None


def _dsql_service_available(region: str) -> bool:
    try:
        import boto3
        from botocore.exceptions import UnknownServiceError

        boto3.session.Session().client("dsql", region_name=region)
        return True
    except UnknownServiceError:
        return False


def _sso_backend_requires_keyring() -> bool:
    backend = os.getenv("SSO_CACHE_BACKEND", "auto").strip().lower()
    return backend == "keyring"


def _dsql_is_authenticated(start_url: str, cfg: dict) -> bool:
    import sso

    return sso.has_cached_access_token(
        start_url=start_url,
        sso_region=cfg["SSO_REGION"],
        account_id=cfg["ACCOUNT_ID"],
        role_name=cfg["ROLE_NAME"],
    )


def _fetch_dsql_accounts() -> list[dict]:
    import common_dsql

    with common_dsql.connect_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    ba.bank_account_id,
                    ba.routing,
                    ba.account,
                    ba.name,
                    ba.company_name_1,
                    ba.company_name_2,
                    ba.company_address_1,
                    ba.company_address_2,
                    ba.next_check_number,
                    b.bank_name_1,
                    b.bank_name_2,
                    b.bank_address_1,
                    b.bank_address_2,
                    b.bank_fractional
                FROM bank_accounts ba
                LEFT JOIN banks b ON b.routing = ba.routing
                ORDER BY ba.name
                """
            )
            return cur.fetchall()


def _fetch_dsql_account(account_id: str) -> dict | None:
    import common_dsql

    with common_dsql.connect_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    ba.bank_account_id,
                    ba.routing,
                    ba.account,
                    ba.name,
                    ba.company_name_1,
                    ba.company_name_2,
                    ba.company_address_1,
                    ba.company_address_2,
                    ba.next_check_number,
                    b.bank_name_1,
                    b.bank_name_2,
                    b.bank_address_1,
                    b.bank_address_2,
                    b.bank_fractional
                FROM bank_accounts ba
                LEFT JOIN banks b ON b.routing = ba.routing
                WHERE ba.bank_account_id = %s
                """,
                (account_id,),
            )
            return cur.fetchone()


def _update_dsql_next_check(account_id: str, next_check_number: int) -> None:
    import common_dsql

    with common_dsql.connect_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE bank_accounts
                SET next_check_number = %s
                WHERE bank_account_id = %s
                """,
                (next_check_number, account_id),
            )
            conn.commit()

SETTINGS_DIR = Path(os.environ.get("SETTINGS_DIR", "data"))
SETTINGS_FILE = SETTINGS_DIR / "settings.json"
SETTINGS_NAME_RE = re.compile(r"^[A-Za-z0-9_-]{1,50}$")


def load_settings() -> dict:
    if not SETTINGS_FILE.exists():
        return {"presets": {}, "accounts": {}, "global": {}}
    try:
        data = json.loads(SETTINGS_FILE.read_text())
    except json.JSONDecodeError:
        return {"presets": {}, "accounts": {}, "global": {}}
    if isinstance(data, dict) and ("presets" in data or "accounts" in data or "global" in data):
        return {
            "presets": dict(data.get("presets", {})),
            "accounts": dict(data.get("accounts", {})),
            "global": dict(data.get("global", {})),
        }
    if isinstance(data, dict):
        return {"presets": dict(data), "accounts": {}, "global": {}}
    return {"presets": {}, "accounts": {}, "global": {}}


def save_settings(settings: dict) -> None:
    SETTINGS_DIR.mkdir(parents=True, exist_ok=True)
    temp_file = SETTINGS_FILE.with_suffix(".tmp")
    payload = {
        "presets": settings.get("presets", {}),
        "accounts": settings.get("accounts", {}),
        "global": settings.get("global", {}),
    }
    temp_file.write_text(json.dumps(payload, indent=2, sort_keys=True))
    temp_file.replace(SETTINGS_FILE)


def parse_page_size(form: dict) -> Tuple[float, float]:
    choice = form.get("page_size", "triple")
    if choice in PAGE_SIZES:
        return PAGE_SIZES[choice]
    width = float(form.get("custom_width", 8.5))
    height = float(form.get("custom_height", 11.0))
    return (width, height)


def parse_int(value: str, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


@app.get("/api/settings")
def list_settings():
    settings = load_settings()
    return jsonify({"settings": sorted(settings["presets"].keys())})


@app.get("/api/settings/<name>")
def get_setting(name: str):
    settings = load_settings()
    data = settings["presets"].get(name)
    if data is None:
        return jsonify({"error": "Preset not found."}), 404
    return jsonify({"name": name, "data": data})


@app.post("/api/settings")
def save_setting():
    payload = request.get_json(silent=True) or {}
    name = (payload.get("name") or "").strip()
    data = payload.get("data") or {}
    if not SETTINGS_NAME_RE.match(name):
        return jsonify({"error": "Preset name must be 1-50 characters (letters, numbers, _ or -)."}), 400
    if not isinstance(data, dict):
        return jsonify({"error": "Preset data must be a JSON object."}), 400
    settings = load_settings()
    settings["presets"][name] = data
    save_settings(settings)
    return jsonify({"status": "saved", "name": name})


@app.get("/api/accounts")
def list_accounts():
    settings = load_settings()
    return jsonify({"accounts": sorted(settings["accounts"].keys())})


@app.get("/api/accounts/<name>")
def get_account(name: str):
    settings = load_settings()
    data = settings["accounts"].get(name)
    if data is None:
        return jsonify({"error": "Account not found."}), 404
    return jsonify({"name": name, "data": data})


@app.post("/api/accounts")
def save_account():
    payload = request.get_json(silent=True) or {}
    name = (payload.get("name") or "").strip()
    data = payload.get("data") or {}
    if not SETTINGS_NAME_RE.match(name):
        return jsonify({"error": "Account name must be 1-50 characters (letters, numbers, _ or -)."}), 400
    if not isinstance(data, dict):
        return jsonify({"error": "Account data must be a JSON object."}), 400
    settings = load_settings()
    settings["accounts"][name] = data
    save_settings(settings)
    return jsonify({"status": "saved", "name": name})


@app.post("/api/accounts/<name>/last-check")
def update_last_check(name: str):
    payload = request.get_json(silent=True) or {}
    try:
        last_check = int(payload.get("last_check_number"))
    except (TypeError, ValueError):
        return jsonify({"error": "Last check number must be an integer."}), 400
    if last_check < 1:
        return jsonify({"error": "Last check number must be positive."}), 400
    settings = load_settings()
    account = settings["accounts"].get(name)
    if account is None:
        return jsonify({"error": "Account not found."}), 404
    account["last_check_number"] = last_check
    settings["accounts"][name] = account
    save_settings(settings)
    return jsonify({"status": "updated", "name": name, "last_check_number": last_check})


@app.get("/api/global-settings")
def get_global_settings():
    settings = load_settings()
    return jsonify({"settings": settings["global"]})


@app.post("/api/global-settings")
def save_global_settings():
    payload = request.get_json(silent=True) or {}
    sso_url = (payload.get("sso_url") or "").strip()
    if sso_url and not sso_url.startswith(("http://", "https://")):
        return jsonify({"error": "SSO URL must start with http:// or https://"}), 400
    sso_region = (payload.get("sso_region") or "").strip()
    account_id_raw = (payload.get("account_id") or "").strip()
    account_id = re.sub(r"[^0-9]", "", account_id_raw)
    role_name = (payload.get("role_name") or "").strip()
    aws_region = (payload.get("aws_region") or "").strip()
    db_name = (payload.get("db_name") or "").strip()
    db_user = (payload.get("db_user") or "").strip()
    tag_key = (payload.get("tag_key") or "").strip()
    tag_value = (payload.get("tag_value") or "").strip()
    if sso_region and not re.fullmatch(r"[a-z0-9-]+", sso_region):
        return jsonify({"error": "SSO region must look like us-west-2."}), 400
    if aws_region and not re.fullmatch(r"[a-z0-9-]+", aws_region):
        return jsonify({"error": "AWS region must look like us-west-2."}), 400
    if account_id and not re.fullmatch(r"\d{12}", account_id):
        return jsonify({"error": "Account ID must be a 12-digit number."}), 400
    settings = load_settings()
    settings["global"]["sso_url"] = sso_url
    settings["global"]["sso_region"] = sso_region
    settings["global"]["account_id"] = account_id
    settings["global"]["role_name"] = role_name
    settings["global"]["aws_region"] = aws_region
    settings["global"]["db_name"] = db_name
    settings["global"]["db_user"] = db_user
    settings["global"]["tag_key"] = tag_key
    settings["global"]["tag_value"] = tag_value
    save_settings(settings)
    _sync_global_settings(settings)
    return jsonify({"status": "saved", "settings": settings["global"]})


@app.get("/api/sso/status")
def sso_status():
    settings = load_settings()
    try:
        cfg = _dsql_required_settings(settings)
    except RuntimeError as exc:
        return jsonify({"authenticated": False, "error": str(exc)}), 400
    if not _boto3_available():
        return jsonify({"authenticated": False, "error": "boto3 is not available."}), 400
    if _sso_backend_requires_keyring() and not _keyring_available():
        return jsonify({"authenticated": False, "error": "Keyring is not available. Set SSO_CACHE_BACKEND=file."}), 400
    start_url = _resolve_start_url(settings, cfg)
    authenticated = _dsql_is_authenticated(start_url, cfg)
    return jsonify({"authenticated": authenticated})


@app.post("/api/sso/device/start")
def sso_device_start():
    settings = load_settings()
    try:
        cfg = _dsql_required_settings(settings)
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 400
    if not _boto3_available():
        return jsonify({"error": "boto3 is not available."}), 400
    if _sso_backend_requires_keyring() and not _keyring_available():
        return jsonify({"error": "Keyring is not available. Set SSO_CACHE_BACKEND=file."}), 400
    start_url = _resolve_start_url(settings, cfg)
    import sso

    auth = sso.start_device_authorization(
        start_url=start_url,
        sso_region=cfg["SSO_REGION"],
        account_id=cfg["ACCOUNT_ID"],
        role_name=cfg["ROLE_NAME"],
    )
    return jsonify(auth)


@app.post("/api/sso/device/poll")
def sso_device_poll():
    payload = request.get_json(silent=True) or {}
    device_code = (payload.get("device_code") or "").strip()
    if not device_code:
        return jsonify({"error": "Missing device_code."}), 400
    settings = load_settings()
    try:
        cfg = _dsql_required_settings(settings)
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 400
    if not _boto3_available():
        return jsonify({"error": "boto3 is not available."}), 400
    if _sso_backend_requires_keyring() and not _keyring_available():
        return jsonify({"error": "Keyring is not available. Set SSO_CACHE_BACKEND=file."}), 400
    start_url = _resolve_start_url(settings, cfg)
    import sso

    result = sso.poll_device_authorization(
        start_url=start_url,
        sso_region=cfg["SSO_REGION"],
        account_id=cfg["ACCOUNT_ID"],
        role_name=cfg["ROLE_NAME"],
        device_code=device_code,
    )
    if result["status"] in {"pending", "slow_down"}:
        return jsonify(result), 202
    if result["status"] != "authorized":
        return jsonify({"error": "Device authorization expired."}), 400
    return jsonify(result)


@app.get("/api/dsql/accounts")
def list_dsql_accounts():
    settings = load_settings()
    try:
        cfg = _dsql_required_settings(settings)
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 400
    if not _boto3_available():
        return jsonify({"error": "boto3 is not available."}), 400
    if not _dsql_service_available(cfg["AWS_REGION"]):
        return jsonify({"error": "boto3 does not support the DSQL service."}), 400
    if not _psycopg2_available():
        return jsonify({"error": "psycopg2 is not available."}), 400
    if _sso_backend_requires_keyring() and not _keyring_available():
        return jsonify({"error": "Keyring is not available. Set SSO_CACHE_BACKEND=file."}), 400
    start_url = _resolve_start_url(settings, cfg)
    if not _dsql_is_authenticated(start_url, cfg):
        return jsonify({"error": "SSO login required for DSQL access."}), 401
    accounts = _fetch_dsql_accounts()
    return jsonify({"accounts": accounts, "fields": DSQL_ACCOUNT_FIELDS})


@app.post("/api/dsql/accounts/<account_id>/next-check")
def update_dsql_next_check(account_id: str):
    payload = request.get_json(silent=True) or {}
    try:
        next_check = int(payload.get("next_check_number"))
    except (TypeError, ValueError):
        return jsonify({"error": "Next check number must be an integer."}), 400
    if next_check < 1:
        return jsonify({"error": "Next check number must be positive."}), 400
    settings = load_settings()
    try:
        cfg = _dsql_required_settings(settings)
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 400
    if not _boto3_available():
        return jsonify({"error": "boto3 is not available."}), 400
    if not _dsql_service_available(cfg["AWS_REGION"]):
        return jsonify({"error": "boto3 does not support the DSQL service."}), 400
    if not _psycopg2_available():
        return jsonify({"error": "psycopg2 is not available."}), 400
    if _sso_backend_requires_keyring() and not _keyring_available():
        return jsonify({"error": "Keyring is not available. Set SSO_CACHE_BACKEND=file."}), 400
    start_url = _resolve_start_url(settings, cfg)
    if not _dsql_is_authenticated(start_url, cfg):
        return jsonify({"error": "SSO login required for DSQL access."}), 401
    _update_dsql_next_check(account_id, next_check)
    return jsonify({"status": "updated", "account_id": account_id, "next_check_number": next_check})


@app.get("/")
def index():
    return redirect("/generate_check.html")


@app.get("/blank")
def blank():
    return redirect("/blank_checks.html")


@app.get("/settings")
def settings_page():
    return redirect("/settings.html")


@app.get("/login")
def login():
    settings = load_settings()
    sso_url = settings["global"].get("sso_url")
    if not sso_url:
        return jsonify({"error": "SSO URL is not configured."}), 400
    return redirect(sso_url)


@app.post("/generate")
def generate():
    form = request.form
    payee = form.get("payee", "")
    amount = form.get("amount", "0")
    date = form.get("date", "")
    memo = form.get("memo", "")

    page_size = parse_page_size(form)
    checks_per_page = parse_int(form.get("checks_per_page", "1"), 1)
    position = parse_int(form.get("position", "1"), 1)

    tmp_file = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
    tmp_file.close()

    @after_this_request
    def cleanup(response):
        try:
            os.remove(tmp_file.name)
        except FileNotFoundError:
            pass
        return response

    create_check(
        payee,
        amount,
        date,
        memo,
        position=position,
        filename=tmp_file.name,
        checks_per_page=checks_per_page,
        page_size=page_size,
    )

    return send_file(tmp_file.name, as_attachment=True, download_name="check.pdf")


@app.post("/generate-blank")
def generate_blank():
    form = request.form
    account_name = form.get("account", "")
    account_source = form.get("account_source", "local")
    settings = load_settings()
    account = None
    if account_source == "dsql":
        try:
            cfg = _dsql_required_settings(settings)
        except RuntimeError as exc:
            return jsonify({"error": str(exc)}), 400
        if not _boto3_available():
            return jsonify({"error": "boto3 is not available."}), 400
        if not _dsql_service_available(cfg["AWS_REGION"]):
            return jsonify({"error": "boto3 does not support the DSQL service."}), 400
        if not _psycopg2_available():
            return jsonify({"error": "psycopg2 is not available."}), 400
        if _sso_backend_requires_keyring() and not _keyring_available():
            return jsonify({"error": "Keyring is not available. Set SSO_CACHE_BACKEND=file."}), 400
        start_url = _resolve_start_url(settings, cfg)
        if not _dsql_is_authenticated(start_url, cfg):
            return jsonify({"error": "SSO login required for DSQL access."}), 401
        account = _fetch_dsql_account(account_name)
        if not account:
            return jsonify({"error": "DSQL account not found."}), 400
    else:
        account = settings["accounts"].get(account_name)
        if not account:
            return jsonify({"error": "Account not found."}), 400

    first_check_number = parse_int(form.get("first_check_number", "1"), 1)
    total_checks = parse_int(form.get("total_checks", "1"), 1)
    if first_check_number < 1 or total_checks < 1:
        return jsonify({"error": "Check numbers and totals must be positive."}), 400

    page_size = parse_page_size(form)
    checks_per_page = parse_int(form.get("checks_per_page", "1"), 1)
    checks_per_page = max(1, min(checks_per_page, 3))

    tmp_file = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
    tmp_file.close()

    @after_this_request
    def cleanup(response):
        try:
            os.remove(tmp_file.name)
        except FileNotFoundError:
            pass
        return response

    if account_source == "dsql":
        owner_name = "\n".join(
            filter(None, [account.get("company_name_1"), account.get("company_name_2")])
        )
        owner_address = "\n".join(
            filter(None, [account.get("company_address_1"), account.get("company_address_2")])
        )
        bank_name = "\n".join(filter(None, [account.get("bank_name_1"), account.get("bank_name_2")]))
        bank_address = "\n".join(
            filter(None, [account.get("bank_address_1"), account.get("bank_address_2")])
        )
        routing_number = account.get("routing")
        account_number = account.get("account")
        fractional_routing = account.get("bank_fractional")
        micr_style = "A"
    else:
        owner_name = account.get("owner_name")
        owner_address = account.get("owner_address")
        bank_name = account.get("bank_name")
        bank_address = account.get("bank_address")
        routing_number = account.get("routing_number")
        account_number = account.get("account_number")
        fractional_routing = account.get("fractional_routing")
        micr_style = account.get("micr_style", "A")

    create_blank_checks(
        filename=tmp_file.name,
        checks_per_page=checks_per_page,
        page_size=page_size,
        total_checks=total_checks,
        first_check_number=first_check_number,
        owner_name=owner_name,
        owner_address=owner_address,
        bank_name=bank_name,
        bank_address=bank_address,
        fractional_routing=fractional_routing,
        routing_number=routing_number,
        account_number=account_number,
        micr_style=micr_style,
    )

    return send_file(tmp_file.name, as_attachment=True, download_name="blank_checks.pdf")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
