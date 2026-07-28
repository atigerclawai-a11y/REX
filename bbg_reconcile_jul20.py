#!/usr/bin/env python3
"""BBG Payment Reconciliation — July 20, 2026"""
import json, csv, re, subprocess, smtplib
from pathlib import Path
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders

REX_DIR = Path.home() / "Desktop/REX"
OUT_DIR = REX_DIR / "output"
DEPOSIT = 45

# ── Step 1: Load reservations for today ──
res_file = REX_DIR / "CC_bbg_reservations.json"
with open(res_file) as f:
    all_res = json.load(f)

today = "2026-07-20"
reservations = [r for r in all_res if r.get("reservation_date") == today]
print(f"📋 Reservations for {today}: {len(reservations)}")

# ── Step 2: Try Gmail IMAP for Owner.com emails ──
import imaplib, email as em
with open(Path.home() / '.rex_gmail_imap.json') as f:
    creds = json.load(f)
M = imaplib.IMAP4_SSL('imap.gmail.com', 993)
M.login(creds['email'], creds['app_password'])
M.select('INBOX')
status, msgs = M.search(None, 'FROM "olympusbbg" SINCE "20-Jul-2026"')
email_map = {}
for num in msgs[0].split():
    status, data = M.fetch(num, '(RFC822)')
    msg = em.message_from_bytes(data[0][1])
    body = ""
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                body = part.get_payload(decode=True).decode('utf-8', errors='ignore')
                break
    else:
        body = msg.get_payload(decode=True).decode('utf-8', errors='ignore')
    lines = body.strip().split('\n')
    guest_name = guest_email = guest_phone = ''
    for line in lines:
        line = line.strip()
        if line.startswith(': ') and '@' in line:
            guest_email = line[2:].strip()
        elif line.startswith(': ') and not guest_name:
            guest_name = line[2:].strip()
        elif line.startswith(': ') and guest_name:
            guest_phone = line[2:].strip()
    if guest_email:
        email_map[guest_name.lower()] = {'email': guest_email, 'phone': guest_phone}
        parts = guest_name.lower().split()
        if len(parts) > 1:
            email_map[parts[-1].lower()] = {'email': guest_email, 'phone': guest_phone}
M.logout()
print(f"📧 Owner.com emails today: {len(msgs[0].split()) if msgs[0] else 0}")
print(f"   Extracted entries: {len(email_map)}")

# Merge emails into reservations
for r in reservations:
    name = r.get('party_name', '').lower()
    if not r.get('email') and name in email_map:
        r['email'] = email_map[name]['email']
    if not r.get('email'):
        for gname, gdata in email_map.items():
            if gname in name or name in gname:
                r['email'] = gdata['email']
                break

# ── Step 3: Stripe payments from Chrome scrape ──
# Hardcoded from the browser extraction (Jul 19-20 within 48h window)
# Only include deposit-eligible payments: amount % 45 == 0 and amount >= 45
stripe_raw = [
    # Jul 19
    ("pi_3TuyjuIC68Kv9IV50YI0J0ci", 270.00, "alex.reynus@gmail.com", "Jul 19, 5:42 PM"),
    ("pi_3TuxczIC68Kv9IV50saWLmrn", 540.00, "maxikny@gmail.com", "Jul 19, 4:31 PM"),
    ("pi_3TumNEIC68Kv9IV51K7YHv8J", 225.00, "kirill.likovv@gmail.com", "Jul 19, 4:30 AM"),
    ("pi_3TulN9IC68Kv9IV50gIutFAn", 225.00, "alexander.zhik@gmail.com", "Jul 19, 3:26 AM"),
    # Jul 18 (within 48h)
    ("pi_3TuhPuIC68Kv9IV51XdzWwUf", 90.00, "stevenr303@gmail.com", "Jul 18, 11:13 PM"),
    ("pi_3TufTlIC68Kv9IV517B8FtL5", 180.00, "benjaminwmourier@gmail.com", "Jul 18, 9:09 PM"),
    ("pi_3TufCEIC68Kv9IV50DvhaR1G", 540.00, "ednovo64@gmail.com", "Jul 18, 8:50 PM"),
    ("pi_3Tue9KIC68Kv9IV50TcS2psF", 360.00, "valery013013@gmail.com", "Jul 18, 7:43 PM"),
    ("pi_3TudkKIC68Kv9IV51x6Yzxwq", 135.00, "cashcashwinnie@gmail.com", "Jul 18, 7:18 PM"),
    ("pi_3TudhJIC68Kv9IV50ciCEya3", 90.00, "romanice9999@gmail.com", "Jul 18, 7:14 PM"),
    ("pi_3TuMz2IC68Kv9IV51kS2NtFL", 90.00, "bossangeles1@yahoo.com", "Jul 18, 1:24 AM"),
    ("pi_3TuMCLIC68Kv9IV50KfycOyh", 45.00, "eleonorapankratova@gmail.com", "Jul 18, 12:33 AM"),
]
payments = [{'pi_id': p[0], 'amount': p[1], 'email': p[2], 'date': p[3]} for p in stripe_raw]
print(f"💳 Stripe deposit payments (48h window): {len(payments)}")

