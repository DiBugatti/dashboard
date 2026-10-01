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


def _norm_match_key(name: str) -> str:
    """Нормализация для стыковки БП ↔ уатВидГруза (пробелы вокруг запятой)."""
    s = (name or "").strip().lower()
    while ", " in s:
        s = s.replace(", ", ",")
    while "  " in s:
        s = s.replace("  ", " ")
    return s


# УАТ: номенклатура.уатВидГруза → справочник видов груза (_Reference10024)
VID_GRUZA_QUERY = """
SELECT
  CONVERT(nvarchar(150), nu._Description) AS NomUat,
  CONVERT(nvarchar(200), vg._Description) AS VidGruza
FROM dbo._Reference82 AS nu
INNER JOIN dbo._Reference10024 AS vg ON vg._IDRRef = nu._Fld15914RRef
WHERE nu._Marked = 0x00
  AND vg._Marked = 0x00
"""


SHIFTS_QUERY = """
SELECT
  CONVERT(varchar(10), DATEADD(year, -2000, d._Date_Time), 120) AS DocDate,
  CONVERT(nvarchar(20), d._Number) AS DocNumber,
  CONVERT(nvarchar(150), brig._Description) AS Brigade,
  CONVERT(nvarchar(150), pod._Description) AS Workshop,
  CONVERT(nvarchar(150), nom._Description) AS Nomenclature,
  CONVERT(nvarchar(40), vt._Fld18360) AS Tag,
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
  -- TODO: номер машины. В подсказке графика усушки строка «Машина» появится сама,
  -- как только запрос начнёт отдавать колонку Vehicle (поле ТС документа ак_Отгрузка).
  -- Вес шапки только для сверки. Усушку считаем по биркам и весам,
  -- поле «Расхождение» не читаем: оно пишется один раз при загрузке весов.
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

# Процент отбора: нетто ТКО из РегистрСведений.Взвешивания
# против итогового количества Документ.ак_Смены. ИтогоТКО шапки не используем.
# _Enum9405._EnumOrder = 6 — вид отходов «ТКО».
SELECTION_QUERY = """
WITH tko AS (
  SELECT
    CONVERT(varchar(10), DATEADD(year, -2000, w._Fld9407), 120) AS DayDate,
    SUM(w._Fld9409) AS TkoNettoKg
  FROM dbo._InfoRg9406 AS w
  INNER JOIN dbo._Enum9405 AS e
    ON e._IDRRef = w._Fld9411RRef AND e._EnumOrder = 6
  WHERE DATEADD(year, -2000, w._Fld9407) >= %s
    AND DATEADD(year, -2000, w._Fld9407) <  %s
  GROUP BY CONVERT(varchar(10), DATEADD(year, -2000, w._Fld9407), 120)
),
sh AS (
  SELECT
    CONVERT(varchar(10), DATEADD(year, -2000, d._Date_Time), 120) AS DayDate,
    SUM(vt._Fld18353) AS OutputKg
  FROM dbo._Document18335 AS d
  LEFT JOIN dbo._Document18335_VT18350 AS vt
    ON vt._Document18335_IDRRef = d._IDRRef
  WHERE d._Marked = 0x00
    AND DATEADD(year, -2000, d._Date_Time) >= %s
    AND DATEADD(year, -2000, d._Date_Time) <  %s
  GROUP BY CONVERT(varchar(10), DATEADD(year, -2000, d._Date_Time), 120)
)
SELECT
  COALESCE(t.DayDate, s.DayDate) AS DayDate,
  ISNULL(t.TkoNettoKg, 0) AS TkoNettoKg,
  ISNULL(s.OutputKg, 0) AS OutputKg
FROM tko AS t
FULL JOIN sh AS s ON s.DayDate = t.DayDate
ORDER BY 1
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

