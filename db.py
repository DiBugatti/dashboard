"""Дашборд ВМР: SQL к msk_uat + msk_buh по ТЗ."""

from __future__ import annotations

import os
import statistics
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any, Iterator

import pymssql
from dotenv import load_dotenv

load_dotenv()

DB_UAT = os.getenv("SQL_DATABASE_UAT", os.getenv("SQL_DATABASE", "msk_uat"))
DB_BUH = os.getenv("SQL_DATABASE_BUH", "msk_buh")

# цвета фракций — постоянные во всех блоках (п. 9 ТЗ)
FRACTION_COLORS = {
    "ПЭТ бело-голубой": "#3dba7a",
    "ПЭТ Коричнево-зелёный МИКС": "#2a8f5c",
    "ПЭТ микс 4 цвета": "#2a8f5c",
    "ПЭТ микс": "#5bb8d4",
    "ПЭТ матовый (белый)": "#8ec5a8",
    "ПЭТ молочный,маслянный": "#8ec5a8",
    "Картон": "#e2b45a",
    "картон": "#e2b45a",
    "Банка алюминиевая": "#c9886a",
    "алюминиевая банка": "#c9886a",
    "Стекло": "#7a8fa3",
    "стеклобой микс": "#7a8fa3",
    "Химия": "#9b7edc",
    "флакон": "#9b7edc",
    "Канистра": "#d47a9b",
    "ПНД Канистра": "#d47a9b",
}


def fraction_color(name: str) -> str:
    if name in FRACTION_COLORS:
        return FRACTION_COLORS[name]
    for k, v in FRACTION_COLORS.items():
        if k.lower() == (name or "").lower():
            return v
    return "#6a8f7c"


def _cfg() -> dict[str, str]:
    return {
        "uat_server": os.getenv("SQL_SERVER_UAT", os.getenv("SQL_SERVER", "192.168.80.10")),
        "buh_server": os.getenv("SQL_SERVER_BUH", "192.168.80.5"),
        "uat_database": DB_UAT,
        "buh_database": DB_BUH,
        "user": os.getenv("SQL_USER", "user1c"),
        "password": os.getenv("SQL_PASSWORD", ""),
    }


def _server_for(database: str) -> str:
    cfg = _cfg()
    if database == cfg["buh_database"]:
        return cfg["buh_server"]
    return cfg["uat_server"]


@contextmanager
def connect(database: str | None = None) -> Iterator[Any]:
    cfg = _cfg()
    if not cfg["password"]:
        raise RuntimeError("Не задан SQL_PASSWORD в .env")
    db = database or cfg["uat_database"]
    conn = pymssql.connect(
        server=_server_for(db),
        user=cfg["user"],
        password=cfg["password"],
        database=db,
        login_timeout=10,
        timeout=90,
        charset="utf8",
    )
    try:
        yield conn
    finally:
        conn.close()


