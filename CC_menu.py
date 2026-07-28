#!/usr/bin/env python3
"""CC_menu.py — Weekly Russian-language menu generator for Garden of Joy.
Usage: python3 CC_menu.py [--preview] [--export] [--week YYYY-MM-DD]"""

import argparse, json, random, sys, textwrap
from datetime import date, timedelta
from pathlib import Path

HOME = Path.home()
REX = HOME / "Desktop" / "REX"
PREFS = REX / "state" / "menu_preferences.json"
OUTPUT = REX / "output"

# Import meal lists from canonical constants
spec = __import__("importlib.util").util.spec_from_file_location(
    "cc", REX / "CC_menu_constants.py")
cc = __import__("importlib.util").util.module_from_spec(spec)
spec.loader.exec_module(cc)
MEALS = {"mains": cc.ALL_MAINS, "soups": cc.SOUPS, "salads": cc.SALADS}
DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]
DAY_RU = ["ПН", "ВТ", "СР", "ЧТ", "ПТ", "СБ"]

def get_next_monday() -> date:
    today = date.today()
    return today + timedelta(days=(7 - today.weekday()) % 7 or 7)

def load_preferences(ws: date) -> list[dict]:
    if PREFS.exists():
        data = json.loads(PREFS.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else data.get("clients", data)
    random.seed(str(ws))
    names = ["Иванов Иван","Петров Петр","Сидоров Сидор","Кузнецов Алексей",
             "Смирнова Ольга","Попов Дмитрий","Лебедева Мария",
             "Новиков Андрей","Морозова Елена","Волков Сергей"]
    return [{"name": n, **{d: {"main": random.choice(MEALS["mains"]),
                                "soup": random.choice(MEALS["soups"]),
                                "salad": random.choice(MEALS["salads"])}
                           for d in DAYS}} for n in names]

def get_entry(c: dict, d: str) -> dict:
    e = c.get(d, {}) or {}
    return {k: e.get(k,"") or "" for k in ("main","soup","salad")}

def preview(clients: list[dict]):
    nw, cw = 18, 14
    sep = "│"
    rule = "─" * (nw + 1 + (cw + 1) * 18)
    hdr = f"{'Клиент':^{nw}}{sep}" + "".join(
        f"{dr+'_'+l:^{cw}}{sep}" for dr in DAY_RU for l in ["Гл","Суп","Сал"])
    print(f"{rule}\n{hdr}\n{rule}")
    for c in clients:
        r = f"{c['name'][:nw]:^{nw}}{sep}"
        for d in DAYS:
            e = get_entry(c, d)
            for k in ["main","soup","salad"]:
                r += f"{(e[k][:cw] if e[k] else '—'):^{cw}}{sep}"
        print(r)
    print(f"{rule}\n  {len(clients)} клиентов")

def export_pdf(clients: list[dict], ws: date):
    from reportlab.lib.pagesizes import landscape, A3
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    # Register Cyrillic font
    for fp in ["/Library/Fonts/Arial Unicode.ttf",
               "/System/Library/Fonts/Supplemental/Arial Unicode.ttf"]:
        if Path(fp).exists():
            pdfmetrics.registerFont(TTFont("RU", fp)); break
    else:
        pdfmetrics.registerFont(TTFont("RU", "Helvetica"))
    OUTPUT.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(str(OUTPUT / f"menu_{ws.isoformat()}.pdf"),
                            pagesize=landscape(A3), leftMargin=8, rightMargin=8,
                            topMargin=12, bottomMargin=12)
    ps = getSampleStyleSheet()["Normal"]
    ps.fontName, ps.fontSize, ps.leading = "RU", 7, 8
    hdr = [Paragraph("<b>Клиент</b>", ps)]
    for dr in DAY_RU:
        for lbl in ["Главное","Суп","Салат"]:
            hdr.append(Paragraph(f"<b>{dr} {lbl}</b>", ps))
    data = [hdr]
    for c in clients:
        row = [Paragraph(c["name"][:32], ps)]
        for d in DAYS:
            e = get_entry(c, d)
            for k in ["main","soup","salad"]:
                row.append(Paragraph(e[k] if e[k] else "—", ps))
        data.append(row)
    cw = [22] + [36]*18
    t = Table(data, colWidths=cw, repeatRows=1)
    t.setStyle(TableStyle([
        ("FONTNAME",(0,0),(-1,-1),"RU"), ("FONTSIZE",(0,0),(-1,-1),7),
        ("GRID",(0,0),(-1,-1),0.3,colors.grey),
        ("BACKGROUND",(0,0),(-1,0),colors.HexColor("#4472C4")),
        ("TEXTCOLOR",(0,0),(-1,0),colors.white),
        ("ROWBACKGROUNDS",(0,1),(-1,-1),[colors.white,colors.HexColor("#D6E4F0")]),
        ("VALIGN",(0,0),(-1,-1),"MIDDLE"),
        ("ALIGN",(0,0),(-1,-1),"CENTER"),
    ]))
    for i, dr in enumerate(DAY_RU):
        s = 1 + i * 3
        t.setStyle(TableStyle([("SPAN",(s,0),(s+2,0)),
                               ("FONTSIZE",(s,0),(s+2,0),9)]))
    doc.build([t])
    print(f"✅ PDF: {OUTPUT}/menu_{ws.isoformat()}.pdf")

def main():
    p = argparse.ArgumentParser(description="CC_menu.py — Weekly Russian menu generator")
    p.add_argument("--week", help="Week start YYYY-MM-DD (default: next Monday)")
    p.add_argument("--preview", action="store_true", help="Console table")
    p.add_argument("--export", action="store_true", help="Export PDF")
    args = p.parse_args()
    ws = date.fromisoformat(args.week) if args.week else get_next_monday()
    if ws.weekday() != 0:
        ws += timedelta(days=(7 - ws.weekday()) % 7)
    clients = load_preferences(ws)
    print(f"📅 Week: {ws.isoformat()}  ({len(clients)} clients)")
    if args.preview:
        preview(clients)
    if args.export or not (args.preview or args.export):
        export_pdf(clients, ws)
    if not (args.preview or args.export):
        print("ℹ️  Use --preview or --export. Default: --export")

if __name__ == "__main__":
    main()
