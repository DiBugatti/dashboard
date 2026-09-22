# -*- coding: utf-8 -*-
"""Сборка PDF-презентации: backend дашборда ВМР."""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
from PIL import Image as PILImage
from reportlab.lib.colors import Color, HexColor, white, black
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

ROOT = Path(__file__).resolve().parent
ASSETS = ROOT / "assets"
OUT = ROOT / "backend-vmr-presentation.pdf"
PLITKA = Path(r"C:\vs") / "плитка.png"

# palette
BG = HexColor("#0f1419")
CARD = HexColor("#1a2332")
ACCENT = HexColor("#3dba7a")
ACCENT2 = HexColor("#5bb8d4")
MUTED = HexColor("#8a9bb0")
LIGHT = HexColor("#e8eef5")
WARN = HexColor("#e2b45a")
LINE = HexColor("#2a3a4d")

PAGE = landscape(A4)
W, H = PAGE


def register_fonts() -> tuple[str, str]:
    candidates = [
        (r"C:\Windows\Fonts\segoeui.ttf", r"C:\Windows\Fonts\segoeuib.ttf"),
        (r"C:\Windows\Fonts\arial.ttf", r"C:\Windows\Fonts\arialbd.ttf"),
        (r"C:\Windows\Fonts\calibri.ttf", r"C:\Windows\Fonts\calibrib.ttf"),
    ]
    for regular, bold in candidates:
        if Path(regular).exists() and Path(bold).exists():
            pdfmetrics.registerFont(TTFont("UI", regular))
            pdfmetrics.registerFont(TTFont("UI-Bold", bold))
            return "UI", "UI-Bold"
    return "Helvetica", "Helvetica-Bold"


FONT, FONT_B = register_fonts()


def draw_bg(c: canvas.Canvas) -> None:
    c.setFillColor(BG)
    c.rect(0, 0, W, H, fill=1, stroke=0)
    # subtle top accent bar
    c.setFillColor(ACCENT)
    c.rect(0, H - 4 * mm, W, 4 * mm, fill=1, stroke=0)


def header(c: canvas.Canvas, title: str, subtitle: str = "", page: int = 0, total: int = 0) -> None:
    draw_bg(c)
    c.setFillColor(LIGHT)
    c.setFont(FONT_B, 22)
    c.drawString(18 * mm, H - 18 * mm, title)
    if subtitle:
        c.setFillColor(MUTED)
        c.setFont(FONT, 11)
        c.drawString(18 * mm, H - 26 * mm, subtitle)
    if total:
        c.setFillColor(MUTED)
        c.setFont(FONT, 9)
        c.drawRightString(W - 18 * mm, 8 * mm, f"{page} / {total}")


def card(c: canvas.Canvas, x, y, w, h, radius=6) -> None:
    c.setFillColor(CARD)
    c.roundRect(x, y, w, h, radius, fill=1, stroke=0)


def bullet(c: canvas.Canvas, x, y, text, size=11, color=LIGHT) -> float:
    c.setFillColor(ACCENT)
    c.circle(x + 2 * mm, y + 1.2 * mm, 1.2 * mm, fill=1, stroke=0)
    c.setFillColor(color)
    c.setFont(FONT, size)
    c.drawString(x + 6 * mm, y, text)
    return y - 7 * mm


# ── diagrams ──────────────────────────────────────────────────────────────


