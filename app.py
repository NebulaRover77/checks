from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path
from typing import Tuple

from flask import Flask, after_this_request, jsonify, redirect, request, send_file

from utilities import create_blank_checks, create_check

app = Flask(__name__, static_folder="site", static_url_path="")

PAGE_SIZES = {
    "single": (8.5, 4.0),
    "double": (8.5, 7.5),
    "triple": (8.5, 11.0),
}

SETTINGS_DIR = Path(os.environ.get("SETTINGS_DIR", "data"))
SETTINGS_FILE = SETTINGS_DIR / "settings.json"
SETTINGS_NAME_RE = re.compile(r"^[A-Za-z0-9_-]{1,50}$")


def load_settings() -> dict:
    if not SETTINGS_FILE.exists():
        return {"presets": {}, "accounts": {}}
    try:
        data = json.loads(SETTINGS_FILE.read_text())
    except json.JSONDecodeError:
        return {"presets": {}, "accounts": {}}
    if isinstance(data, dict) and ("presets" in data or "accounts" in data):
        return {
            "presets": dict(data.get("presets", {})),
            "accounts": dict(data.get("accounts", {})),
        }
    if isinstance(data, dict):
        return {"presets": dict(data), "accounts": {}}
    return {"presets": {}, "accounts": {}}


def save_settings(settings: dict) -> None:
    SETTINGS_DIR.mkdir(parents=True, exist_ok=True)
    temp_file = SETTINGS_FILE.with_suffix(".tmp")
    payload = {
        "presets": settings.get("presets", {}),
        "accounts": settings.get("accounts", {}),
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


@app.get("/")
def index():
    return redirect("/generate_check.html")


@app.get("/blank")
def blank():
    return redirect("/blank_checks.html")


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
    settings = load_settings()
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

    create_blank_checks(
        filename=tmp_file.name,
        checks_per_page=checks_per_page,
        page_size=page_size,
        total_checks=total_checks,
        first_check_number=first_check_number,
        owner_name=account.get("owner_name"),
        owner_address=account.get("owner_address"),
        bank_name=account.get("bank_name"),
        bank_address=account.get("bank_address"),
        fractional_routing=account.get("fractional_routing"),
        routing_number=account.get("routing_number"),
        account_number=account.get("account_number"),
        micr_style=account.get("micr_style", "A"),
    )

    return send_file(tmp_file.name, as_attachment=True, download_name="blank_checks.pdf")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
