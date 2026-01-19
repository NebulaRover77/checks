from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path
from typing import Tuple

from flask import Flask, after_this_request, jsonify, redirect, request, send_file

from utilities import create_check

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
        return {}
    try:
        return json.loads(SETTINGS_FILE.read_text())
    except json.JSONDecodeError:
        return {}


def save_settings(settings: dict) -> None:
    SETTINGS_DIR.mkdir(parents=True, exist_ok=True)
    temp_file = SETTINGS_FILE.with_suffix(".tmp")
    temp_file.write_text(json.dumps(settings, indent=2, sort_keys=True))
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
    return jsonify({"settings": sorted(settings.keys())})


@app.get("/api/settings/<name>")
def get_setting(name: str):
    settings = load_settings()
    data = settings.get(name)
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
    settings[name] = data
    save_settings(settings)
    return jsonify({"status": "saved", "name": name})


@app.get("/")
def index():
    return redirect("/generate_check.html")


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


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