def make_arch_diagram() -> Path:
    """Два независимых контура: MCP (разведка) и SQL (рантайм дашборда)."""
    path = ASSETS / "arch.png"
    fig, ax = plt.subplots(figsize=(12.5, 5.6), dpi=160)
    fig.patch.set_facecolor("#0f1419")
    ax.set_facecolor("#0f1419")
    ax.set_xlim(0, 12.5)
    ax.set_ylim(0, 5.6)
    ax.axis("off")

    # zone labels
    ax.text(0.3, 5.35, "КОНТУР A — разведка (разово / по необходимости)", ha="left",
            color="#5bb8d4", fontsize=9, fontweight="bold")
    ax.text(0.3, 2.55, "КОНТУР B — дашборд в рантайме (без MCP)", ha="left",
            color="#3dba7a", fontsize=9, fontweight="bold")

    # Contour A
    boxes_a = [
        (0.3, 3.5, 2.5, 1.5, "Агент / IDE", "#5bb8d4"),
        (3.3, 3.5, 2.8, 1.5, "MCP odines\n:6003  execute_code", "#5bb8d4"),
        (6.6, 3.5, 2.8, 1.5, "1С · структура\nхранения → имена\n_Document / _Fld", "#e2b45a"),
        (9.9, 3.5, 2.3, 1.5, "маппинг\nв код / docs", "#8a9bb0"),
    ]
    # Contour B
    boxes_b = [
        (0.3, 0.55, 2.5, 1.6, "Браузер\nUI Chart.js", "#3dba7a"),
        (3.3, 0.55, 2.8, 1.6, "Flask + pymssql\n/api/data", "#3dba7a"),
        (6.6, 0.55, 2.8, 1.6, "SQL Server\n192.168.80.10\nУАТ + БП", "#3dba7a"),
        (9.9, 0.55, 2.3, 1.6, "SELECT\nнапрямую", "#3dba7a"),
    ]

    def draw_boxes(boxes):
        for x, y, w, h, label, ec in boxes:
            rect = FancyBboxPatch(
                (x, y), w, h, boxstyle="round,pad=0.05,rounding_size=0.12",
                linewidth=2, edgecolor=ec, facecolor="#1a2332",
            )
            ax.add_patch(rect)
            ax.text(x + w / 2, y + h / 2, label, ha="center", va="center",
                    color="#e8eef5", fontsize=9, fontweight="bold", linespacing=1.3)

    draw_boxes(boxes_a)
    draw_boxes(boxes_b)

    for y in (4.25, 1.35):
        for x0, x1 in ((2.8, 3.3), (6.1, 6.6), (9.4, 9.9)):
            ax.annotate(
                "", xy=(x1, y), xytext=(x0, y),
                arrowprops=dict(arrowstyle="->", color="#8a9bb0", lw=1.6),
            )

    # dashed separator + note: no runtime link
    ax.plot([0.3, 12.2], [3.15, 3.15], color="#2a3a4d", lw=1.2, ls="--")
    ax.text(6.25, 2.85,
            "нет зависимости в рантайме: SQL-запросы дашборда не ходят в MCP и не требуют его",
            ha="center", color="#e2b45a", fontsize=9, fontweight="bold")

    fig.tight_layout(pad=0.3)
    fig.savefig(path, facecolor=fig.get_facecolor(), bbox_inches="tight")
    plt.close(fig)
    return path


def make_mcp_flow() -> Path:
    path = ASSETS / "mcp_flow.png"
    fig, ax = plt.subplots(figsize=(12.5, 4.0), dpi=160)
    fig.patch.set_facecolor("#0f1419")
    ax.set_facecolor("#0f1419")
    ax.set_xlim(0, 12.5)
    ax.set_ylim(0, 4.0)
    ax.axis("off")

    steps = [
        (0.3, "get_metadata\nРасширение1", "#5bb8d4"),
        (3.2, "execute_code\nПолучитьСтруктуру\nХраненияБазыДанных", "#3dba7a"),
        (6.4, "маппинг\nак_Смены →\n_Document18335", "#e2b45a"),
        (9.4, "имена таблиц\nи полей\nзафиксированы", "#5bb8d4"),
    ]
    for i, (x, label, ec) in enumerate(steps):
        rect = FancyBboxPatch(
            (x, 1.0), 2.7, 2.0, boxstyle="round,pad=0.05,rounding_size=0.12",
            linewidth=2, edgecolor=ec, facecolor="#1a2332",
        )
        ax.add_patch(rect)
        ax.text(x + 1.35, 2.0, label, ha="center", va="center",
                color="#e8eef5", fontsize=9.5, fontweight="bold", linespacing=1.3)
        ax.text(x + 1.35, 3.25, f"{i + 1}", ha="center", va="center",
                color=ec, fontsize=14, fontweight="bold")
        if i < len(steps) - 1:
            ax.annotate(
                "", xy=(x + 2.85, 2.0), xytext=(x + 2.7, 2.0),
                arrowprops=dict(arrowstyle="->", color="#8a9bb0", lw=2),
            )

    ax.text(6.25, 0.35,
            "MCP нужен только чтобы узнать структуру SQL. Дальше дашборд ходит в СУБД сам.",
            ha="center", color="#e2b45a", fontsize=10, fontweight="bold")
    fig.tight_layout(pad=0.3)
    fig.savefig(path, facecolor=fig.get_facecolor(), bbox_inches="tight")
    plt.close(fig)
    return path


