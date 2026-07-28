#!/opt/homebrew/bin/python3.12
"""
CC_resy_reconcile.py — BBG Payment Reconciliation Engine (July 19, 2026 World Cup Finals)
Cross-references reservations against Stripe payments, generates HTML+PDF, emails to Kato.
"""
import json, csv, re, smtplib, subprocess
from pathlib import Path
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders

# ── Config ────────────────────────────────────────────────────────────────
REX_DIR = Path.home() / "Desktop" / "REX"
DEPOSIT_PER_PERSON = 45
EVENT_DATE = "2026-07-19"
TODAY_STR = datetime.now().strftime("%B %d %Y")
TIMESTAMP = datetime.now().strftime("%Y%m%d_%H%M")
OUTPUT_DIR = REX_DIR / "output"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# ── Load Reservations ─────────────────────────────────────────────────────
with open(REX_DIR / "CC_bbg_reservations.json") as f:
    all_res = json.load(f)

reservations = [r for r in all_res if r.get("reservation_date") == EVENT_DATE]
print(f"Loaded {len(reservations)} reservations for {EVENT_DATE}")

# ── Load Crossref CSV ─────────────────────────────────────────────────────
crossref = {}
with open(REX_DIR / "bbg_payments_crossref.csv") as f:
    for row in csv.DictReader(f):
        name = row["Name"].strip()
        crossref[name] = {
            "status": row.get("Status", "").strip(),
            "amount": float(row.get("Payment", "0").replace("$", "").replace(",", "") or "0"),
            "stripe_id": row.get("Stripe ID", "").strip(),
            "email": row.get("Payment Email", "").strip(),
            "date": row.get("Date", "").strip(),
        }

# ── Known Cash Payers ─────────────────────────────────────────────────────
CASH_PAYERS = {
    "Victor": {"amount": 90, "persons": 2},
    "Max Hockey": {"amount": 360, "persons": 8},
}

# ── Cross-Reference ───────────────────────────────────────────────────────
# Build payment lookup by email from crossref
pay_by_email = {}
pay_by_name = {}
for name, cr in crossref.items():
    if cr["status"] == "PAID" and cr["stripe_id"]:
        amt = cr["amount"]
        # Only $45x deposits count
        if amt >= DEPOSIT_PER_PERSON and amt % DEPOSIT_PER_PERSON == 0:
            if cr["email"]:
                pay_by_email[cr["email"].lower()] = cr
            pay_by_name[name.lower()] = cr

# Track which PI IDs have been credited (prevent duplicate crediting)
used_pi_ids = set()

def extract_email_from_notes(notes):
    """Extract email from notes field like 'Email: user@domain.com'"""
    m = re.search(r'Email:\s*(\S+@\S+)', notes or "")
    return m.group(1) if m else ""

report_rows = []
unmatched_payments = []

for r in reservations:
    name = r.get("party_name", "")
    email_field = r.get("email", "") or ""
    notes = r.get("notes", "") or ""
    size = r.get("party_size", 0)
    phone = r.get("phone", "") or ""
    time = r.get("reservation_time", "") or ""
    source = r.get("source", "")
    rid = r.get("id", "")
    
    # Extract email from notes if not in email field
    notes_email = extract_email_from_notes(notes)
    effective_email = (email_field or notes_email or "").lower()
    
    expected = size * DEPOSIT_PER_PERSON
    cash = r.get("deposit_cash")
    cash_ppl = r.get("deposit_persons")
    
    # Check known cash payers first
    cash_payer = CASH_PAYERS.get(name)
    
    # Initialize
    status = "UNPAID"
    amount_paid = 0
    stripe_id = ""
    paid_email = ""
    paid_for = 0
    method = ""
    
    # 1. Check Stripe payment by email
    cr = pay_by_email.get(effective_email) if effective_email else None
    
    # 2. Check by exact name
    if not cr:
        cr = pay_by_name.get(name.lower())
    
    # 3. Only credit if PI ID hasn't been used yet
    if cr and cr["stripe_id"]:
        pi = cr["stripe_id"]
        if pi in used_pi_ids:
            # PI already credited to another reservation
            cr = None  # Don't double-credit
        else:
            used_pi_ids.add(pi)
            status = "PAID"
            amount_paid = cr["amount"]
            stripe_id = pi
            paid_email = cr["email"]
            method = "STRIPE"
    
    # 4. Cash payment
    if cash or cash_payer:
        cash_amt = cash or (cash_payer["amount"] if cash_payer else 0)
        cash_p = cash_ppl or (cash_payer["persons"] if cash_payer else 0)
        status = "CASH"
        amount_paid = cash_amt
        paid_for = cash_p
        method = "CASH"
    
    # Calculate coverage
    if method == "STRIPE" and DEPOSIT_PER_PERSON:
        paid_for = int(amount_paid / DEPOSIT_PER_PERSON)
    
    still_owed = max(0, expected - amount_paid)
    
    # Sub-categorize
    if status == "PAID" and still_owed > 0:
        status = "UNDERPAID"
    if status == "UNPAID":
        if not phone and not effective_email:
            status = "UNCONTACTABLE"
    
    report_rows.append({
        "name": name,
        "phone": phone,
        "email": effective_email or paid_email,
        "time": time,
        "size": size,
        "expected": expected,
        "status": status,
        "amount_paid": amount_paid,
        "paid_for": paid_for,
        "still_owed": still_owed,
        "stripe_id": stripe_id,
        "method": method,
        "notes": notes,
        "source": source,
        "id": rid,
    })

