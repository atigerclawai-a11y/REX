#!/usr/bin/env python3
"""CC_unified_sheets.py — Single source of truth for ALL GOJ daily sheets.

Reads from ghs_schedule.db (Carecenta-synced, authoritative schedule data).
Produces kitchen, distribution, sign-in, and driver sheets from ONE query.
All sheets for the same date/shift will have IDENTICAL client counts.

Usage:
    python3 CC_unified_sheets.py --date 2026-07-27
    python3 CC_unified_sheets.py --date 2026-07-27 --shift 1
"""

import argparse, os, sqlite3, sys
from datetime import date, datetime
from pathlib import Path

HOME = Path.home()
SCHEDULE_DB = HOME / "Desktop/REX/signin_lists/ghs_schedule.db"
AUTH_DB = HOME / "Documents/goj files/dashboard/auth_tracker.db"
OUT_DIR = HOME / "Documents/goj files/output_docs"
LISRA_DIR = HOME / "Desktop/REX/output"

DAY_WEEKDAY_MAP = {0: "sun", 1: "mon", 2: "tue", 3: "wed", 4: "thu", 5: "fri", 6: "sat"}
DAY_DB_COL = {0: "day_M_actual", 1: "day_T_actual", 2: "day_W_actual",
              3: "day_TH_actual", 4: "day_F_actual", 5: "day_Su_actual",
              6: "day_Su_actual"}

# Carecenta time slots → GHS shift mapping
AM_SLOTS = {"9AM-1PM", "9AM-2PM", "10AM-2PM", "MORNING", "9AM-1:15PM"}
PM_SLOTS = {"1:15PM-5:15PM", "2PM-6PM", "2PM-8PM", "AFTERNOON", "EVENING", "1PM-5PM", "1:15PM-5PM"}
FULL_DAY_SLOTS = {"9AM-5PM", "9AM-9PM"}  # These are full-day clients — assigned to both shifts