def make_independence_diagram() -> Path:
    path = ASSETS / "independence.png"
    fig, ax = plt.subplots(figsize=(12.5, 4.2), dpi=160)
    fig.patch.set_facecolor("#0f1419")
    ax.set_facecolor("#0f1419")
    ax.set_xlim(0, 12.5)
    ax.set_ylim(0, 4.2)
    ax.axis("off")

    # left MCP
    left = FancyBboxPatch(
        (0.4, 0.8), 5.0, 2.8, boxstyle="round,pad=0.06,rounding_size=0.15",
        linewidth=2.5, edgecolor="#5bb8d4", facecolor="#1a2332",
    )
    ax.add_patch(left)
    ax.text(2.9, 3.2, "MCP odines", ha="center", color="#5bb8d4",
            fontsize=13, fontweight="bold")
    ax.text(2.9, 2.2,
            "роль: разведка структуры\n"
            "ПолучитьСтруктуруХранения…\n"
            "имена _Document / _Fld\n"
            "не участвует в /api/data",
            ha="center", va="center", color="#e8eef5", fontsize=10, linespacing=1.4)

    # right SQL
    right = FancyBboxPatch(
        (7.1, 0.8), 5.0, 2.8, boxstyle="round,pad=0.06,rounding_size=0.15",
        linewidth=2.5, edgecolor="#3dba7a", facecolor="#1a2332",
    )
    ax.add_patch(right)
    ax.text(9.6, 3.2, "SQL дашборда", ha="center", color="#3dba7a",
            fontsize=13, fontweight="bold")
    ax.text(9.6, 2.2,
            "роль: данные для UI\npymssql → 192.168.80.10\n"
            "SELECT в db.py\nне требует сессии MCP",
            ha="center", va="center", color="#e8eef5", fontsize=10, linespacing=1.4)

    # crossed / no link
    ax.annotate(
        "", xy=(7.0, 2.2), xytext=(5.5, 2.2),
        arrowprops=dict(arrowstyle="-", color="#e2b45a", lw=2, ls="--"),
    )
    ax.text(6.25, 2.55, "✗ нет", ha="center", color="#e2b45a",
            fontsize=11, fontweight="bold")
    ax.text(6.25, 0.35,
            "Отключение MCP не останавливает дашборд. SQL-запросы на MCP не влияют.",
            ha="center", color="#e2b45a", fontsize=10, fontweight="bold")
    fig.tight_layout(pad=0.3)
    fig.savefig(path, facecolor=fig.get_facecolor(), bbox_inches="tight")
    plt.close(fig)
    return path


