"""Flask-дашборд показателей ВМР по ТЗ."""

from __future__ import annotations

import os
from datetime import date, datetime

from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request

from db import build_dashboard

load_dotenv()

app = Flask(__name__)


def _month_bounds(today: date | None = None) -> tuple[date, date]:
    today = today or date.today()
    start = date(today.year, today.month, 1)
    if today.month == 12:
        end = date(today.year, 12, 31)
    else:
        next_month = date(today.year, today.month + 1, 1)
        end = date.fromordinal(next_month.toordinal() - 1)
    return start, end


DEFAULT_FROM, DEFAULT_TO = _month_bounds()


def _parse_date(raw: str | None, fallback: date) -> date:
    if not raw:
        return fallback
    return datetime.strptime(raw, "%Y-%m-%d").date()


@app.get("/")
def index():
    d0, d1 = _month_bounds()
    return render_template(
        "dashboard.html",
        default_from=d0.isoformat(),
        default_to=d1.isoformat(),
    )


@app.get("/api/data")
def api_data():
    d0, d1 = _month_bounds()
    try:
        date_from = _parse_date(request.args.get("from"), d0)
        date_to = _parse_date(request.args.get("to"), d1)
    except ValueError:
        return jsonify({"ok": False, "error": "Неверный формат даты (ожидается YYYY-MM-DD)"}), 400

    if date_from > date_to:
        return jsonify({"ok": False, "error": "Дата «с» больше даты «по»"}), 400

    try:
        payload = build_dashboard(date_from, date_to)
    except Exception as exc:  # noqa: BLE001
        return jsonify({"ok": False, "error": str(exc)}), 500

    return jsonify({"ok": True, "from": date_from.isoformat(), "to": date_to.isoformat(), **payload})


if __name__ == "__main__":
    host = os.getenv("FLASK_HOST", "127.0.0.1")
    port = int(os.getenv("FLASK_PORT", "5050"))
    app.run(host=host, port=port, debug=True)