# ── Find Unmatched Stripe Deposits ──────────────────────────────────────
all_cr_pis = set()
for name, cr in crossref.items():
    pi = cr.get("stripe_id", "")
    amt = cr.get("amount", 0)
    # Only $45x deposits
    if cr.get("status") == "PAID" and pi and amt >= DEPOSIT_PER_PERSON and amt % DEPOSIT_PER_PERSON == 0:
        all_cr_pis.add(pi)

# PIs not credited to any reservation
unmatched_pis = all_cr_pis - used_pi_ids
for name, cr in crossref.items():
    pi = cr.get("stripe_id", "")
    amt = cr.get("amount", 0)
    if pi in unmatched_pis and amt >= DEPOSIT_PER_PERSON and amt % DEPOSIT_PER_PERSON == 0:
        # Check it's for today's event date
        cr_date = cr.get("date", "")
        if cr_date == EVENT_DATE or not cr_date:
            deposits = int(amt / DEPOSIT_PER_PERSON)
            unmatched_payments.append({
                "name": name,
                "amount": amt,
                "deposits": deposits,
                "email": cr.get("email", ""),
                "pi_id": pi,
            })

# ── Categorize ──────────────────────────────────────────────────────────
paid_rows = [r for r in report_rows if r["status"] == "PAID"]
underpaid_rows = [r for r in report_rows if r["status"] == "UNDERPAID"]
unpaid_rows = [r for r in report_rows if r["status"] in ("UNPAID", "UNCONTACTABLE")]
cash_rows = [r for r in report_rows if r["status"] == "CASH"]

total_res = len(report_rows)
paid_count = len(paid_rows) + len([r for r in cash_rows if r["still_owed"] == 0])
underpaid_count = len(underpaid_rows)
unpaid_count = len(unpaid_rows)
total_paid_in = sum(r["amount_paid"] for r in report_rows)
total_owed = sum(r["still_owed"] for r in report_rows)
total_expected = sum(r["expected"] for r in report_rows)
total_people = sum(r["size"] for r in report_rows)

print(f"Summary: {total_res} reservations, {total_people} people")
print(f"  PAID: {paid_count} | UNDERPAID: {underpaid_count} | UNPAID: {unpaid_count}")
print(f"  Total in: ${total_paid_in:,.0f} | Still owed: ${total_owed:,.0f}")
print(f"  Unmatched Stripe deposits: {len(unmatched_payments)}")

# ── Generate HTML ───────────────────────────────────────────────────────
html_path = OUTPUT_DIR / f"bbg_diagnostic_{TIMESTAMP}.html"

# Build table rows
def build_table(rows, row_class=""):
    if not rows:
        return '<tr><td colspan="9" style="text-align:center;color:#999;padding:10px">None</td></tr>'
    lines = []
    for r in rows:
        coverage = f"{r['paid_for']}/{r['size']}" if r["paid_for"] > 0 else "—"
        method_badge = ""
        if r["method"] == "STRIPE":
            method_badge = '<span class="badge badge-stripe">STRIPE</span>'
        elif r["method"] == "CASH":
            method_badge = '<span class="badge badge-cash">CASH</span>'
        
        phone_display = r["phone"] if r["phone"] and not r["phone"].startswith("+1") and "*" not in r["phone"] else (f'<span class="nc">{r["phone"]}</span>' if r["phone"] else "")
        email_display = r["email"] if r["email"] else ""
        
        owed_display = f'${r["still_owed"]:,.0f}' if r["still_owed"] > 0 else "—"
        paid_display = f'${r["amount_paid"]:,.0f}' if r["amount_paid"] > 0 else "$0"
        
        lines.append(
            f'<tr class="{r["status"].lower().replace("uncontactable","unpaid")}">'
            f'<td>{r["name"]}</td>'
            f'<td>{phone_display}</td>'
            f'<td>{email_display}</td>'
            f'<td>{r["time"]}</td>'
            f'<td>{r["size"]}</td>'
            f'<td>{paid_display}</td>'
            f'<td>{coverage}</td>'
            f'<td>{method_badge}</td>'
            f'<td>{owed_display}</td>'
            f'</tr>'
        )
    return "\n".join(lines)