def make_sql_schema() -> Path:
    path = ASSETS / "sql_schema.png"
    fig, ax = plt.subplots(figsize=(12.5, 5.4), dpi=160)
    fig.patch.set_facecolor("#0f1419")
    ax.set_facecolor("#0f1419")
    ax.set_xlim(0, 12.5)
    ax.set_ylim(0, 5.4)
    ax.axis("off")

    def table(x, y, w, h, title, rows, ec):
        rect = FancyBboxPatch(
            (x, y), w, h, boxstyle="round,pad=0.04,rounding_size=0.1",
            linewidth=1.8, edgecolor=ec, facecolor="#1a2332",
        )
        ax.add_patch(rect)
        ax.text(x + w / 2, y + h - 0.28, title, ha="center", va="top",
                color=ec, fontsize=9, fontweight="bold")
        ax.text(x + 0.12, y + h - 0.55, "\n".join(rows), ha="left", va="top",
                color="#e8eef5", fontsize=7.5, family="monospace", linespacing=1.35)

    # UAT
    ax.text(3.5, 5.15, "УАТ  msk_uat_copy3", ha="center", color="#3dba7a", fontsize=11, fontweight="bold")
    table(0.2, 2.7, 3.0, 2.2, "_Document18335  ак_Смены",
          ["_Date_Time  (+2000 лет)", "_Fld18344RRef  бригада", "_Fld18341RRef  цех",
           "_Marked  удаление", "_IDRRef"], "#3dba7a")
    table(3.4, 2.7, 3.2, 2.2, "_Document18335_VT18350  Товары",
          ["_Document18335_IDRRef", "_Fld18354RRef  номенклатура",
           "_Fld18353  количество", "_LineNo18351"], "#5bb8d4")
    table(0.2, 0.2, 3.0, 2.2, "_Document18337  ак_Отгрузка",
          ["_Fld18387  вес тюков", "_Fld18389  вес весовой",
           "усушка = тюки − весовая"], "#e2b45a")
    table(3.4, 0.2, 3.2, 2.2, "_Document18336  ак_Тюк",
          ["статус EnumOrder=1", "«На складе»", "остаток на сегодня"], "#9b7edc")

    # BP
    ax.text(9.5, 5.15, "БП  msk_buh_copy", ha="center", color="#5bb8d4", fontsize=11, fontweight="bold")
    table(7.0, 2.5, 5.1, 2.4, "_Document637  РеализацияТоваровУслуг",
          ["_Posted = 0x01  проведён", "ТЧ: qty / price / amount",
           "_Reference204  номенклатура", "_Reference177  контрагент",
           "join УАТ↔БП по очищенному имени"], "#5bb8d4")
    table(7.0, 0.2, 5.1, 2.0, "Справочники УАТ",
          ["_Reference106X1  бригады", "_Reference90  подразделения",
           "_Reference82  номенклатура / фракции"], "#8a9bb0")

    # link arrow
    ax.annotate("", xy=(7.0, 3.5), xytext=(6.6, 3.5),
                arrowprops=dict(arrowstyle="->", color="#8a9bb0", lw=1.5))
    ax.text(6.8, 3.7, "имя", color="#8a9bb0", fontsize=7, ha="center")

    fig.tight_layout(pad=0.2)
    fig.savefig(path, facecolor=fig.get_facecolor(), bbox_inches="tight")
    plt.close(fig)
    return path


