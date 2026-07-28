#!/usr/bin/env python3
"""CC_daily_pack.py — Daily doc pack: Sign-in, Kitchen prep, Driver route PDFs."""
import argparse, sqlite3, sys
from collections import defaultdict
from datetime import date
from pathlib import Path
from reportlab.lib.pagesizes import letter, landscape
from reportlab.pdfgen import canvas

HOME = Path.home()
DB_PATHS = [HOME / "goj_corpus/goj files/dashboard/auth_tracker.db",
            HOME / "Documents/goj files/dashboard/auth_tracker.db"]
OUT_DIR = HOME / "Desktop" / "REX" / "output"
ADDR = "3152 Brighton 6 St, Brooklyn NY 11235 | Garden of Joy Adult Day Care Center"
DK = {0: "M", 1: "T", 2: "W", 3: "TH", 4: "F", 5: "Sa", 6: "Su"}
DC = {k: f"day_{k}_actual" for k in DK.values()}
DVC = {k: f"driver_{k}" for k in DK.values()}
MEAL_MAP = {1: ["B", "L"], 2: ["L", "S"]}
CAR_SVC = "CAR_SERVICE"


def get_day_key(d):
    return DK.get(d.weekday(), "M")


def fmt_date(d):
    return d.strftime("%A, %B %d, %Y")


def fetch_clients(db_path, sd, shifts):
    dk = get_day_key(sd)
    q = f"""SELECT name,address,transportation,shift,{DVC[dk]} AS driver FROM clients
            WHERE active=1 AND {DC[dk]}=1 AND shift IN ({','.join('?' for _ in shifts)})
            ORDER BY shift,name"""
    with sqlite3.connect(str(db_path)) as conn:
        rows = conn.execute(q, shifts).fetchall()
    r = {s: [] for s in shifts}
    for name, addr, trans, shift, driver in rows:
        r[int(shift)].append({"name": name, "address": addr or "",
                              "transport": trans or "", "driver": driver or "", "shift": int(shift)})
    return r


def draw_header(c, title, subtitle, y, w):
    c.setFont("Helvetica-Bold", 14)
    c.drawCentredString(w / 2, y, title)
    c.setFont("Helvetica", 10)
    c.drawCentredString(w / 2, y - 16, subtitle)
    c.setFont("Helvetica", 7)
    c.drawCentredString(w / 2, y - 28, ADDR)
    return y - 36


def draw_table(c, headers, rows, x, y, cw, row_h=16):
    c.setFont("Helvetica-Bold", 8)
    c.setFillColorRGB(0.2, 0.2, 0.2)
    cx = x
    for i, h in enumerate(headers):
        c.drawString(cx + 2, y + 3, h)
        cx += cw[i]
    y -= row_h
    c.setStrokeColorRGB(0.6, 0.6, 0.6)
    c.line(x, y + row_h, x + sum(cw), y + row_h)
    c.setFont("Helvetica", 8)
    c.setFillColorRGB(0, 0, 0)
    for row in rows:
        if y < 40:
            c.showPage()
            y = 720
        cx = x
        for i, cell in enumerate(row):
            c.drawString(cx + 2, y + 3, cell)
            cx += cw[i]
        c.line(x, y, x + sum(cw), y)
        y -= row_h
    c.line(x, y + row_h, x + sum(cw), y + row_h)
    return y


def gen_signin(clients, sd, shift, out):
    path = out / f"CC_SignIn_{sd.isoformat()}_S{shift}.pdf"
    c = canvas.Canvas(str(path), pagesize=letter)
    w, h = letter
    top = draw_header(c, f"Garden of Joy \u2014 Sign-In Sheet (Shift {shift})", fmt_date(sd), h - 36, w)
    data = [[str(i + 1), cl["name"], cl["transport"], "", ""] for i, cl in enumerate(clients)]
    draw_table(c, ["#", "Client Name", "Transport", "Time In", "Signature"],
               data, 36, top - 8, [20, 280, 60, 80, 160], 18)
    c.save()
    print(f"  \u2713 Sign-in: {path.name}")