def get_clients_for_day(target_date: str, shift: int) -> list[dict]:
    """Get client schedule from Carecenta's ghs_schedule.db.
    
    Uses the schedule table (Carecenta-synced) as the single source of truth.
    Falls back to auth_tracker.db for driver route info.
    
    Returns [{
        'name', 'shift', 'time_slot', 'payer', 'auth_number', 'auth_status',
        'has_transport', 'address', 'phone', 'driver_name', 'driver_phone',
        'driver_address'
    }]
    """
    dt = datetime.strptime(target_date, "%Y-%m-%d")
    weekday_num = dt.weekday()
    day_name = DAY_WEEKDAY_MAP[weekday_num]  # 'mon', 'tue', etc.
    day_of_week_db = weekday_num  # 0=Monday
    
    # Week number: find which relative week we're in
    today = date.today()
    week_diff = (dt.date() - today).days // 7
    if week_diff >= 0:
        week_number = 30 + week_diff  # Current = 30, Next = 31
    else:
        week_number = 30 + week_diff  # Past weeks
    
    # Carecenta DB: day_of_week 0=Sunday, 1=Monday, ..., 6=Saturday
    # Python weekday(): 0=Monday, 6=Sunday
    carecenta_day_of_week = (weekday_num + 1) % 7  # Convert Python → Carecenta
    
    if not SCHEDULE_DB.exists():
        print(f"ERROR: Carecenta schedule DB not found at {SCHEDULE_DB}", file=sys.stderr)
        return []
    
    conn = sqlite3.connect(str(SCHEDULE_DB))
    conn.row_factory = sqlite3.Row
    
    # Determine which time slots map to this shift
    if shift == 1:
        slot_filter = "s.time_slot IN ('" + "','".join(sorted(AM_SLOTS)) + "')"
    elif shift == 2:
        slot_filter = "s.time_slot IN ('" + "','".join(sorted(PM_SLOTS)) + "')"
    else:
        slot_filter = "1=1"  # All slots
    
    query = f"""
        SELECT DISTINCT
            c.id as client_id,
            c.first_name || ' ' || c.last_name as client_name,
            c.first_name,
            c.last_name,
            s.time_slot,
            s.payer,
            s.has_transport
        FROM schedule s
        JOIN clients c ON s.client_id = c.id
        WHERE s.day_of_week = ?
          AND s.week_number = ?
          AND {slot_filter}
          AND (s.is_cancelled IS NULL OR s.is_cancelled = 0)
          AND c.status = 'ACTIVE'
        ORDER BY c.last_name, c.first_name
    """
    
    rows = conn.execute(query, (carecenta_day_of_week, week_number)).fetchall()
    
    # Also get full-day clients (they go to BOTH shifts)
    if shift in (1, 2):
        fd_slots = "s.time_slot IN ('" + "','".join(sorted(FULL_DAY_SLOTS)) + "')"
        fd_rows = conn.execute(f"""
            SELECT DISTINCT
                c.id as client_id,
                c.first_name || ' ' || c.last_name as client_name,
                c.first_name, c.last_name,
                s.time_slot, s.payer, s.has_transport
            FROM schedule s
            JOIN clients c ON s.client_id = c.id
            WHERE s.day_of_week = ?
              AND s.week_number = ?
              AND {fd_slots}
              AND (s.is_cancelled IS NULL OR s.is_cancelled = 0)
              AND c.status = 'ACTIVE'
            ORDER BY c.last_name, c.first_name
        """, (carecenta_day_of_week, week_number)).fetchall()
    else:
        fd_rows = []
    
    all_rows = list(rows) + list(fd_rows)
    
    # Deduplicate by client_id
    seen_ids = set()
    clients = []
    for r in all_rows:
        cid = r["client_id"]
        if cid in seen_ids:
            continue
        seen_ids.add(cid)
        
        name = r["client_name"]
        first = r["first_name"]
        last = r["last_name"]
        
        # Get auth info from auth_tracker.db
        auth_number = ""
        payer = r["payer"] or ""
        auth_status = ""
        
        client = {
            "name": name,
            "first_name": first,
            "last_name": last,
            "shift": shift,
            "time_slot": r["time_slot"],
            "payer": payer,
            "auth_number": auth_number,
            "auth_status": auth_status,
            "has_transport": r["has_transport"],
            "address": "",
            "phone": "",
            "driver_name": "",
            "driver_phone": "",
            "driver_address": "",
        }
        clients.append(client)
    
    conn.close()
    
    # Now enrich with auth and driver data from auth_tracker.db
    enrich_from_auth_db(clients, target_date, shift)
    
    return clients


def enrich_from_auth_db(clients: list[dict], target_date: str, shift: int):
    """Add authorization numbers, driver routes, and contact info."""
    if not AUTH_DB.exists():
        return
    
    conn = sqlite3.connect(str(AUTH_DB))
    conn.row_factory = sqlite3.Row
    
    for c in clients:
        name = c["name"]
        
        # Get auth info
        auths = conn.execute("""
            SELECT authorization_number, payer_canonical, status
            FROM authorization
            WHERE client_name = ?
            ORDER BY service_end_date DESC
            LIMIT 1
        """, (name,)).fetchall()
        
        if auths:
            a = auths[0]
            c["auth_number"] = a["authorization_number"] or ""
            c["payer"] = a["payer_canonical"] or c["payer"]
            c["auth_status"] = a["status"] or ""
        
        # Get driver route info from ghs_schedule.db driver_routes table
        try:
            routes_conn = sqlite3.connect(str(SCHEDULE_DB))
            routes_conn.row_factory = sqlite3.Row
            
            day_short = DAY_WEEKDAY_MAP[datetime.strptime(target_date, "%Y-%m-%d").weekday()]
            shift_label = "MORNING" if shift == 1 else "AFTERNOON"
            
            route = routes_conn.execute("""
                SELECT client_name, client_address, client_phone,
                       driver_name, driver_phone, driver_address
                FROM driver_routes
                WHERE day_of_week = ? AND shift = ? AND client_name LIKE ?
                LIMIT 1
            """, (day_short, shift_label, f"%{c['last_name']}%")).fetchall()
            
            if route:
                r = route[0]
                c["address"] = r["client_address"] or ""
                c["phone"] = r["client_phone"] or ""
                c["driver_name"] = r["driver_name"] or ""
                c["driver_phone"] = r["driver_phone"] or ""
                c["driver_address"] = r["driver_address"] or ""
            
            routes_conn.close()
        except Exception:
            pass
    
    conn.close()