# ── Step 4: Load crossref CSV ──
crossref_path = REX_DIR / "bbg_payments_crossref.csv"
crossref = {}
if crossref_path.exists():
    with open(crossref_path, newline='') as f:
        for row in csv.DictReader(f):
            crossref[row['Name'].strip()] = {
                'status': row.get('Status', ''),
                'amount': float(row.get('Payment', '0').replace('$', '').replace(',', '') or '0'),
                'stripe_id': row.get('Stripe ID', ''),
                'email': row.get('Payment Email', ''),
            }

# ── Build payment lookup ──
pay_by_email = {}
for p in payments:
    if p['email']:
        pay_by_email[p['email'].lower()] = p

# ── Cross-reference ──
DEPOSIT_PER_PERSON = 45
report_rows = []
seen_stripe_ids = set()

for r in reservations:
    name = r['party_name']
    email = (r.get('email', '') or '').lower()
    size = r['party_size']
    expected = size * DEPOSIT_PER_PERSON
    phone = r.get('phone', '')
    time = r.get('reservation_time', '')
    notes = r.get('notes', '')
    cash = r.get('deposit_cash')
    cash_ppl = r.get('deposit_persons')

    payment = pay_by_email.get(email) if email else None
    cr = crossref.get(name, {})

    if payment:
        status = 'PAID'
        amount_paid = payment['amount']
        stripe_id = payment['pi_id']
        paid_email = payment['email']
    elif cr.get('status') == 'PAID':
        status = 'PAID'
        amount_paid = cr['amount']
        stripe_id = cr['stripe_id']
        paid_email = cr.get('email', '')
    elif cash:
        status = 'CASH'
        amount_paid = cash
        stripe_id = ''
        paid_email = ''
    else:
        status = 'UNPAID'
        amount_paid = 0
        stripe_id = ''
        paid_email = ''

    still_owed = max(0, expected - amount_paid)
    paid_for = int(amount_paid / DEPOSIT_PER_PERSON) if DEPOSIT_PER_PERSON and amount_paid > 0 else 0
    if cash:
        paid_for = cash_ppl or 0

    if status == 'PAID' and still_owed > 0:
        status = 'UNDERPAID'
    if status == 'UNPAID' and not phone and not email:
        status = 'UNCONTACTABLE'

    if stripe_id:
        if stripe_id in seen_stripe_ids:
            notes += ' [DUPLICATE Stripe ID]'
        seen_stripe_ids.add(stripe_id)

    report_rows.append({
        'name': name, 'phone': phone, 'email': paid_email or email,
        'time': time, 'size': size, 'status': status,
        'amount_paid': amount_paid, 'expected': expected,
        'still_owed': still_owed, 'paid_for': paid_for,
        'stripe_id': stripe_id, 'notes': notes,
    })

# ── Unmatched Stripe Deposits ──
# Payments that don't match any reservation
matched_emails = set()
for rr in report_rows:
    if rr['email']:
        matched_emails.add(rr['email'])
    if rr.get('stripe_id'):
        matched_emails.add(rr['email'])

# Also check crossref for matched payments
crossref_matched_emails = set()
for cr_name, cr_data in crossref.items():
    if cr_data.get('email'):
        crossref_matched_emails.add(cr_data['email'].lower())

unmatched = []
for p in payments:
    pe = p['email'].lower() if p['email'] else ''
    if pe not in matched_emails and pe not in crossref_matched_emails:
        unmatched.append(p)

# Also check - which payments from crossref are not matched to today's reservations
# For Jul 19, the crossref already has matches, so most payments are accounted for
# But some might be NEW unmatched

print(f"Unmatched deposits: {len(unmatched)}")
for u in unmatched:
    print(f"   ${u['amount']:.0f} ({int(u['amount']/45)} dep) — {u['email']} — {u['pi_id'][:18]}... — {u['date']}")

