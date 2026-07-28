#!/usr/bin/env python3
"""BBG Payment Reconciliation — Full Report Generator
Uses crossref CSV + reservation JSON. Stripe scraping unavailable (Chrome JS from Apple Events disabled).
"""

import json, csv, re, smtplib, subprocess
from pathlib import Path
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders

DEPOSIT_PER_PERSON = 45
REX_DIR = Path.home() / "Desktop/REX"
OUT_DIR = REX_DIR / "output"
today_str = datetime.now().strftime("%B %d, %Y")
timestamp = datetime.now().strftime("%Y%m%d_%H%M")
today_iso = datetime.now().strftime("%Y-%m-%d")
yesterday_iso = "2026-07-18"

# --- Load reservations ---
with open(REX_DIR / "CC_bbg_reservations.json") as f:
    all_res = json.load(f)

# Filter today and yesterday
reservations = [r for r in all_res if r.get("reservation_date") in (today_iso, yesterday_iso)]
# Also include known special cases
for r in all_res:
    name = r.get("party_name", "")
    if name == "Max Hockey" and r.get("reservation_date") not in (today_iso, yesterday_iso):
        reservations.append(r)
    if name == "Eugene Peltz" and r.get("reservation_date") not in (today_iso, yesterday_iso):
        reservations.append(r)

# Remove duplicates by unique key
seen = set()
unique_res = []
for r in reservations:
    key = f"{r.get('party_name','')}|{r.get('reservation_time','')}|{r.get('party_size',0)}|{r.get('reservation_date','')}"
    if key not in seen:
        seen.add(key)
        unique_res.append(r)
reservations = unique_res

print(f"Loaded {len(reservations)} reservations for {today_iso} / {yesterday_iso}")

# --- Extract emails from notes field ---
for r in reservations:
    notes = r.get("notes", "")
    if not r.get("email"):
        email_match = re.search(r'Email:\s*(\S+@\S+)', notes)
        if email_match:
            r["email"] = email_match.group(1)

# --- Load crossref CSV ---
crossref = {}
csv_path = REX_DIR / "bbg_payments_crossref.csv"
if csv_path.exists():
    with open(csv_path) as f:
        for row in csv.DictReader(f):
            name = row["Name"].strip()
            crossref[name] = {
                "status": row.get("Status", ""),
                "amount": float(row.get("Payment", "0").replace("$", "").replace(",", "") or "0"),
                "stripe_id": row.get("Stripe ID", ""),
                "email": row.get("Payment Email", ""),
            }

# --- Cross-reference ---
report_rows = []
unmatched_deposits = []
used_stripe_ids = set()

for r in reservations:
    name = r["party_name"]
    email = (r.get("email") or "").lower()
    size = r["party_size"]
    expected = size * DEPOSIT_PER_PERSON
    phone = r.get("phone", "")
    time = r.get("reservation_time", "")
    notes = r.get("notes", "")
    date = r.get("reservation_date", "")
    cash = r.get("deposit_cash")
    cash_ppl = r.get("deposit_persons")

    # Check crossref by name
    cr = crossref.get(name, {})
    
    if cr.get("status") == "PAID":
        amount_paid = cr["amount"]
        stripe_id = cr["stripe_id"]
        paid_email = cr.get("email", "")
        still_owed = max(0, expected - amount_paid)
        paid_for = int(amount_paid / DEPOSIT_PER_PERSON) if DEPOSIT_PER_PERSON and amount_paid > 0 else 0
        
        # Check for duplicate Stripe IDs
        if stripe_id and stripe_id in used_stripe_ids:
            status = "PAID" if still_owed <= 0 else "UNDERPAID"
            notes_extra = f"⚠️ SHARED STRIPE ID: {stripe_id}"
        else:
            if stripe_id:
                used_stripe_ids.add(stripe_id)
            
            if amount_paid >= expected and (amount_paid % DEPOSIT_PER_PERSON == 0 or amount_paid >= expected):
                status = "PAID"
            elif amount_paid > 0:
                status = "UNDERPAID"
            else:
                status = "UNPAID"
            notes_extra = ""
        
        # Yan's $41 is not a deposit multiple — mark as SPECIAL
        if amount_paid > 0 and amount_paid % DEPOSIT_PER_PERSON != 0 and amount_paid < expected:
            status = "UNDERPAID"
        
    elif cash:
        status = "CASH"
        amount_paid = cash
        stripe_id = ""
        paid_email = ""
        still_owed = max(0, expected - cash)
        paid_for = cash_ppl or 0
        notes_extra = ""
    else:
        # Check if this name appears under a different name in crossref
        alt_match = None
        for cr_name, cr_data in crossref.items():
            if cr_data.get("status") == "PAID" and (cr_name.lower() == name.lower() or 
               name.lower().startswith(cr_name.lower()) or cr_name.lower().startswith(name.lower())):
                alt_match = (cr_name, cr_data)
                break
        
        if alt_match:
            cr_name, cr_data = alt_match
            amount_paid = cr_data["amount"]
            stripe_id = cr_data["stripe_id"]
            paid_email = cr_data.get("email", "")
            still_owed = max(0, expected - amount_paid)
            paid_for = int(amount_paid / DEPOSIT_PER_PERSON) if amount_paid > 0 else 0
            status = "PAID" if still_owed <= 0 else "UNDERPAID"
            notes_extra = f"Matched to '{cr_name}' in crossref"
        else:
            status = "UNPAID"
            amount_paid = 0
            stripe_id = ""
            paid_email = ""
            still_owed = expected
            paid_for = 0
            notes_extra = ""

    # Sub-categorize UNPAID
    if status == "UNPAID":
        has_phone = bool(phone) and "****" not in phone
        has_email = bool(email or paid_email)
        if not has_phone and not has_email:
            status = "UNCONTACTABLE"

    report_rows.append({
        "name": name,
        "phone": phone if phone else "",
        "email": paid_email or email or "",
        "time": time,
        "date": date,
        "size": size,
        "status": status,
        "amount_paid": amount_paid,
        "expected": expected,
        "still_owed": still_owed,
        "paid_for": paid_for,
        "stripe_id": stripe_id,
        "notes": notes,
        "notes_extra": notes_extra,
    })