def make_python_stack() -> Path:
    path = ASSETS / "python_stack.png"
    fig, ax = plt.subplots(figsize=(12.5, 3.6), dpi=160)
    fig.patch.set_facecolor("#0f1419")
    ax.set_facecolor("#0f1419")
    ax.set_xlim(0, 12.5)
    ax.set_ylim(0, 3.6)
    ax.axis("off")

    layers = [
        (0.4, ".env\nSQL_SERVER\nSQL_PASSWORD", "#e2b45a"),
        (3.0, "db.py\npymssql.connect\nbuild_dashboard()", "#3dba7a"),
        (5.8, "app.py\nFlask\nGET /api/data", "#5bb8d4"),
        (8.4, "JSON\nkpis / production\nshrinkage / sales", "#9b7edc"),
        (10.6, "Chart.js\nKPI + 5 блоков\n:5050", "#c9886a"),
    ]
    for i, (x, label, ec) in enumerate(layers):
        w = 2.2 if i < 4 else 1.7
        rect = FancyBboxPatch(
            (x, 0.7), w, 2.2, boxstyle="round,pad=0.05,rounding_size=0.12",
            linewidth=2, edgecolor=ec, facecolor="#1a2332",
        )
        ax.add_patch(rect)
        ax.text(x + w / 2, 1.8, label, ha="center", va="center",
                color="#e8eef5", fontsize=9, fontweight="bold", linespacing=1.35)
        if i < len(layers) - 1:
            ax.annotate("", xy=(x + w + 0.15, 1.8), xytext=(x + w, 1.8),
                        arrowprops=dict(arrowstyle="->", color="#8a9bb0", lw=2))

    fig.tight_layout(pad=0.3)
    fig.savefig(path, facecolor=fig.get_facecolor(), bbox_inches="tight")
    plt.close(fig)
    return path


def draw_image(c: canvas.Canvas, path: Path, x, y, max_w, max_h) -> None:
    if not path.exists():
        return
    img = PILImage.open(path)
    iw, ih = img.size
    scale = min(max_w / iw, max_h / ih)
    dw, dh = iw * scale, ih * scale
    c.drawImage(str(path), x + (max_w - dw) / 2, y + (max_h - dh) / 2,
                width=dw, height=dh, preserveAspectRatio=True, mask="auto")


# ── slides ────────────────────────────────────────────────────────────────


def slide_title(c: canvas.Canvas, page: int, total: int) -> None:
    draw_bg(c)
    c.setFillColor(ACCENT)
    c.setFont(FONT_B, 12)
    c.drawString(18 * mm, H - 28 * mm, "ДАШБОРД ВМР · МСК")
    c.setFillColor(LIGHT)
    c.setFont(FONT_B, 32)
    c.drawString(18 * mm, H - 48 * mm, "Backend проекта:")
    c.drawString(18 * mm, H - 62 * mm, "MCP для структуры, SQL для данных")
    c.setFillColor(MUTED)
    c.setFont(FONT, 14)
    c.drawString(18 * mm, H - 78 * mm, "Как через MCP узнали таблицы хранения, подключились к SQL Server")
    c.drawString(18 * mm, H - 86 * mm, "и вывели показатели в визуал — без зависимости дашборда от MCP")

    card(c, 18 * mm, 28 * mm, W - 36 * mm, 42 * mm)
    items = [
        "MCP — только чтобы узнать структуру SQL (имена таблиц и полей 1С)",
        "Дашборд ходит в SQL Server напрямую: запросы не зависят от MCP",
        "Базы: msk_uat_copy3 (УАТ) + msk_buh_copy (БП) на 192.168.80.10",
    ]
    y = 58 * mm
    for t in items:
        y = bullet(c, 26 * mm, y, t, size=12)
        y -= 2 * mm

    c.setFillColor(MUTED)
    c.setFont(FONT, 9)
    c.drawRightString(W - 18 * mm, 8 * mm, f"{page} / {total}")
    c.showPage()


def slide_arch(c: canvas.Canvas, page: int, total: int, img: Path) -> None:
    header(c, "Архитектура backend", "Два контура: MCP для разведки, SQL для дашборда", page, total)
    draw_image(c, img, 10 * mm, 18 * mm, W - 20 * mm, H - 50 * mm)
    c.showPage()