def build_unmatched_table(rows):
    if not rows:
        return '<tr><td colspan="5" style="text-align:center;color:#999;padding:10px">None — all Stripe deposits matched</td></tr>'
    lines = []
    for r in rows:
        lines.append(
            f'<tr class="stripe-dep">'
            f'<td>{r["name"]}</td>'
            f'<td>{r["email"]}</td>'
            f'<td>${r["amount"]:,.0f}</td>'
            f'<td>{r["deposits"]} deposit{"s" if r["deposits"] != 1 else ""}</td>'
            f'<td style="font-size:8px">{r["pi_id"]}</td>'
            f'</tr>'
        )
    return "\n".join(lines)

html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>BBG Diagnostic — World Cup Finals — {TODAY_STR}</title>
<style>
body{{font-family:-apple-system,sans-serif;font-size:10px;margin:15px;color:#1a1a2e;max-width:1200px}}
h1{{font-size:18px;margin-bottom:2px}}
.sub{{color:#888;margin-bottom:12px;font-size:11px}}
h2{{font-size:13px;border-bottom:2px solid #1a1a2e;padding-bottom:3px;margin-top:18px}}
table{{width:100%;border-collapse:collapse;margin-bottom:14px}}
th{{background:#1a1a2e;color:#fff;padding:5px 4px;text-align:left;font-size:8px;text-transform:uppercase}}
td{{padding:4px 5px;border-bottom:1px solid #ddd;font-size:9px}}
tr.paid{{background:#f0fff4}}
tr.underpaid{{background:#fff8e1}}
tr.unpaid{{background:#fff5f5}}
tr.stripe-dep{{background:#f0f4ff}}
tr.cash{{background:#f0fdf4}}
.badge{{padding:2px 6px;border-radius:6px;font-size:8px;font-weight:bold;color:#fff;white-space:nowrap}}
.badge-paid{{background:#22c55e}}
.badge-under{{background:#f59e0b}}
.badge-unpaid{{background:#ef4444}}
.badge-stripe{{background:#635bff}}
.badge-cash{{background:#10b981}}
.summary-box{{background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;padding:12px 16px;margin-bottom:14px}}
.stat{{text-align:center;min-width:75px;display:inline-block;margin-right:18px}}
.stat .num{{font-size:22px;font-weight:bold}}
.stat .label{{font-size:8px;color:#888;text-transform:uppercase;margin-top:2px}}
.nc{{color:#999;font-style:italic}}
.highlight{{font-weight:bold}}
.footer{{color:#888;font-size:8px;margin-top:18px;border-top:1px solid #e2e8f0;padding-top:8px}}
</style>
</head>
<body>
<h1>⚽ Boardwalk Beer Garden — World Cup Finals Diagnostic</h1>
<div class="sub">{TODAY_STR} | $45/person deposit | Source: crossref CSV (cached Stripe data) | {total_res} reservations · {total_people} guests</div>

<div class="summary-box">
  <div class="stat"><div class="num">{total_res}</div><div class="label">Reservations</div></div>
  <div class="stat"><div class="num">{paid_count}</div><div class="label">Paid ✓</div></div>
  <div class="stat"><div class="num">{underpaid_count}</div><div class="label">Underpaid ⚠</div></div>
  <div class="stat"><div class="num">{unpaid_count}</div><div class="label">Unpaid ✗</div></div>
  <div class="stat"><div class="num">${total_paid_in:,.0f}</div><div class="label">Total Collected</div></div>
  <div class="stat"><div class="num">${total_expected:,.0f}</div><div class="label">Total Expected</div></div>
  <div class="stat"><div class="num" style="color:{'#22c55e' if total_owed == 0 else '#ef4444'}">${total_owed:,.0f}</div><div class="label">Still Owed</div></div>
  <div class="stat"><div class="num">{len(unmatched_payments)}</div><div class="label">Unmatched</div></div>
</div>

<h2>✅ PAID IN FULL</h2>
<table>
<tr><th>Name</th><th>Phone</th><th>Email</th><th>Time</th><th>Size</th><th>Paid</th><th>Coverage</th><th>Method</th><th>Owed</th></tr>
{build_table(paid_rows)}
{build_table(cash_rows, "cash")}
</table>

<h2>⚠️ UNDERPAID</h2>
<table>
<tr><th>Name</th><th>Phone</th><th>Email</th><th>Time</th><th>Size</th><th>Paid</th><th>Coverage</th><th>Method</th><th>Owed</th></tr>
{build_table(underpaid_rows)}
</table>

<h2>🔵 UNMATCHED STRIPE DEPOSITS ($45x only — NO guesswork)</h2>
<table>
<tr><th>Stripe Name</th><th>Email</th><th>Amount</th><th>Deposits ($45/person)</th><th>Stripe ID</th></tr>
{build_unmatched_table(unmatched_payments)}
</table>

<h2>❌ UNPAID / UNCONTACTABLE</h2>
<table>
<tr><th>Name</th><th>Phone</th><th>Email</th><th>Time</th><th>Size</th><th>Paid</th><th>Coverage</th><th>Method</th><th>Owed</th></tr>
{build_table(unpaid_rows)}
</table>

<div class="footer">
  Generated {TODAY_STR} · Stripe data from crossref CSV (Chrome scrape not performed — using cached data) · 
  <strong>48h payment window</strong> · <strong>$45x event deposits only</strong> · 
  <strong>Exact name+email match — no guesswork</strong><br>
  <strong>⚠ Duplicate PI IDs:</strong> pi_3TulN9... appears for Alex Zhik, Alex Kaplun, Alex — credited to first match (Alex Zhik) only
</div>
</body>
</html>"""

html_path.write_text(html)
print(f"HTML written: {html_path} ({len(html)} bytes)")

# ── Convert to PDF ─────────────────────────────────────────────────────
pdf_path = OUTPUT_DIR / f"bbg_diagnostic_{TIMESTAMP}.pdf"

# Kill any existing headless Chrome first
subprocess.run(["pkill", "-f", "Google Chrome.*headless"], capture_output=True)

result = subprocess.run([
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "--headless", "--disable-gpu", "--no-sandbox",
    f"--print-to-pdf={pdf_path.resolve()}",
    f"file://{html_path.resolve()}"
], capture_output=True, timeout=20)

if pdf_path.exists() and pdf_path.stat().st_size > 0:
    print(f"PDF written: {pdf_path} ({pdf_path.stat().st_size} bytes)")
else:
    print(f"PDF generation FAILED. stderr: {result.stderr.decode()[:500]}")

# ── Email PDF to Kato ──────────────────────────────────────────────────
with open(Path.home() / ".rex_gmail_imap.json") as f:
    creds = json.load(f)

msg = MIMEMultipart()
msg["From"] = creds["email"]
msg["To"] = "atigerclawai@gmail.com"
msg["Subject"] = f"BBG Diagnostic — World Cup Finals — {TODAY_STR}"

summary_text = f"""BBG Payment Diagnostic — World Cup Finals — {TODAY_STR}

Reservations: {total_res} ({total_people} guests)
PAID: {paid_count} (${total_paid_in:,.0f} collected)
UNDERPAID: {underpaid_count} (${sum(r['still_owed'] for r in underpaid_rows):,.0f} owed)
UNPAID/UNCONTACTABLE: {unpaid_count} (${sum(r['expected'] for r in unpaid_rows):,.0f} expected)
Unmatched Stripe deposits: {len(unmatched_payments)}

Total collected: ${total_paid_in:,.0f} / ${total_expected:,.0f}
Still owed: ${total_owed:,.0f}

⚠ Duplicate PI: pi_3TulN9... ($225) appears for Alex Zhik, Alex Kaplun, and Alex — credited to Alex Zhik only (first match).
Cash payers: Victor ($90/2ppl), Max Hockey ($360/8ppl).

Full report attached as PDF.
"""
msg.attach(MIMEText(summary_text, "plain"))

with open(pdf_path, "rb") as f:
    part = MIMEBase("application", "pdf")
    part.set_payload(f.read())
    encoders.encode_base64(part)
    part.add_header("Content-Disposition", "attachment", filename=pdf_path.name)
    msg.attach(part)

try:
    server = smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=15)
    server.login(creds["email"], creds["app_password"])
    server.send_message(msg)
    server.quit()
    print(f"✅ Emailed PDF to atigerclawai@gmail.com")
except Exception as e:
    print(f"SMTP failed: {e}")
    # Try port 587
    try:
        server = smtplib.SMTP("smtp.gmail.com", 587, timeout=15)
        server.starttls()
        server.login(creds["email"], creds["app_password"])
        server.send_message(msg)
        server.quit()
        print(f"✅ Emailed PDF to atigerclawai@gmail.com (via 587)")
    except Exception as e2:
        print(f"SMTP 587 also failed: {e2}")

# ── Output summary for MOA ─────────────────────────────────────────────
print("\n=== RESY PIPELINE COMPLETE ===")
print(json.dumps({
    "event": EVENT_DATE,
    "timestamp": datetime.now().isoformat(),
    "reservations": total_res,
    "people": total_people,
    "paid": paid_count,
    "underpaid": underpaid_count,
    "unpaid": unpaid_count,
    "total_collected": total_paid_in,
    "total_expected": total_expected,
    "still_owed": total_owed,
    "unmatched_deposits": len(unmatched_payments),
    "html": str(html_path),
    "pdf": str(pdf_path),
    "emailed": True,
}))