# Sort: by time, then by status
report_rows.sort(key=lambda x: (x["time"] or "99:99", 
                                 0 if x["status"] in ("PAID", "CASH") else 
                                 1 if x["status"] == "UNDERPAID" else 
                                 2 if x["status"] == "UNPAID" else 3))

# --- Summary counts ---
total_res = len(report_rows)
paid_rows = [r for r in report_rows if r["status"] in ("PAID", "CASH")]
underpaid_rows = [r for r in report_rows if r["status"] == "UNDERPAID"]
unpaid_rows = [r for r in report_rows if r["status"] == "UNPAID"]
uncontactable_rows = [r for r in report_rows if r["status"] == "UNCONTACTABLE"]
paid_total = sum(r["amount_paid"] for r in paid_rows + underpaid_rows)
still_owed_total = sum(r["still_owed"] for r in report_rows)
expected_total = sum(r["expected"] for r in report_rows)

# --- Build HTML ---
def html_phone(p):
    if not p:
        return '<span class="nc">no phone</span>'
    if "****" in p:
        return f'<span class="nc">{p}</span>'
    return p

paid_section_rows = [r for r in report_rows if r["status"] in ("PAID", "CASH")]
underpaid_section_rows = [r for r in report_rows if r["status"] == "UNDERPAID"]
unpaid_section_rows = [r for r in report_rows if r["status"] in ("UNPAID", "UNCONTACTABLE")]

def badge(s):
    cls_map = {"PAID": "badge-paid", "CASH": "badge-cash", "UNDERPAID": "badge-under", "UNPAID": "badge-unpaid", "UNCONTACTABLE": "badge-unpaid"}
    cls = cls_map.get(s, "badge-unpaid")
    return f'<span class="badge {cls}">{s}</span>'

def row_html(r, cls):
    method = "STRIPE" if r["stripe_id"] else ("CASH" if r["status"] == "CASH" else "—")
    coverage = f"{r['paid_for']}/{r['size']}" if r["paid_for"] else "—"
    owed = f"${r['still_owed']:,.0f}" if r["still_owed"] > 0 and r["status"] not in ("PAID", "CASH") else "—"
    stripe_display = r["stripe_id"][:25] + "…" if len(r["stripe_id"]) > 25 else r["stripe_id"]
    extra = f' <span style="color:#888;font-size:8px">({r["notes_extra"]})</span>' if r.get("notes_extra") else ""
    return f"""<tr class="{cls}">
<td>{r["name"]}{extra}</td>
<td>{html_phone(r["phone"])}</td>
<td>{r["email"] if r["email"] else '<span class="nc">—</span>'}</td>
<td>{r["time"]}</td>
<td>{r["size"]}</td>
<td>{badge(r["status"])}</td>
<td>${r["amount_paid"]:,.0f}</td>
<td>{coverage}</td>
<td>{method}</td>
<td>{owed}</td>
<td style="font-size:8px;color:#666">{stripe_display}</td>
</tr>"""