def slide_mcp(c: canvas.Canvas, page: int, total: int, img: Path) -> None:
    header(c, "Шаг 1. MCP → структура SQL", "MCP использовали, чтобы узнать, как 1С хранит данные в СУБД", page, total)
    draw_image(c, img, 10 * mm, H / 2 - 5 * mm, W - 20 * mm, H / 2 - 25 * mm)

    card(c, 18 * mm, 16 * mm, W - 36 * mm, 55 * mm)
    y = 60 * mm
    points = [
        "Транспорт HTTP: http://192.168.80.15:6003/mcp  (Authorization: Bearer …)",
        "Инструменты: execute_code, get_metadata (extension_name = «Расширение1»)",
        "Ключ: ПолучитьСтруктуруХраненияБазыДанных(, Истина) → _Document… / _Fld…",
        "Пример: Документ.ак_Смены → _Document18335, ТЧ Товары → _Document18335_VT18350",
        "После маппинга MCP для работы дашборда не нужен — имена уже в db.py",
    ]
    for p in points:
        y = bullet(c, 26 * mm, y, p, size=10)
        y -= 1 * mm
    c.showPage()


def slide_independence(c: canvas.Canvas, page: int, total: int, img: Path) -> None:
    header(
        c,
        "MCP и SQL независимы",
        "Запросы дашборда не влияют на MCP и не зависят от его подключения",
        page,
        total,
    )
    draw_image(c, img, 10 * mm, H / 2 - 8 * mm, W - 20 * mm, 55 * mm)

    card(c, 18 * mm, 16 * mm, W - 36 * mm, 58 * mm)
    y = 62 * mm
    points = [
        "MCP — инструмент разработки/разведки: один раз узнали структуру хранения в SQL",
        "Дашборд (Flask + pymssql) подключается к 192.168.80.10 сам, через .env",
        "SELECT в db.py и /api/data не вызывают MCP и не держат сессию 1С",
        "Можно выключить MCP — KPI и графики продолжают работать, пока доступен SQL",
        "Обратно: нагрузка SQL дашборда не затрагивает MCP-сервер odines",
    ]
    for p in points:
        y = bullet(c, 26 * mm, y, p, size=10)
        y -= 1 * mm
    c.showPage()


def slide_sql_connect(c: canvas.Canvas, page: int, total: int) -> None:
    header(c, "Шаг 2. Подключение к SQL Server", "Прямой доступ дашборда — без MCP", page, total)

    # left card
    card(c, 18 * mm, 55 * mm, 120 * mm, 85 * mm)
    c.setFillColor(WARN)
    c.setFont(FONT_B, 13)
    c.drawString(26 * mm, 128 * mm, "Разделение ролей хостов")
    y = 115 * mm
    for t in [
        "192.168.80.15 — сервер приложений 1С",
        "Порты 1433/1434 на нём закрыты",
        "СУБД живёт на 192.168.80.10",
        "УАТ: msk_uat_copy3",
        "БП:  msk_buh_copy",
        "Логин: user1c  (пароль в .env / DPAPI)",
    ]:
        y = bullet(c, 26 * mm, y, t, size=11)
        y -= 1.5 * mm

    # right card
    card(c, 145 * mm, 55 * mm, W - 163 * mm, 85 * mm)
    c.setFillColor(ACCENT2)
    c.setFont(FONT_B, 13)
    c.drawString(153 * mm, 128 * mm, "Клиенты")
    y = 115 * mm
    for t in [
        "Python: pymssql (UTF-8)",
        "без вызовов MCP odines",
        "PowerShell: tools/sql-1c.ps1",
        "Часто нужен -ReadWriteIntent",
        "Flask читает SQL_PASSWORD",
        "из dashboard/.env",
    ]:
        y = bullet(c, 153 * mm, y, t, size=11)
        y -= 1.5 * mm

    card(c, 18 * mm, 16 * mm, W - 36 * mm, 32 * mm)
    c.setFillColor(MUTED)
    c.setFont(FONT, 10)
    c.drawString(26 * mm, 38 * mm, "Фрагмент подключения (db.py) — только SQL, MCP не участвует:")
    c.setFillColor(LIGHT)
    c.setFont(FONT, 9)
    c.drawString(26 * mm, 28 * mm,
                 "pymssql.connect(server='192.168.80.10', user='user1c', password=..., database='msk_uat_copy3', charset='utf8')")
    c.drawString(26 * mm, 20 * mm,
                 "Даты 1С в SQL со смещением +2000 лет → везде DATEADD(year, -2000, _Date_Time)")
    c.showPage()