def generate_pdf(kind: str, clients: list[dict], target_date: str, shift: int):
    """Generate a PDF for one sheet type."""
    try:
        from reportlab.lib.pagesizes import letter
        from reportlab.lib import colors
        from reportlab.lib.units import inch
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.enums import TA_CENTER, TA_LEFT
    except ImportError:
        os.system(f"{sys.executable} -m pip install reportlab")
        from reportlab.lib.pagesizes import letter
        from reportlab.lib import colors
        from reportlab.lib.units import inch
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.enums import TA_CENTER, TA_LEFT
    
    # Try Cyrillic font
    FONT_REG = "Helvetica"
    FONT_BOLD = "Helvetica-Bold"
    for fp, fpb in [(Path.home() / "Documents/goj files/fonts/DejaVuSans.ttf",
                      Path.home() / "Documents/goj files/fonts/DejaVuSans-Bold.ttf")]:
        if fp.exists() and fpb.exists():
            from reportlab.pdfbase import pdfmetrics
            from reportlab.pdfbase.ttfonts import TTFont
            try:
                pdfmetrics.registerFont(TTFont("DejaVu", str(fp)))
                pdfmetrics.registerFont(TTFont("DejaVuBold", str(fpb)))
                FONT_REG = "DejaVu"
                FONT_BOLD = "DejaVuBold"
            except Exception:
                pass
            break
    
    day_name = datetime.strptime(target_date, "%Y-%m-%d").strftime("%A")
    shift_label = f"Shift {shift}" if shift else "Combined"
    
    if kind == "kitchen":
        title = f"KITCHEN LIST — {day_name} {target_date} — {shift_label}"
        headers = ["#", "Client Name", "Main Dish", "Side", "Notes"]
        col_widths = [18, 180, 120, 100, 80]
        data = [headers]
        for i, c in enumerate(clients, 1):
            data.append([str(i), c["name"], "", "", ""])
    
    elif kind == "distribution":
        title = f"DISTRIBUTION LIST — {day_name} {target_date} — {shift_label}"
        headers = ["#", "Client Name", "Payer", "Auth #", "Status"]
        col_widths = [18, 180, 100, 100, 60]
        data = [headers]
        for i, c in enumerate(clients, 1):
            data.append([str(i), c["name"], c["payer"], c["auth_number"], c["auth_status"]])
    
    elif kind == "signin":
        title = f"SIGN-IN SHEET — {day_name} {target_date} — {shift_label}"
        headers = ["#", "Client Name", "Time In", "Time Out", "Signature"]
        col_widths = [18, 200, 80, 80, 120]
        data = [headers]
        for i, c in enumerate(clients, 1):
            data.append([str(i), c["name"], "", "", ""])
    
    elif kind == "drivers":
        title = f"DRIVER ROUTES — {day_name} {target_date} — {shift_label}"
        headers = ["#", "Client Name", "Address", "Phone", "Driver Name"]
        col_widths = [18, 150, 170, 100, 100]
        data = [headers]
        for i, c in enumerate(clients, 1):
            data.append([str(i), c["name"], c["address"], c["phone"], c["driver_name"]])
    
    else:
        print(f"Unknown sheet kind: {kind}")
        return None
    
    os.makedirs(str(OUT_DIR), exist_ok=True)
    path = str(OUT_DIR / f"GOJ_{target_date}_{kind}_S{shift}.pdf")
    
    doc = SimpleDocTemplate(path, pagesize=letter,
                            leftMargin=20, rightMargin=20, topMargin=20, bottomMargin=20)
    
    styles = getSampleStyleSheet()
    t_style = ParagraphStyle('Title', fontName=FONT_BOLD, fontSize=13, alignment=TA_CENTER, spaceAfter=2)
    s_style = ParagraphStyle('Sub', fontName=FONT_REG, fontSize=9, alignment=TA_CENTER, textColor=colors.gray, spaceAfter=6)
    
    elements = []
    elements.append(Paragraph(f"GARDEN OF JOY", t_style))
    elements.append(Paragraph(title, s_style))
    elements.append(Spacer(1, 4))
    
    # Break into pages of 35 rows
    page_size = 35
    for page_start in range(0, len(data), page_size):
        if page_start > 0:
            elements.append(PageBreak())
            elements.append(Paragraph(f"GARDEN OF JOY", t_style))
            elements.append(Paragraph(title, s_style))
            elements.append(Spacer(1, 4))
        
        page_data = [headers] + data[page_start+1:page_start+page_size]
        if len(page_data) <= 1:
            continue
        
        t = Table(page_data, colWidths=col_widths, repeatRows=1)
        t.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (-1, 0), FONT_BOLD),
            ('FONTNAME', (0, 1), (-1, -1), FONT_REG),
            ('FONTSIZE', (0, 0), (-1, -1), 8),
            ('BACKGROUND', (0, 0), (-1, 0), colors.Color(0, 0.35, 0, 0.12)),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.Color(0, 0.3, 0)),
            ('ALIGN', (0, 0), (0, -1), 'CENTER'),
            ('GRID', (0, 0), (-1, -1), 0.4, colors.Color(0, 0, 0, 0.12)),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.Color(0, 0.4, 0, 0.03)]),
            ('TOPPADDING', (0, 0), (-1, -1), 2.5),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 2.5),
        ]))
        elements.append(t)
    
    elements.append(Spacer(1, 8))
    elements.append(Paragraph(
        f"Total clients: {len(clients)} | Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        ParagraphStyle('Footer', fontName=FONT_BOLD, fontSize=8, alignment=TA_CENTER, textColor=colors.gray)
    ))
    
    doc.build(elements)
    return path