html = f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<title>BBG Payment Diagnostic — {today_str}</title>
<style>
body{{font-family:-apple-system,BlinkMacSystemFont,sans-serif;font-size:10px;margin:15px;color:#1a1a2e}}
h1{{font-size:18px;margin-bottom:2px;color:#1a1a2e}}
.sub{{color:#888;margin-bottom:12px;font-size:11px}}
h2{{font-size:13px;border-bottom:2px solid #1a1a2e;padding-bottom:3px;margin-top:16px;color:#1a1a2e}}
table{{width:100%;border-collapse:collapse;margin-bottom:12px}}
th{{background:#1a1a2e;color:#fff;padding:5px 4px;text-align:left;font-size:8px;text-transform:uppercase;white-space:nowrap}}
td{{padding:4px;border-bottom:1px solid #ddd;font-size:9px}}
tr.paid{{background:#f0fff4}} tr.underpaid{{background:#fff8e1}} tr.unpaid{{background:#fff5f5}} tr.stripe-dep{{background:#f0f4ff}}
.badge{{padding:2px 6px;border-radius:6px;font-size:8px;font-weight:bold;color:#fff;white-space:nowrap}}
.badge-paid{{background:#22c55e}} .badge-under{{background:#f59e0b}} .badge-unpaid{{background:#ef4444}} .badge-stripe{{background:#635bff}} .badge-cash{{background:#10b981}}
.summary-box{{background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;padding:10px;margin-bottom:12px;display:flex;flex-wrap:wrap;gap:8px}}
.stat{{text-align:center;min-width:60px}}
.stat .num{{font-size:20px;font-weight:bold}}
.stat .label{{font-size:8px;color:#888;text-transform:uppercase}}
.nc{{color:#999;font-style:italic}}
.alert{{background:#fff5f5;border:1px solid #fecaca;border-radius:6px;padding:8px;margin:8px 0;font-size:9px;color:#991b1b}}
.alert-warn{{background:#fffbeb;border:1px solid #fde68a;padding:8px;margin:8px 0;font-size:9px;color:#92400e}}
.footer{{color:#888;font-size:8px;margin-top:16px;border-top:1px solid #e2e8f0;padding-top:8px}}
</style></head><body>
<h1>🏖️ Boardwalk Beer Garden — Payment Diagnostic</h1>
<div class="sub">{today_str} | $45/person deposit | <strong>IMPORTANT:</strong> Stripe dashboard table failed to load (Chrome JS from Apple Events disabled). Using cached crossref payment data from previous runs. Fresh Stripe scrape not available.</div>

<div class="summary-box">
<div class="stat"><div class="num">{total_res}</div><div class="label">Reservations</div></div>
<div class="stat"><div class="num" style="color:#22c55e">{len(paid_rows)}</div><div class="label">PAID</div></div>
<div class="stat"><div class="num" style="color:#f59e0b">{len(underpaid_rows)}</div><div class="label">UNDERPAID</div></div>
<div class="stat"><div class="num" style="color:#ef4444">{len(unpaid_rows)}</div><div class="label">UNPAID</div></div>
<div class="stat"><div class="num" style="color:#999">{len(uncontactable_rows)}</div><div class="label">UNCONTACTABLE</div></div>
<div class="stat"><div class="num" style="color:#22c55e">${paid_total:,.0f}</div><div class="label">Collected</div></div>
<div class="stat"><div class="num" style="color:#ef4444">${still_owed_total:,.0f}</div><div class="label">Still Owed</div></div>
<div class="stat"><div class="num">${expected_total:,.0f}</div><div class="label">Expected Total</div></div>
</div>"""

# PAID section
if paid_section_rows:
    html += """<h2>✅ PAID IN FULL</h2>
<table><tr><th>Name</th><th>Phone</th><th>Email</th><th>Time</th><th>Size</th><th>Status</th><th>Amt</th><th>Cov.</th><th>Method</th><th>Owed</th><th>Stripe ID</th></tr>"""
    for r in paid_section_rows:
        html += row_html(r, "paid")
    html += "</table>"

# UNDERPAID section
if underpaid_section_rows:
    html += """<h2>🟡 UNDERPAID</h2>
<table><tr><th>Name</th><th>Phone</th><th>Email</th><th>Time</th><th>Size</th><th>Status</th><th>Amt In</th><th>Cov.</th><th>Method</th><th>Still Owed</th><th>Stripe ID</th></tr>"""
    for r in underpaid_section_rows:
        html += row_html(r, "underpaid")
    html += "</table>"

# UNPAID section
if unpaid_section_rows or uncontactable_rows:
    html += """<h2>🔴 UNPAID</h2>
<table><tr><th>Name</th><th>Phone</th><th>Email</th><th>Time</th><th>Size</th><th>Status</th><th>Amt</th><th>Cov.</th><th>Method</th><th>Owed</th><th>Notes</th></tr>"""
    for r in unpaid_section_rows + uncontactable_rows:
        html += row_html(r, "unpaid")
    html += "</table>"

html += f"""
<div class="alert-warn"><strong>⚠️ Data Source Note:</strong> Stripe dashboard table failed to load ("Something went wrong. Please try again later." + Chrome JS from Apple Events disabled). Payment data is sourced from the existing crossref CSV which may not reflect real-time Stripe activity. For fresh data, Kato should export from Stripe dashboard or fix the Chrome JS from Apple Events setting in Chrome → View → Developer → Allow JavaScript from Apple Events.</div>

<div class="footer">
Generated {today_str} at {datetime.now().strftime('%I:%M %p')} | Using cached crossref data | World Cup Finals Day — 40+ reservations
</div>
</body></html>"""

# --- Write HTML ---
OUT_DIR.mkdir(exist_ok=True)
html_path = OUT_DIR / f"bbg_diagnostic_{timestamp}.html"
html_path.write_text(html)
print(f"HTML: {html_path}")

# --- Convert to PDF via Chrome headless ---
pdf_path = OUT_DIR / f"bbg_diagnostic_{timestamp}.pdf"
try:
    result = subprocess.run([
        '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
        '--headless', '--disable-gpu', '--no-sandbox',
        f'--print-to-pdf={pdf_path.resolve()}',
        f'file://{html_path.resolve()}'
    ], capture_output=True, timeout=15)
    if pdf_path.exists():
        print(f"PDF: {pdf_path} ({pdf_path.stat().st_size} bytes)")
    else:
        print("PDF generation failed — check Chrome path/processes")
        pdf_path = html_path  # Fall back to HTML
except Exception as e:
    print(f"PDF generation error: {e}")
    pdf_path = html_path

# --- Email the report ---
try:
    with open(Path.home() / '.rex_gmail_imap.json') as f:
        creds = json.load(f)

    msg = MIMEMultipart()
    msg['From'] = creds['email']
    msg['To'] = 'atigerclawai@gmail.com'
    msg['Subject'] = f'BBG Diagnostic — {today_str}'

    summary = f"""BBG Payment Diagnostic — {today_str}

Total Reservations: {total_res}
✅ PAID (incl CASH): {len(paid_rows)} (${paid_total:,.0f})
🟡 UNDERPAID: {len(underpaid_rows)}
🔴 UNPAID: {len(unpaid_rows)}
🚫 UNCONTACTABLE: {len(uncontactable_rows)}

💰 Collected: ${paid_total:,.0f}
💵 Still Owed: ${still_owed_total:,.0f}
📊 Expected Total: ${expected_total:,.0f}

⚠️ NOTE: Stripe dashboard data unavailable. Using cached crossref data.
Fresh Stripe scrape blocked by Chrome JS from Apple Events setting.

Full report attached.

— Hermes (resy skill cron)
"""
    msg.attach(MIMEText(summary, 'plain'))

    if pdf_path.exists():
        with open(pdf_path, 'rb') as f:
            part = MIMEBase('application', 'pdf')
            part.set_payload(f.read())
            encoders.encode_base64(part)
            part.add_header('Content-Disposition', 'attachment', filename=pdf_path.name)
            msg.attach(part)

    server = smtplib.SMTP_SSL('smtp.gmail.com', 465)
    server.login(creds['email'], creds['app_password'])
    server.send_message(msg)
    server.quit()
    print(f"✅ Emailed report to atigerclawai@gmail.com")
except Exception as e:
    print(f"Email failed: {e}")
    # Try fallback SMTP
    try:
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(creds['email'], creds['app_password'])
        server.send_message(msg)
        server.quit()
        print(f"✅ Emailed (STARTTLS fallback)")
    except Exception as e2:
        print(f"Email fallback also failed: {e2}")

print("Done.")