# ── Step 5: Build categories ──
paid_rows = [r for r in report_rows if r['status'] == 'PAID']
underpaid_rows = [r for r in report_rows if r['status'] == 'UNDERPAID']
unpaid_rows = [r for r in report_rows if r['status'] in ('UNPAID', 'UNCONTACTABLE')]
total_res = len(report_rows)
total_paid = sum(r['amount_paid'] for r in report_rows)
total_owed = sum(r['still_owed'] for r in report_rows)
total_expected = sum(r['expected'] for r in report_rows)

# ── Step 6: Generate HTML ──
today_str = "July 20, 2026"
timestamp = "20260720_0800"

html_path = OUT_DIR / f"bbg_diagnostic_{timestamp}.html"
pdf_path = OUT_DIR / f"bbg_diagnostic_{timestamp}.pdf"

def phone_display(phone):
    if not phone:
        return '<span class="nc">—</span>'
    if any(c.isdigit() for c in phone) and len(phone) > 6 and '****' in phone:
        return f'<span class="nc">{phone}</span>'
    return phone

def badge(status):
    m = {'PAID': 'badge-paid', 'UNDERPAID': 'badge-under', 'UNPAID': 'badge-unpaid',
         'UNCONTACTABLE': 'badge-unpaid', 'CASH': 'badge-cash'}
    cls = m.get(status, 'badge-unpaid')
    return f'<span class="badge {cls}">{status}</span>'

# ── Sort unpaid: full phone > partial phone > email only > nothing ──
def sort_key(r):
    p = r['phone']
    e = r['email']
    if p and '****' not in p:
        return 0  # full phone
    elif p and '****' in p:
        return 1  # partial phone
    elif e and '@' in e:
        return 2  # email only
    else:
        return 3  # nothing

unpaid_rows.sort(key=sort_key)