def generate_lisra(clients: list[dict], target_date: str, shift: int):
    """Generate the daily lisra (service list) PDF."""
    return generate_pdf("distribution", clients, target_date, shift)


def main():
    parser = argparse.ArgumentParser(description="Unified GOJ daily sheet generator")
    parser.add_argument("--date", default=date.today().isoformat(), help="Date YYYY-MM-DD")
    parser.add_argument("--shift", type=int, default=0, choices=[0, 1, 2], help="1=S1, 2=S2, 0=Both")
    parser.add_argument("--kind", default="all", choices=["all", "kitchen", "distribution", "signin", "drivers"],
                       help="Sheet type to generate")
    args = parser.parse_args()
    
    target_date = args.date
    kinds = ["kitchen", "distribution", "signin", "drivers"] if args.kind == "all" else [args.kind]
    shifts = [args.shift] if args.shift else [1, 2]
    
    results = {}
    
    for shift in shifts:
        clients = get_clients_for_day(target_date, shift)
        if not clients:
            print(f"⚠️  No clients found for Shift {shift} on {target_date}")
            continue
        
        print(f"\nShift {shift}: {len(clients)} clients")
        results[shift] = len(clients)
        
        for kind in kinds:
            path = generate_pdf(kind, clients, target_date, shift)
            if path:
                print(f"  ✅ {kind}: {path}")
    
    # Verify match
    if len(results) > 1:
        counts = list(results.values())
        if len(set(counts)) == 1:
            print(f"\n✅ ALL MATCH: {counts[0]} clients per shift")
        else:
            print(f"\n❌ MISMATCH: {results}")
    
    return results


if __name__ == "__main__":
    main()