def slide_schema(c: canvas.Canvas, page: int, total: int, img: Path) -> None:
    header(c, "Шаг 3. Схема хранения", "Объекты 1С → таблицы SQL", page, total)
    draw_image(c, img, 8 * mm, 12 * mm, W - 16 * mm, H - 42 * mm)
    c.showPage()


def slide_queries(c: canvas.Canvas, page: int, total: int) -> None:
    header(c, "Шаг 4. Прямые SQL-запросы", "Что считает backend в db.py — без обращения к MCP", page, total)

    queries = [
        ("SHIFTS_QUERY", "ак_Смены + ТЧ Товары", "выработка, бригады, цеха, фракции"),
        ("SHIPMENTS_QUERY", "ак_Отгрузка", "вывезено по весовой, усушка по рейсам"),
        ("WAREHOUSE_QUERY", "ак_Тюк + статус", "остаток склада «на сегодня»"),
        ("SALES_PERIOD_QUERY", "Реализация (БП)", "выручка, тонны, покупатели"),
        ("SALES_12M_QUERY", "Реализация 12 мес.", "индекс цен по фракциям"),
    ]
    y0 = H - 42 * mm
    for i, (name, obj, role) in enumerate(queries):
        y = y0 - i * 24 * mm
        card(c, 18 * mm, y - 4 * mm, W - 36 * mm, 20 * mm)
        c.setFillColor(ACCENT if i % 2 == 0 else ACCENT2)
        c.setFont(FONT_B, 11)
        c.drawString(26 * mm, y + 8 * mm, name)
        c.setFillColor(LIGHT)
        c.setFont(FONT, 10)
        c.drawString(26 * mm, y + 1 * mm, f"{obj}  ·  {role}")

    c.showPage()


def slide_python_ui(c: canvas.Canvas, page: int, total: int, img: Path) -> None:
    header(c, "Шаг 5. Python → API → визуал", "Flask отдаёт JSON, фронт рисует KPI и блоки", page, total)
    draw_image(c, img, 10 * mm, H / 2 + 5 * mm, W - 20 * mm, 55 * mm)

    card(c, 18 * mm, 16 * mm, 120 * mm, 70 * mm)
    c.setFillColor(ACCENT)
    c.setFont(FONT_B, 12)
    c.drawString(26 * mm, 75 * mm, "API")
    y = 62 * mm
    for t in [
        "GET /  — HTML дашборд",
        "GET /api/data?from=&to= — JSON",
        "build_dashboard(from, to) агрегирует",
        "границу «по» делает exclusive (+1 день)",
        "хост: 127.0.0.1:5050",
    ]:
        y = bullet(c, 26 * mm, y, t, size=10)
        y -= 1 * mm

    card(c, 145 * mm, 16 * mm, W - 163 * mm, 70 * mm)
    c.setFillColor(ACCENT2)
    c.setFont(FONT_B, 12)
    c.drawString(153 * mm, 75 * mm, "UI-блоки")
    y = 62 * mm
    for t in [
        "4 KPI-плитки",
        "Производство (дни/бригады)",
        "Усушка по рейсам",
        "Склад / Цены / Продажи",
        "Chart.js + пресеты периода",
    ]:
        y = bullet(c, 153 * mm, y, t, size=10)
        y -= 1 * mm
    c.showPage()


def slide_kpi(c: canvas.Canvas, page: int, total: int) -> None:
    header(c, "Визуал KPI (из макета)", "Целевые плитки, которые кормит backend", page, total)
    if PLITKA.exists():
        draw_image(c, PLITKA, 15 * mm, 20 * mm, W - 30 * mm, H - 55 * mm)
    else:
        c.setFillColor(MUTED)
        c.setFont(FONT, 12)
        c.drawCentredString(W / 2, H / 2, "файл плитка.png не найден")
    c.showPage()