# Цена номенклатуры — из её последнего проведённого документа, не средняя за период.
LAST_SALE_PRICE_QUERY = """
WITH line AS (
  SELECT
    CONVERT(nvarchar(500), n._Description) AS NomFull,
    d._IDRRef AS DocId,
    CONVERT(varchar(19), DATEADD(year, -2000, d._Date_Time), 120) AS DocDate,
    CONVERT(nvarchar(20), d._Number) AS DocNumber,
    vt._Fld9752 AS Qty,
    vt._Fld9754 AS Amount
  FROM dbo._Document637 AS d
  INNER JOIN dbo._Document637_VT9746 AS vt ON vt._Document637_IDRRef = d._IDRRef
  LEFT JOIN dbo._Reference204 AS n ON n._IDRRef = vt._Fld9748RRef
  WHERE d._Marked = 0x00 AND d._Posted = 0x01
    AND ISNULL(vt._Fld9752, 0) > 0
),
per_doc AS (
  SELECT
    NomFull,
    DocDate,
    DocNumber,
    SUM(Qty) AS Qty,
    SUM(Amount) AS Amount,
    ROW_NUMBER() OVER (
      PARTITION BY NomFull
      ORDER BY DocDate DESC, DocNumber DESC
    ) AS rn
  FROM line
  GROUP BY NomFull, DocId, DocDate, DocNumber
)
SELECT NomFull, DocDate, DocNumber, Qty, Amount
FROM per_doc
WHERE rn = 1
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
            "tag": (r.get("Tag") or "").strip(),
            "quantity": _f(r.get("Quantity")),
        }
        for r in rows
    ]


# Автоматические смены россыпи: бирка ББА у бригады БА, БПВ у бригады ПВ.
AUTO_SHIFT_TAGS = frozenset({"БПВ", "ББА"})


def _worked_shift_ids(shifts: list[dict[str, Any]]) -> set[str]:
    """Смены, в которых есть строка не с биркой БПВ/ББА."""
    ids: set[str] = set()
    for r in shifts:
        if (r.get("tag") or "").strip() in AUTO_SHIFT_TAGS:
            continue
        ids.add(f"{r['date']}|{r['number']}")
    return ids


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
            "vehicle": (r.get("Vehicle") or "").strip(),
            "label": vesy_soft_axis_label((r.get("VesySoftNumber") or "").strip()),
            "bale_weight": _f(r.get("BaleWeight")),
            "scale_weight": _f(r.get("ScaleWeight")),
            "nomenclature": (r.get("Nomenclature") or "").strip() or "—",
            "line_qty": _f(r.get("LineQty")),
        }
        for r in rows
    ]


def fetch_selection(date_from: date, date_to: date) -> dict[str, Any]:
    """Приехавшее ТКО (нетто, кг) и отобранное по сменам (кг) по дням периода."""
    d0, d1 = _bounds(date_from, date_to)
    with connect(DB_UAT) as conn:
        cur = conn.cursor(as_dict=True)
        cur.execute(SELECTION_QUERY, (d0, d1, d0, d1))
        rows = cur.fetchall() or []
    days = []
    arrived = 0.0
    selected = 0.0
    for r in rows:
        tko = _f(r.get("TkoNettoKg"))
        out = _f(r.get("OutputKg"))
        arrived += tko
        selected += out
        days.append(
            {
                "date": _serialize(r.get("DayDate")),
                "arrived_kg": round(tko, 3),
                "selected_kg": round(out, 3),
                "pct": round(out / tko * 100.0, 2) if tko else None,
            }
        )
    return {
        "days": days,
        "arrived_t": round(arrived / 1000.0, 1),
        "selected_t": round(selected / 1000.0, 1),
        "pct": round(selected / arrived * 100.0, 2) if arrived else None,
    }


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


def fetch_vid_gruza_map() -> list[dict[str, str]]:
    """Пары УАТ: номенклатура ↔ уатВидГруза (для стыковки с номенклатурой БП)."""
    with connect(DB_UAT) as conn:
        cur = conn.cursor(as_dict=True)
        cur.execute(VID_GRUZA_QUERY)
        rows = cur.fetchall() or []
    out: list[dict[str, str]] = []
    for r in rows:
        nom = (r.get("NomUat") or "").strip()
        vid = (r.get("VidGruza") or "").strip()
        if nom and vid:
            out.append({"nom_uat": nom, "vid_gruza": vid})
    return out


def _vid_gruza_indexes(
    pairs: list[dict[str, str]],
) -> tuple[dict[str, str], dict[str, str]]:
    """norm(vid_gruza)→nom_uat и norm(nom_uat)→vid_gruza."""
    by_vid: dict[str, str] = {}
    by_uat: dict[str, str] = {}
    for p in pairs:
        vk = _norm_match_key(p["vid_gruza"])
        uk = _norm_match_key(p["nom_uat"])
        by_vid.setdefault(vk, p["nom_uat"])
        by_uat.setdefault(uk, p["vid_gruza"])
    return by_vid, by_uat


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


def fetch_last_sale_prices() -> dict[str, float]:
    """₽/т по очищенному имени БП: сумма ÷ количество в последнем проведённом документе."""
    with connect(DB_BUH) as conn:
        cur = conn.cursor(as_dict=True)
        cur.execute(LAST_SALE_PRICE_QUERY)
        rows = cur.fetchall() or []
    best: dict[str, tuple[str, float]] = {}
    for r in rows:
        full = (r.get("NomFull") or "").strip()
        key = _norm_match_key(clean_buh_name(full) or full)
        if not key:
            continue
        qty = _f(r.get("Qty"))
        if qty <= 0:
            continue
        stamp = _serialize(r.get("DocDate")) or ""
        price = _f(r.get("Amount")) / qty
        prev = best.get(key)
        if prev is None or stamp > prev[0]:
            best[key] = (stamp, price)
    return {k: v[1] for k, v in best.items()}


def _build_production(shifts: list[dict[str, Any]]) -> dict[str, Any]:
    by_day_brigade: dict[str, dict[str, float]] = {}
    by_workshop: dict[str, float] = {}
    brigades: set[str] = set()

    for r in shifts:
        day = r["date"] or "—"
        brig = r["brigade"]
        brigades.add(brig)
        by_day_brigade.setdefault(day, {})
        by_day_brigade[day][brig] = by_day_brigade[day].get(brig, 0.0) + r["quantity"]
        by_workshop[r["workshop"]] = by_workshop.get(r["workshop"], 0.0) + r["quantity"]

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
        "shift_count": len(_worked_shift_ids(shifts)),
        "total_kg": round(sum(by_workshop.values()), 3),
        "note": "Выработка включает россыпные фракции",
    }


def _group_shipment_docs(ship_rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    docs: dict[str, dict[str, Any]] = {}
    for r in ship_rows:
        key = f"{r['date']}|{r['number']}"
        doc = docs.setdefault(
            key,
            {
                "date": r["date"],
                "number": r["number"],
                "vesy_soft_number": r.get("vesy_soft_number") or "",
                "vehicle": r.get("vehicle") or "",
                "label": r.get("label") or vesy_soft_axis_label(r.get("vesy_soft_number") or ""),
                "scale_weight": r["scale_weight"],
                "lines": [],
            },
        )
        if r["line_qty"]:
            doc["lines"].append({"nomenclature": r["nomenclature"], "qty": r["line_qty"]})
    return docs


def _shipment_is_weighed(doc: dict[str, Any]) -> bool:
    """Без номера весов и с нулевым весом рейс ещё не взвешен: в усушку он дал бы 100% потери."""
    number = (doc.get("vesy_soft_number") or "").strip()
    return bool(number) and doc["scale_weight"] > 0


def shipment_scale_totals(ship_rows: list[dict[str, Any]]) -> dict[str, float]:
    """Вывезено: все отгрузки, вес по весам один раз на документ."""
    docs = _group_shipment_docs(ship_rows)
    return {
        "trip_count": float(len(docs)),
        "scale_kg": sum(d["scale_weight"] for d in docs.values()),
    }


def _build_shrinkage(ship_rows: list[dict[str, Any]]) -> dict[str, Any]:
    # Коэффициент рейса = вес по весам / сумма весов тюков по биркам.
    # Вес фракции по весам = её вес по биркам × коэффициент.
    # Усушка фракции = бирки − вес по весам. Поле «Расхождение» не используем.
    docs = _group_shipment_docs(ship_rows)

    trips = []
    frac_agg: dict[str, dict[str, float]] = {}
    pcts_for_median: list[float] = []

    for doc in docs.values():
        if not _shipment_is_weighed(doc):
            continue
        by_name: dict[str, float] = {}
        for line in doc["lines"]:
            name = line["nomenclature"] if line["nomenclature"] and line["nomenclature"] != "—" else "—"
            by_name[name] = by_name.get(name, 0.0) + line["qty"]
        bale = sum(by_name.values())
        if bale <= 0:
            continue
        scale = doc["scale_weight"]
        coeff = scale / bale
        shrink_kg = bale - scale
        shrink_pct = shrink_kg / bale * 100.0
        named = {n for n in by_name if n != "—"}
        mixed = len(named) > 1
        anomaly = abs(shrink_kg) / bale > 0.15

        fractions = []
        for name, qty in sorted(by_name.items(), key=lambda x: -x[1]):
            if name == "—":
                continue
            scale_part = qty * coeff
            shrink_part = qty - scale_part
            fractions.append(
                {
                    "name": name,
                    "kg": round(qty, 3),
                    "scale_kg": round(scale_part, 3),
                    "shrink_kg": round(shrink_part, 3),
                }
            )
            fa = frac_agg.setdefault(
                name,
                {"trips": 0.0, "bale": 0.0, "scale": 0.0, "shrink_kg": 0.0},
            )
            fa["trips"] += qty / bale
            fa["bale"] += qty
            fa["scale"] += scale_part
            fa["shrink_kg"] += shrink_part

        trips.append(
            {
                "date": doc["date"],
                "number": doc["number"],
                "vesy_soft_number": doc["vesy_soft_number"],
                "vehicle": doc["vehicle"],
                "fractions": fractions,
                "bale_weight": round(bale, 3),
                "scale_weight": round(scale, 3),
                "shrink_kg": round(shrink_kg, 3),
                "shrink_pct": round(shrink_pct, 2),
                "mixed": mixed,
                "anomaly": anomaly,
                "label": doc["label"],
            }
        )
        if not anomaly:
            pcts_for_median.append(shrink_pct)

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


def _prices_by_uat_name(
    prices_buh: dict[str, float],
    by_uat: dict[str, str],
) -> dict[str, float]:
    """Цены БП, доступные по имени номенклатуры УАТ через уатВидГруза."""
    out = dict(prices_buh)
    for uat_key, vid in by_uat.items():
        price = prices_buh.get(_norm_match_key(vid))
        if price is not None:
            out[uat_key] = price
            out[(vid or "").strip().lower()] = price
    return out


def _build_warehouse(wh: list[dict[str, Any]], prices: dict[str, float]) -> dict[str, Any]:
    total = sum(x["quantity"] for x in wh) or 1.0
    rows = []
    total_rub = 0.0
    for x in wh:
        key = _norm_match_key(x["nomenclature"])
        price = prices.get(key, prices.get(x["nomenclature"].lower(), 0.0))
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


def _sale_uat_name(fraction: str, by_vid: dict[str, str]) -> str:
    """Имя для продаж: номенклатура УАТ через уатВидГруза, иначе очищенное имя БП."""
    key = _norm_match_key(fraction)
    return by_vid.get(key) or fraction


def _build_sales(
    sales: list[dict[str, Any]],
    by_vid: dict[str, str] | None = None,
) -> dict[str, Any]:
    by_vid = by_vid or {}
    by_frac: dict[str, dict[str, float]] = {}
    by_buyer: dict[str, float] = {}
    for r in sales:
        name = _sale_uat_name(r["fraction"], by_vid)
        f = by_frac.setdefault(name, {"tons": 0.0, "rub": 0.0})
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


def _build_prices(
    monthly: list[dict[str, Any]],
    sales: list[dict[str, Any]] | None = None,
    by_vid: dict[str, str] | None = None,
) -> dict[str, Any]:
    # ряды — по фракциям из продаж периода; имя — номенклатура УАТ через уатВидГруза
    by_vid = by_vid or {}
    sales_names: dict[str, str] = {}
    for r in sales or []:
        fr = (r.get("fraction") or "").strip()
        if fr and fr != "—":
            sales_names.setdefault(_norm_match_key(fr), fr)

    months = sorted({m["month"] for m in monthly if m["month"]})
    if len(months) > 12:
        months = months[-12:]
    data: dict[str, dict[str, list[float]]] = {}
    for r in monthly:
        if r["month"] not in months:
            continue
        fr = (r.get("fraction") or "").strip()
        if not fr:
            continue
        fr_key = _norm_match_key(fr)
        if sales_names and fr_key not in sales_names:
            continue
        # БП NomKey = уатВидГруза → показываем номенклатуру УАТ
        display = by_vid.get(fr_key) or sales_names.get(fr_key, fr)
        bucket = data.setdefault(display, {})
        prev = bucket.get(r["month"], [0.0, 0.0])
        bucket[r["month"]] = [prev[0] + r["amount"], prev[1] + r["quantity"]]

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

    # все позиции продаж; полные ряды — первыми
    series = sorted(series, key=lambda s: -sum(1 for x in s["indexes"] if x is not None))
    return {"months": months, "series": series}


def build_dashboard(
    date_from: date,
    date_to: date,
) -> dict[str, Any]:
    shifts = fetch_shifts(date_from, date_to)
    ships = fetch_shipments(date_from, date_to)
    selection = fetch_selection(date_from, date_to)
    warehouse = fetch_warehouse()
    vid_pairs = fetch_vid_gruza_map()
    by_vid, by_uat = _vid_gruza_indexes(vid_pairs)

    sales: list[dict[str, Any]] = []
    monthly: list[dict[str, Any]] = []
    last_prices: dict[str, float] = {}
    sales_error = None
    try:
        sales = fetch_sales(date_from, date_to)
        monthly = fetch_sales_monthly(12)
        last_prices = fetch_last_sale_prices()
    except Exception as exc:  # noqa: BLE001
        sales_error = str(exc)

    production = _build_production(shifts)
    shipped = shipment_scale_totals(ships)
    shrinkage = _build_shrinkage(ships)
    prices_map = _prices_by_uat_name(last_prices, by_uat)

    wh = _build_warehouse(warehouse, prices_map)
    sales_block = _build_sales(sales, by_vid)
    prices_block = _build_prices(monthly, sales, by_vid)

    # KPI плитки по ТЗ
    prod_kg = production["total_kg"]
    ship_kg = shipped["scale_kg"]
    # усушка: сумма весов бирок − вес по весам, без невзвешенных рейсов
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
        "trip_count": int(shipped["trip_count"]),
        "sold_rub": sales_block["total_rub"],
        "sold_tons": round(sales_block["total_tons"], 1),
        "shrink_pct": round(shrink_pct, 1),
        "shrink_kg": round(shrink_kg, 3),
        "shrink_rub": round(shrink_rub, 2),
    }

    return {
        "kpis": kpis,
        "selection": selection,
        "production": production,
        "shrinkage": shrinkage,
        "warehouse": wh,
        "prices": prices_block,
        "sales": sales_block,
        "sales_error": sales_error,
        "rows": shifts,
    }