def gen_kitchen(clients, sd, shift, out):
    path = out / f"CC_Kitchen_{sd.isoformat()}_S{shift}.pdf"
    c = canvas.Canvas(str(path), pagesize=landscape(letter))
    w, h = landscape(letter)
    top = draw_header(c, f"Garden of Joy \u2014 Kitchen Prep Count (Shift {shift})", fmt_date(sd), h - 36, w)
    codes = MEAL_MAP[shift]
    lbl = {"B": "B=Breakfast(9am)", "L": "L=Lunch(12pm)", "S": "S=Snack(3pm)"}
    c.setFont("Helvetica-Bold", 10)
    c.drawString(36, top - 4, f"Meal codes: {' + '.join(lbl[mc] for mc in codes)}")
    top -= 20
    headers = ["#", "Client Name", "Transport"] + codes + ["Total"]
    cw = [20, 280, 60] + [50] * len(codes) + [50]
    total_meal = {c2: 0 for c2 in codes}
    data = []
    for i, cl in enumerate(clients):
        row = [str(i + 1), cl["name"], cl["transport"]]
        for mc in codes:
            row.append("X")
            total_meal[mc] += 1
        row.append(str(len(codes)))
        data.append(row)
    data.append(["", "TOTAL", ""] + [str(total_meal[mc]) for mc in codes] + [str(sum(total_meal.values()))])
    y = draw_table(c, headers, data, 36, top - 8, cw, 14)
    y -= 20
    c.setFont("Helvetica-Bold", 10)
    c.drawString(36, y, "Meal Summary:")
    y -= 14
    c.setFont("Helvetica", 9)
    for mc in codes:
        c.drawString(36, y, f"  {mc} = {lbl[mc].split('=')[1]}: {total_meal[mc]:>3}")
        y -= 14
    c.setFont("Helvetica-Bold", 9)
    c.drawString(36, y, f"  Total meals: {sum(total_meal.values()):>3}  Clients: {len(clients):>3}")
    c.save()
    print(f"  \u2713 Kitchen: {path.name}")


def gen_driver(clients, sd, shift, out):
    path = out / f"CC_DriverRoute_{sd.isoformat()}_S{shift}.pdf"
    c = canvas.Canvas(str(path), pagesize=landscape(letter))
    w, h = landscape(letter)
    top = draw_header(c, f"Garden of Joy \u2014 Driver Route Sheet (Shift {shift})", fmt_date(sd), h - 36, w)
    groups = defaultdict(list)
    for cl in clients:
        groups[cl["driver"] if cl["driver"] else "Unassigned"].append(cl)
    sorted_d = sorted(groups, key=lambda d: (d == CAR_SVC, d == "Unassigned", d.lower()))
    y = top - 4
    for drv in sorted_d:
        if y < 60:
            c.showPage()
            y = 700
        grp = groups[drv]
        svc = "" if drv == "Unassigned" else f" \u2014 {CAR_SVC if drv == CAR_SVC else 'Transport'}"
        c.setFillColorRGB(0.15, 0.15, 0.15)
        c.setFont("Helvetica-Bold", 10)
        c.drawString(36, y, f"Driver: {drv}{svc}  ({len(grp)} client{'s' if len(grp)!=1 else ''})")
        y -= 18
        c.setFont("Helvetica-Bold", 8)
        c.setFillColorRGB(0.3, 0.3, 0.3)
        cx = 36
        for hdr, cw in [("#",24),("Client Name",260),("Address",340),("Transport",60)]:
            c.drawString(cx + 2, y + 3, hdr)
            cx += cw
        y -= 14
        c.setStrokeColorRGB(0.7, 0.7, 0.7)
        c.line(36, y + 14, 36 + 684, y + 14)
        c.setFillColorRGB(0, 0, 0)
        c.setFont("Helvetica", 8)
        for i, cl in enumerate(grp):
            if y < 30:
                c.showPage()
                y = 700
            addr = cl["address"][:50] + ("..." if len(cl["address"]) > 50 else "")
            c.drawString(38, y + 3, str(i + 1))
            c.drawString(62, y + 3, cl["name"])
            c.drawString(322, y + 3, addr)
            c.drawString(662, y + 3, cl["transport"])
            c.line(36, y, 720, y)
            y -= 14
        y -= 8
    c.save()
    print(f"  \u2713 Driver route: {path.name}")


def main():
    ap = argparse.ArgumentParser(description="Generate daily document pack for Garden of Joy")
    ap.add_argument("--date", default=date.today().isoformat())
    ap.add_argument("--shifts", default="both", choices=["S1", "S2", "both"])
    ap.add_argument("--db", default="", help="Path to auth_tracker.db (auto-detect if unset)")
    args = ap.parse_args()
    sd = date.fromisoformat(args.date)
    shift_map = {"S1": [1], "S2": [2], "both": [1, 2]}
    shifts = shift_map[args.shifts]
    if args.db:
        db_path = Path(args.db)
    else:
        db_path = next((p for p in DB_PATHS if p.exists()), None)
    if not db_path or not db_path.exists():
        print("\u2717 auth_tracker.db not found. Try: --db <path>")
        sys.exit(1)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    by_shift = fetch_clients(db_path, sd, shifts)
    print(f"\n{'='*60}\n Garden of Joy \u2014 Daily Document Pack\n {fmt_date(sd)}\n{'='*60}")
    for shift in shifts:
        clist = by_shift.get(shift, [])
        if not clist:
            print(f"\n  Shift {shift}: no clients \u2014 skipping")
            continue
        print(f"\n\u2500\u2500 Shift {shift} ({len(clist)} clients) \u2500\u2500")
        gen_signin(clist, sd, shift, OUT_DIR)
        gen_kitchen(clist, sd, shift, OUT_DIR)
        gen_driver(clist, sd, shift, OUT_DIR)
    print(f"\n{'='*60}\n Done \u2014 PDFs in {OUT_DIR}\n{'='*60}\n")


if __name__ == "__main__":
    main()