def slide_formulas(c: canvas.Canvas, page: int, total: int) -> None:
    header(c, "Формулы показателей", "Как Python считает KPI из сырых строк SQL", page, total)
    rows = [
        ("Выработка, т", "SUM(кол-во строк смен) / 1000"),
        ("Вывезено, т", "SUM(вес весовой отгрузки) / 1000"),
        ("Усушка, кг", "SUM(вес тюков − вес весовой)"),
        ("Усушка, %", "(тюки − весовая) / тюки × 100"),
        ("Усушка, ₽", "усушка_т × средняя цена корзины продаж"),
        ("Индекс цены", "цена_месяца / цена_базы × 100"),
        ("Доля покупателя", "сумма контрагента / выручка периода"),
    ]
    y0 = H - 40 * mm
    for i, (k, v) in enumerate(rows):
        y = y0 - i * 18 * mm
        card(c, 18 * mm, y - 3 * mm, W - 36 * mm, 15 * mm)
        c.setFillColor(ACCENT)
        c.setFont(FONT_B, 11)
        c.drawString(26 * mm, y + 2 * mm, k)
        c.setFillColor(LIGHT)
        c.setFont(FONT, 11)
        c.drawString(70 * mm, y + 2 * mm, v)
    c.showPage()


def slide_summary(c: canvas.Canvas, page: int, total: int) -> None:
    header(c, "Итог", "Что получилось на backend", page, total)

    cards = [
        (18 * mm, "Разведка", [
            "MCP → структура SQL",
            "имена _Document/_Fld",
            "разово, не в рантайме",
        ]),
        (105 * mm, "Доступ", [
            "SQL на .10, не MCP",
            "pymssql + .env",
            "независимый контур",
        ]),
        (192 * mm, "Отдача", [
            "живые SELECT",
            "Flask /api/data",
            "KPI + 5 блоков UI",
        ]),
    ]
    for x, title, items in cards:
        card(c, x, 55 * mm, 78 * mm, 85 * mm)
        c.setFillColor(ACCENT)
        c.setFont(FONT_B, 14)
        c.drawString(x + 8 * mm, 125 * mm, title)
        y = 110 * mm
        for t in items:
            y = bullet(c, x + 8 * mm, y, t, size=11)
            y -= 4 * mm

    card(c, 18 * mm, 18 * mm, W - 36 * mm, 28 * mm)
    c.setFillColor(MUTED)
    c.setFont(FONT, 10)
    c.drawString(26 * mm, 36 * mm, "Документация: dashboard/README.md  ·  контекст: CLAUDE.md  ·  код: app.py, db.py")
    c.setFillColor(LIGHT)
    c.setFont(FONT, 10)
    c.drawString(
        26 * mm,
        26 * mm,
        "MCP — структура; SQL — данные UI. Прототип на live SQL (без OData/витрины). Смены в копии — в основном май–июнь 2026.",
    )
    c.showPage()


def main() -> None:
    ASSETS.mkdir(parents=True, exist_ok=True)
    arch = make_arch_diagram()
    mcp = make_mcp_flow()
    indep = make_independence_diagram()
    schema = make_sql_schema()
    stack = make_python_stack()

    total = 11
    c = canvas.Canvas(str(OUT), pagesize=PAGE)

    slide_title(c, 1, total)
    slide_arch(c, 2, total, arch)
    slide_mcp(c, 3, total, mcp)
    slide_independence(c, 4, total, indep)
    slide_sql_connect(c, 5, total)
    slide_schema(c, 6, total, schema)
    slide_queries(c, 7, total)
    slide_python_ui(c, 8, total, stack)
    slide_kpi(c, 9, total)
    slide_formulas(c, 10, total)
    slide_summary(c, 11, total)

    c.save()
    print(f"OK: {OUT}")


if __name__ == "__main__":
    main()