html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
<title>BBG Diagnostic Report — {today_str}</title>
<style>
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;font-size:11px;margin:20px;color:#1a1a2e;background:#fff}}
h1{{font-size:20px;margin-bottom:2px;color:#1a1a2e}}
.sub{{color:#888;margin-bottom:16px;font-size:11px}}
h2{{font-size:14px;border-bottom:2px solid #1a1a2e;padding-bottom:4px;margin-top:18px;margin-bottom:8px;color:#1a1a2e}}
table{{width:100%;border-collapse:collapse;margin-bottom:14px;font-size:10px}}
th{{background:#1a1a2e;color:#fff;padding:6px 5px;text-align:left;font-size:8px;text-transform:uppercase;letter-spacing:0.5px}}
td{{padding:5px;border-bottom:1px solid #e2e8f0}}
tr.paid{{background:#f0fff4}}tr.underpaid{{background:#fff8e1}}tr.unpaid{{background:#fff5f5}}
tr.stripe-dep{{background:#f0f4ff}}
tr:hover{{background:#f1f5f9!important}}
.badge{{display:inline-block;padding:2px 7px;border-radius:5px;font-size:8px;font-weight:bold;color:#fff;text-transform:uppercase}}
.badge-paid{{background:#22c55e}}.badge-under{{background:#f59e0b;color:#1a1a2e}}.badge-unpaid{{background:#ef4444}}
.badge-stripe{{background:#635bff}}.badge-cash{{background:#10b981}}
.summary-box{{background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;padding:12px 16px;margin-bottom:16px;display:flex;flex-wrap:wrap}}
.stat{{text-align:center;min-width:80px;margin-right:20px;padding:4px 0}}
.stat .num{{font-size:24px;font-weight:bold;display:block;color:#1a1a2e}}
.stat .label{{font-size:8px;color:#888;text-transform:uppercase;letter-spacing:0.3px}}
.nc{{color:#999;font-style:italic}}
.highlight{{font-weight:bold}}
.green{{color:#22c55e}}.yellow{{color:#f59e0b}}.red{{color:#ef4444}}
.footer{{color:#888;font-size:8px;margin-top:20px;border-top:1px solid #e2e8f0;padding-top:8px}}
</style></head><body>

<h1>🏖️ Boardwalk Beer Garden — Diagnostic Report</h1>
<div class="sub">{today_str} | $45/person deposit | Stripe Chrome scrape (Jul 18–20)</div>

<div class="summary-box">
  <div class="stat"><span class="num">{total_res}</span><span class="label">Reservations</span></div>
  <div class="stat"><span class="num" style="color:#22c55e">{len(paid_rows)}</span><span class="label">PAID</span></div>
  <div class="stat"><span class="num" style="color:#f59e0b">{len(underpaid_rows)}</span><span class="label">UNDERPAID</span></div>
  <div class="stat"><span class="num" style="color:#ef4444">{len(unpaid_rows)}</span><span class="label">UNPAID</span></div>
  <div class="stat"><span class="num">${total_paid:,.0f}</span><span class="label">Collected</span></div>
  <div class="stat"><span class="num" style="color:#ef4444">${total_owed:,.0f}</span><span class="label">Still Owed</span></div>
  <div class="stat"><span class="num" style="color:#635bff">{len(unmatched)}</span><span class="label">Unmatched Dep</span></div>
</div>
"""

# ── PAID section ──
if paid_rows:
    html += '<h2>✅ PAID IN FULL</h2>\n<table><tr><th>Name</th><th>Phone</th><th>Email</th><th>Time</th><th>Size</th><th>Paid</th><th>Coverage</th><th>Method</th><th>Stripe ID</th></tr>\n'
    for r in paid_rows:
        cov = f"{r['paid_for']}/{r['size']}p"
        method = 'CASH' if r.get('stripe_id') == '' and r['amount_paid'] > 0 else 'STRIPE'
        sid = r['stripe_id'][:22] + '…' if len(r['stripe_id']) > 22 else r['stripe_id']
        html += f'<tr class="paid"><td>{r["name"]}</td><td>{phone_display(r["phone"])}</td><td>{r["email"] or "—"}</td><td>{r["time"]}</td><td>{r["size"]}</td><td>${r["amount_paid"]:.0f}</td><td>{cov}</td><td>{badge(method)}</td><td style="font-size:7px;color:#888">{sid}</td></tr>\n'
    html += '</table>\n'

# ── UNDERPAID section ──
if underpaid_rows:
    html += '<h2>🟡 UNDERPAID</h2>\n<table><tr><th>Name</th><th>Phone</th><th>Email</th><th>Time</th><th>Size</th><th>Paid</th><th>Expected</th><th>Coverage</th><th>Owed</th><th>Notes</th></tr>\n'
    for r in underpaid_rows:
        cov = f"{r['paid_for']}/{r['size']}p"
        html += f'<tr class="underpaid"><td>{r["name"]}</td><td>{phone_display(r["phone"])}</td><td>{r["email"] or "—"}</td><td>{r["time"]}</td><td>{r["size"]}</td><td>${r["amount_paid"]:.0f}</td><td>${r["expected"]:.0f}</td><td>{cov}</td><td class="highlight yellow">${r["still_owed"]:.0f}</td><td>{r["notes"]}</td></tr>\n'
    html += '</table>\n'

# ── Unmatched Stripe Deposits ──
if unmatched:
    html += '<h2>🔷 Unmatched Stripe Deposits</h2>\n<p style="font-size:9px;color:#888;margin-top:-5px">These Stripe payments are clean $45× deposits but don\'t match any reservation.</p>\n'
    html += '<table><tr><th>Amount</th><th>Deposits</th><th>Email</th><th>Date</th><th>Stripe ID</th></tr>\n'
    for u in unmatched:
        dep_count = int(u['amount'] / 45)
        html += f'<tr class="stripe-dep"><td class="highlight">${u["amount"]:.0f}</td><td>{dep_count}×$45</td><td>{u["email"]}</td><td>{u["date"]}</td><td style="font-size:7px;color:#888">{u["pi_id"][:22]}…</td></tr>\n'
    html += '</table>\n'

# ── UNPAID section ──
if unpaid_rows:
    html += '<h2>❌ UNPAID</h2>\n<table><tr><th>Name</th><th>Phone</th><th>Email</th><th>Time</th><th>Size</th><th>Expected</th><th>Contact Quality</th><th>Notes</th></tr>\n'
    for r in unpaid_rows:
        cq = ''
        p = r['phone']
        e = r['email']
        if p and '****' not in p:
            cq = '📞 Full Phone'
        elif p and '****' in p:
            cq = '📞 Partial Phone'
        elif e and '@' in e:
            cq = '📧 Email'
        else:
            cq = '🚫 UNCONTACTABLE'
        html += f'<tr class="unpaid"><td>{r["name"]}</td><td>{phone_display(r["phone"])}</td><td>{r["email"] or "—"}</td><td>{r["time"]}</td><td>{r["size"]}</td><td>${r["expected"]:.0f}</td><td>{cq}</td><td>{r["notes"]}</td></tr>\n'
    html += '</table>\n'

html += f'<div class="footer">Generated {today_str} 08:00 EDT | Data: Owner.com + Gmail IMAP + Stripe Chrome scrape | Report: bbg_diagnostic_{timestamp}</div>\n</body></html>'

OUT_DIR.mkdir(parents=True, exist_ok=True)
html_path.write_text(html)
print(f"✅ HTML: {html_path}")

# ── Convert to PDF via Chrome headless ──
print("📄 Generating PDF via Chrome headless...")
try:
    # Kill any existing headless Chrome
    subprocess.run(['pkill', '-f', 'Google Chrome.*headless'], capture_output=True, timeout=5)
except:
    pass

result = subprocess.run([
    '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
    '--headless', '--disable-gpu', '--no-sandbox',
    f'--print-to-pdf={pdf_path.resolve()}',
    f'file://{html_path.resolve()}'
], capture_output=True, timeout=20)

if pdf_path.exists():
    print(f"✅ PDF: {pdf_path} ({pdf_path.stat().st_size} bytes)")
else:
    print(f"⚠️ PDF generation may have failed. stderr: {result.stderr.decode()[:200]}")
    # Fallback: try again with pkill
    subprocess.run(['pkill', '-f', 'Google Chrome.*headless'], capture_output=True, timeout=5)
    result = subprocess.run([
        '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
        '--headless', '--disable-gpu', '--no-sandbox',
        f'--print-to-pdf={pdf_path.resolve()}',
        f'file://{html_path.resolve()}'
    ], capture_output=True, timeout=20)
    if pdf_path.exists():
        print(f"✅ PDF (retry): {pdf_path} ({pdf_path.stat().st_size} bytes)")

# ── Step 7: Email PDF to Kato ──
if pdf_path.exists():
    print("📧 Emailing report...")
    with open(Path.home() / '.rex_gmail_imap.json') as f:
        creds = json.load(f)

    msg = MIMEMultipart()
    msg['From'] = creds['email']
    msg['To'] = 'atigerclawai@gmail.com'
    msg['Subject'] = f'BBG Diagnostic Report — {today_str}'

    summary_lines = [
        f"BBG Payment Diagnostic — {today_str}",
        "",
        f"Reservations: {total_res}",
        f"PAID: {len(paid_rows)}",
        f"UNDERPAID: {len(underpaid_rows)}",
        f"UNPAID: {len(unpaid_rows)}",
        f"Total collected: ${total_paid:,.0f}",
        f"Total still owed: ${total_owed:,.0f}",
        f"Unmatched Stripe deposits: {len(unmatched)}"
    ]
    if unmatched:
        summary_lines.append("")
        summary_lines.append("⚠️ Unmatched deposits found:")
        for u in unmatched:
            summary_lines.append(f"   ${u['amount']:.0f} ({int(u['amount']/45)} dep) — {u['email']}")
    summary_lines.append("")
    summary_lines.append("Full report attached as PDF.")

    msg.attach(MIMEText('\n'.join(summary_lines), 'plain'))

    with open(pdf_path, 'rb') as f:
        part = MIMEBase('application', 'pdf')
        part.set_payload(f.read())
        encoders.encode_base64(part)
        part.add_header('Content-Disposition', 'attachment', filename=pdf_path.name)
        msg.attach(part)

    try:
        server = smtplib.SMTP_SSL('smtp.gmail.com', 465)
        server.login(creds['email'], creds['app_password'])
        server.send_message(msg)
        server.quit()
        print("✅ PDF emailed to atigerclawai@gmail.com")
    except Exception as e:
        print(f"⚠️ SMTP SSL failed: {e}")
        # Fallback to port 587 with STARTTLS
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(creds['email'], creds['app_password'])
        server.send_message(msg)
        server.quit()
        print("✅ PDF emailed via STARTTLS")

# ── Print summary for report ──
print("\n" + "="*60)
print("RECONCILIATION SUMMARY")
print("="*60)
for r in report_rows:
    print(f"  {r['status']:15s} | {r['name']:20s} | {r['size']}p | ${r['amount_paid']:>5.0f}/${r['expected']:>5.0f} | {r['email'] or 'no email':30s} | {r['phone'] or 'no phone':20s}")
if unmatched:
    print(f"\n⚠️ {len(unmatched)} UNMATCHED DEPOSITS:")
    for u in unmatched:
        print(f"   ${u['amount']:.0f} ({int(u['amount']/45)} dep) — {u['email']} — {u['date']}")
print(f"\nTotal: {total_res} reservations | ${total_paid:,.0f} collected | ${total_owed:,.0f} still owed")