def _serialize(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def _f(value: Any) -> float:
    return float(_serialize(value) or 0)


def _bounds(date_from: date, date_to: date) -> tuple[str, str]:
    return date_from.isoformat(), date.fromordinal(date_to.toordinal() + 1).isoformat()


def clean_buh_name(name: str) -> str:
    s = name or ""
    for pref in (
        "Вторичные ресурсы,извлеченные при сортировке твердых коммунальных отходов",
        "Вторичные ресурсы, извлеченные при сортировке твердых коммунальных отходов",
        "Вторичные ресурсы, извлеченное при сортировке твердых коммунальных  отходов",
    ):
        s = s.replace(pref, "")
    return s.replace("(", "").replace(")", "").strip()


SHIFTS_QUERY = """
SELECT
  CONVERT(varchar(10), DATEADD(year, -2000, d._Date_Time), 120) AS DocDate,
  CONVERT(nvarchar(20), d._Number) AS DocNumber,
  CONVERT(nvarchar(150), brig._Description) AS Brigade,
  CONVERT(nvarchar(150), pod._Description) AS Workshop,
  CONVERT(nvarchar(150), nom._Description) AS Nomenclature,
  vt._Fld18353 AS Quantity
FROM dbo._Document18335 AS d
INNER JOIN dbo._Document18335_VT18350 AS vt ON vt._Document18335_IDRRef = d._IDRRef
LEFT JOIN dbo._Reference106X1 AS brig ON brig._IDRRef = d._Fld18344RRef
LEFT JOIN dbo._Reference90 AS pod ON pod._IDRRef = d._Fld18341RRef
LEFT JOIN dbo._Reference82 AS nom ON nom._IDRRef = vt._Fld18354RRef
WHERE d._Marked = 0x00
  AND DATEADD(year, -2000, d._Date_Time) >= %s
  AND DATEADD(year, -2000, d._Date_Time) <  %s
ORDER BY DATEADD(year, -2000, d._Date_Time), d._Number, vt._LineNo18351
"""

SHIPMENTS_QUERY = """
SELECT
  CONVERT(varchar(10), DATEADD(year, -2000, d._Date_Time), 120) AS DocDate,
  CONVERT(nvarchar(20), d._Number) AS DocNumber,
  CONVERT(nvarchar(20), d._Fld18384) AS VesySoftNumber,
  ISNULL(d._Fld18387, 0) AS BaleWeight,
  ISNULL(d._Fld18389, 0) AS ScaleWeight,
  CONVERT(nvarchar(150), nom._Description) AS Nomenclature,
  ISNULL(vt._Fld18397, 0) AS LineQty
FROM dbo._Document18337 AS d
LEFT JOIN dbo._Document18337_VT18393 AS vt ON vt._Document18337_IDRRef = d._IDRRef
LEFT JOIN dbo._Reference82 AS nom ON nom._IDRRef = vt._Fld18439RRef
WHERE d._Marked = 0x00
  AND DATEADD(year, -2000, d._Date_Time) >= %s
  AND DATEADD(year, -2000, d._Date_Time) <  %s
ORDER BY DATEADD(year, -2000, d._Date_Time), d._Number
"""


def vesy_soft_axis_label(raw: str) -> str:
    """Нижняя подпись оси: числовая часть «Номер документа весы софт» (Ч1-0032062 → 32062)."""
    s = (raw or "").strip()
    if not s:
        return "—"
    if "-" in s:
        s = s.rsplit("-", 1)[-1]
    s = s.lstrip("0") or "0"
    return s

WAREHOUSE_QUERY = """
SELECT
  CONVERT(nvarchar(150), nom._Description) AS Nomenclature,
  ISNULL(SUM(t._Fld18409), 0) AS Qty
FROM dbo._Document18336 AS t
INNER JOIN dbo._Enum18339 AS st ON st._IDRRef = t._Fld18367RRef AND st._EnumOrder = 1
LEFT JOIN dbo._Reference82 AS nom ON nom._IDRRef = t._Fld18410RRef
WHERE t._Marked = 0x00
GROUP BY CONVERT(nvarchar(150), nom._Description)
HAVING ISNULL(SUM(t._Fld18409), 0) > 0
ORDER BY ISNULL(SUM(t._Fld18409), 0) DESC
"""

SALES_PERIOD_QUERY = """
SELECT
  CONVERT(nvarchar(500), n._Description) AS NomFull,
  CONVERT(nvarchar(200), k._Description) AS Contragent,
  vt._Fld9752 AS Qty,
  vt._Fld9753 AS Price,
  vt._Fld9754 AS Amount
FROM dbo._Document637 AS d
INNER JOIN dbo._Document637_VT9746 AS vt ON vt._Document637_IDRRef = d._IDRRef
LEFT JOIN dbo._Reference204 AS n ON n._IDRRef = vt._Fld9748RRef
LEFT JOIN dbo._Reference177 AS k ON k._IDRRef = d._Fld9695RRef
WHERE d._Marked = 0x00 AND d._Posted = 0x01
  AND DATEADD(year, -2000, d._Date_Time) >= %s
  AND DATEADD(year, -2000, d._Date_Time) <  %s
"""

SALES_12M_QUERY = """
SELECT
  CONVERT(varchar(7), DATEADD(year, -2000, d._Date_Time), 120) AS MonthKey,
  CONVERT(nvarchar(500), n._Description) AS NomFull,
  SUM(vt._Fld9752) AS Qty,
  SUM(vt._Fld9754) AS Amount
FROM dbo._Document637 AS d
INNER JOIN dbo._Document637_VT9746 AS vt ON vt._Document637_IDRRef = d._IDRRef
LEFT JOIN dbo._Reference204 AS n ON n._IDRRef = vt._Fld9748RRef
WHERE d._Marked = 0x00 AND d._Posted = 0x01
  AND DATEADD(year, -2000, d._Date_Time) >= %s
  AND DATEADD(year, -2000, d._Date_Time) <  %s
GROUP BY
  CONVERT(varchar(7), DATEADD(year, -2000, d._Date_Time), 120),
  CONVERT(nvarchar(500), n._Description)
"""


def fetch_shifts(date_from: date, date_to: date) -> list[dict[str, Any]]:
    d0, d1 = _bounds(date_from, date_to)
    with connect(DB_UAT) as conn:
        cur = conn.cursor(as_dict=True)
        cur.execute(SHIFTS_QUERY, (d0, d1))
        rows = cur.fetchall() or []
    return [
        {
            "date": _serialize(r.get("DocDate")),
            "number": (r.get("DocNumber") or "").strip(),
            "brigade": (r.get("Brigade") or "").strip() or "—",
            "workshop": (r.get("Workshop") or "").strip() or "—",
            "nomenclature": (r.get("Nomenclature") or "").strip() or "—",
            "quantity": _f(r.get("Quantity")),
        }
        for r in rows
    ]


def fetch_shipments(date_from: date, date_to: date) -> list[dict[str, Any]]:
    d0, d1 = _bounds(date_from, date_to)
    with connect(DB_UAT) as conn:
        cur = conn.cursor(as_dict=True)
        cur.execute(SHIPMENTS_QUERY, (d0, d1))
        rows = cur.fetchall() or []
    return [
        {
            "date": _serialize(r.get("DocDate")),
            "number": (r.get("DocNumber") or "").strip(),
            "vesy_soft_number": (r.get("VesySoftNumber") or "").strip(),
            "label": vesy_soft_axis_label((r.get("VesySoftNumber") or "").strip()),
            "bale_weight": _f(r.get("BaleWeight")),
            "scale_weight": _f(r.get("ScaleWeight")),
            "nomenclature": (r.get("Nomenclature") or "").strip() or "—",
            "line_qty": _f(r.get("LineQty")),
        }
        for r in rows
    ]


def fetch_warehouse() -> list[dict[str, Any]]:
    with connect(DB_UAT) as conn:
        cur = conn.cursor(as_dict=True)
        cur.execute(WAREHOUSE_QUERY)
        rows = cur.fetchall() or []
    return [
        {
            "nomenclature": (r.get("Nomenclature") or "").strip() or "—",
            "quantity": _f(r.get("Qty")),
        }
        for r in rows
    ]


def fetch_sales(date_from: date, date_to: date) -> list[dict[str, Any]]:
    d0, d1 = _bounds(date_from, date_to)
    with connect(DB_BUH) as conn:
        cur = conn.cursor(as_dict=True)
        cur.execute(SALES_PERIOD_QUERY, (d0, d1))
        rows = cur.fetchall() or []
    out = []
    for r in rows:
        full = (r.get("NomFull") or "").strip()
        key = clean_buh_name(full)
        out.append(
            {
                "fraction": key or full or "—",
                "contragent": (r.get("Contragent") or "").strip() or "—",
                "quantity": _f(r.get("Qty")),
                "price": _f(r.get("Price")),
                "amount": _f(r.get("Amount")),
            }
        )
    return out


def fetch_sales_monthly(months: int = 12) -> list[dict[str, Any]]:
    today = date.today()
    start = date(today.year, today.month, 1) - timedelta(days=months * 31)
    start = date(start.year, start.month, 1)
    end = date.fromordinal(today.toordinal() + 1)
    with connect(DB_BUH) as conn:
        cur = conn.cursor(as_dict=True)
        cur.execute(SALES_12M_QUERY, (start.isoformat(), end.isoformat()))
        rows = cur.fetchall() or []
    out = []
    for r in rows:
        full = (r.get("NomFull") or "").strip()
        out.append(
            {
                "month": _serialize(r.get("MonthKey")),
                "fraction": clean_buh_name(full) or full or "—",
                "quantity": _f(r.get("Qty")),
                "amount": _f(r.get("Amount")),
            }
        )
    return out


def _build_production(shifts: list[dict[str, Any]]) -> dict[str, Any]:
    by_day_brigade: dict[str, dict[str, float]] = {}
    by_workshop: dict[str, float] = {}
    shift_ids: set[str] = set()
    brigades: set[str] = set()

    for r in shifts:
        day = r["date"] or "—"
        brig = r["brigade"]
        brigades.add(brig)
        by_day_brigade.setdefault(day, {})
        by_day_brigade[day][brig] = by_day_brigade[day].get(brig, 0.0) + r["quantity"]
        by_workshop[r["workshop"]] = by_workshop.get(r["workshop"], 0.0) + r["quantity"]
        shift_ids.add(f"{r['date']}|{r['number']}")

    days = sorted(by_day_brigade.keys())
    brig_list = sorted(brigades)
    datasets = []
    for brig in brig_list:
        datasets.append(
            {
                "name": brig,
                "color": "#3dba7a" if "БА" in brig else "#e2b45a",
                "values": [round(by_day_brigade[d].get(brig, 0.0), 3) for d in days],
            }
        )

    total_w = sum(by_workshop.values()) or 1.0
    workshops = [
        {
            "name": k,
            "quantity": round(v, 3),
            "share_pct": round(v / total_w * 100.0, 1),
        }
        for k, v in sorted(by_workshop.items(), key=lambda x: -x[1])
    ]

    return {
        "days": days,
        "brigades": datasets,
        "workshops": workshops,
        "shift_count": len(shift_ids),
        "total_kg": round(sum(by_workshop.values()), 3),
        "note": "Выработка включает россыпные фракции",
    }


def _build_shrinkage(ship_rows: list[dict[str, Any]]) -> dict[str, Any]:
    # группировка по документу
    docs: dict[str, dict[str, Any]] = {}
    for r in ship_rows:
        key = f"{r['date']}|{r['number']}"
        doc = docs.setdefault(
            key,
            {
                "date": r["date"],
                "number": r["number"],
                "vesy_soft_number": r.get("vesy_soft_number") or "",
                "label": r.get("label") or vesy_soft_axis_label(r.get("vesy_soft_number") or ""),
                "bale_weight": r["bale_weight"],
                "scale_weight": r["scale_weight"],
                "lines": [],
            },
        )
        if r["line_qty"]:
            doc["lines"].append({"nomenclature": r["nomenclature"], "qty": r["line_qty"]})

    trips = []
    frac_agg: dict[str, dict[str, float]] = {}
    pcts_for_median: list[float] = []

    for doc in docs.values():
        bale = doc["bale_weight"]
        scale = doc["scale_weight"]
        shrink_kg = bale - scale
        shrink_pct = (shrink_kg / bale * 100.0) if bale else 0.0
        fracs = {x["nomenclature"] for x in doc["lines"] if x["nomenclature"] != "—"}
        mixed = len(fracs) > 1
        anomaly = bool(bale and abs(shrink_kg) / bale > 0.15)

        trips.append(
            {
                "date": doc["date"],
                "number": doc["number"],
                "vesy_soft_number": doc["vesy_soft_number"],
                "bale_weight": round(bale, 3),
                "scale_weight": round(scale, 3),
                "shrink_kg": round(shrink_kg, 3),
                "shrink_pct": round(shrink_pct, 2),
                "mixed": mixed,
                "anomaly": anomaly,
                "label": doc["label"],
            }
        )
        if not anomaly and bale > 0:
            pcts_for_median.append(shrink_pct)

        # пропорционально весу строк
        line_sum = sum(x["qty"] for x in doc["lines"]) or 0.0
        if line_sum <= 0:
            continue
        for line in doc["lines"]:
            share = line["qty"] / line_sum
            fa = frac_agg.setdefault(
                line["nomenclature"],
                {"trips": 0.0, "bale": 0.0, "scale": 0.0, "shrink_kg": 0.0},
            )
            fa["trips"] += 1.0 / max(len(doc["lines"]), 1)
            fa["bale"] += bale * share
            fa["scale"] += scale * share
            fa["shrink_kg"] += shrink_kg * share

    trips.sort(key=lambda x: (x["date"] or "", x["number"] or ""))
    median = statistics.median(pcts_for_median) if pcts_for_median else 0.0

    by_fraction = []
    for name, fa in sorted(frac_agg.items(), key=lambda x: -abs(x[1]["shrink_kg"])):
        pct = (fa["shrink_kg"] / fa["bale"] * 100.0) if fa["bale"] else 0.0
        by_fraction.append(
            {
                "name": name,
                "trip_count": round(fa["trips"], 1),
                "shrink_pct": round(pct, 2),
                "shrink_kg": round(fa["shrink_kg"], 3),
                "color": fraction_color(name),
            }
        )

    total_bale = sum(t["bale_weight"] for t in trips)
    total_scale = sum(t["scale_weight"] for t in trips)
    total_shrink = total_bale - total_scale
    total_pct = (total_shrink / total_bale * 100.0) if total_bale else 0.0

    return {
        "trips": trips,
        "median_pct": round(median, 2),
        "by_fraction": by_fraction,
        "total": {
            "trip_count": len(trips),
            "bale_kg": round(total_bale, 3),
            "scale_kg": round(total_scale, 3),
            "shrink_kg": round(total_shrink, 3),
            "shrink_pct": round(total_pct, 2),
        },
        "anomalies": [t for t in trips if t["anomaly"]],
    }


def _last_prices(sales_rows: list[dict[str, Any]]) -> dict[str, float]:
    """Последняя средневзвешенная цена ₽/т по фракции из строк периода продаж."""
    agg: dict[str, list[float]] = {}
    for r in sales_rows:
        if r["quantity"] <= 0:
            continue
        key = r["fraction"].lower()
        agg.setdefault(key, [0.0, 0.0])
        agg[key][0] += r["amount"]
        agg[key][1] += r["quantity"]
    return {k: (v[0] / v[1] if v[1] else 0.0) for k, v in agg.items()}


def _build_warehouse(wh: list[dict[str, Any]], prices: dict[str, float]) -> dict[str, Any]:
    total = sum(x["quantity"] for x in wh) or 1.0
    rows = []
    total_rub = 0.0
    for x in wh:
        price = prices.get(x["nomenclature"].lower(), 0.0)
        # цена в БП за тонну, остаток в кг
        rub = x["quantity"] / 1000.0 * price
        total_rub += rub
        rows.append(
            {
                "name": x["nomenclature"],
                "quantity_kg": round(x["quantity"], 3),
                "share_pct": round(x["quantity"] / total * 100.0, 1),
                "price_per_t": round(price, 2),
                "value_rub": round(rub, 2),
                "color": fraction_color(x["nomenclature"]),
            }
        )
    return {
        "as_of": "сегодня",
        "rows": rows,
        "total_kg": round(sum(x["quantity"] for x in wh), 3),
        "total_rub": round(total_rub, 2),
    }


def _build_sales(sales: list[dict[str, Any]]) -> dict[str, Any]:
    by_frac: dict[str, dict[str, float]] = {}
    by_buyer: dict[str, float] = {}
    for r in sales:
        f = by_frac.setdefault(r["fraction"], {"tons": 0.0, "rub": 0.0})
        f["tons"] += r["quantity"]
        f["rub"] += r["amount"]
        by_buyer[r["contragent"]] = by_buyer.get(r["contragent"], 0.0) + r["amount"]

    fractions = [
        {
            "name": k,
            "tons": round(v["tons"], 3),
            "rub": round(v["rub"], 2),
            "color": fraction_color(k),
        }
        for k, v in sorted(by_frac.items(), key=lambda x: -x[1]["rub"])
    ]
    total_rub = sum(by_buyer.values()) or 1.0
    buyers = [
        {
            "name": k,
            "rub": round(v, 2),
            "share_pct": round(v / total_rub * 100.0, 1),
        }
        for k, v in sorted(by_buyer.items(), key=lambda x: -x[1])
    ]
    concentration = None
    if buyers and buyers[0]["share_pct"] > 50:
        concentration = {
            "name": buyers[0]["name"],
            "share_pct": buyers[0]["share_pct"],
            "rub": buyers[0]["rub"],
        }
    return {
        "by_fraction": fractions,
        "buyers": buyers,
        "total_rub": round(sum(v["rub"] for v in by_frac.values()), 2),
        "total_tons": round(sum(v["tons"] for v in by_frac.values()), 3),
        "concentration": concentration,
    }


def _build_prices(monthly: list[dict[str, Any]]) -> dict[str, Any]:
    # month -> fraction -> (amount, qty)
    months = sorted({m["month"] for m in monthly if m["month"]})
    if len(months) > 12:
        months = months[-12:]
    data: dict[str, dict[str, list[float]]] = {}
    for r in monthly:
        if r["month"] not in months:
            continue
        fr = r["fraction"]
        data.setdefault(fr, {})
        data[fr][r["month"]] = [r["amount"], r["quantity"]]

    series = []
    for fr, by_m in sorted(data.items()):
        prices = []
        for m in months:
            aq = by_m.get(m)
            prices.append(round(aq[0] / aq[1], 2) if aq and aq[1] else None)
        base = next((p for p in prices if p), None)
        indexes = []
        for p in prices:
            if p is None or not base:
                indexes.append(None)
            else:
                indexes.append(round(p / base * 100.0, 1))
        series.append(
            {
                "name": fr,
                "color": fraction_color(fr),
                "prices": prices,
                "indexes": indexes,
                "last_index": next((x for x in reversed(indexes) if x is not None), None),
            }
        )

    # топ фракций по полноте ряда
    series = sorted(series, key=lambda s: -sum(1 for x in s["indexes"] if x is not None))[:8]
    return {"months": months, "series": series}


def build_dashboard(
    date_from: date,
    date_to: date,
) -> dict[str, Any]:
    shifts = fetch_shifts(date_from, date_to)
    ships = fetch_shipments(date_from, date_to)
    warehouse = fetch_warehouse()

    sales: list[dict[str, Any]] = []
    monthly: list[dict[str, Any]] = []
    sales_error = None
    try:
        sales = fetch_sales(date_from, date_to)
        monthly = fetch_sales_monthly(12)
    except Exception as exc:  # noqa: BLE001
        sales_error = str(exc)

    production = _build_production(shifts)
    shrinkage = _build_shrinkage(ships)
    prices_map = _last_prices(sales)
    # дотянуть цены за 12 мес. если в периоде пусто
    if not prices_map and monthly:
        tmp = [
            {"fraction": m["fraction"], "quantity": m["quantity"], "amount": m["amount"]}
            for m in monthly
        ]
        prices_map = _last_prices(tmp)

    wh = _build_warehouse(warehouse, prices_map)
    sales_block = _build_sales(sales)
    prices_block = _build_prices(monthly)

    # KPI плитки по ТЗ
    prod_kg = production["total_kg"]
    ship_kg = shrinkage["total"]["scale_kg"]
    # усушка по ТЗ: тюки − весовая
    shrink_kg = shrinkage["total"]["shrink_kg"]
    shrink_pct = shrinkage["total"]["shrink_pct"]
    # оценка в рублях — грубо по средней цене корзины продаж периода
    avg_price = (
        sales_block["total_rub"] / sales_block["total_tons"]
        if sales_block["total_tons"]
        else 0.0
    )
    shrink_rub = shrink_kg / 1000.0 * avg_price

    kpis = {
        "production_t": round(prod_kg / 1000.0, 1),
        "shift_count": production["shift_count"],
        "shipped_t": round(ship_kg / 1000.0, 1),
        "trip_count": shrinkage["total"]["trip_count"],
        "sold_rub": sales_block["total_rub"],
        "sold_tons": round(sales_block["total_tons"], 1),
        "shrink_pct": round(shrink_pct, 1),
        "shrink_kg": round(shrink_kg, 3),
        "shrink_rub": round(shrink_rub, 2),
    }

    return {
        "kpis": kpis,
        "production": production,
        "shrinkage": shrinkage,
        "warehouse": wh,
        "prices": prices_block,
        "sales": sales_block,
        "sales_error": sales_error,
        "rows": shifts,
    }
