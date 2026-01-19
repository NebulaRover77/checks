from __future__ import annotations

import os
import tempfile
from typing import Tuple

from flask import Flask, after_this_request, redirect, request, send_file

from utilities import create_check

app = Flask(__name__, static_folder="site", static_url_path="")

PAGE_SIZES = {
    "single": (8.5, 4.0),
    "double": (8.5, 7.5),
    "triple": (8.5, 11.0),
}


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
