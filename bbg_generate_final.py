#!/usr/bin/env python3
"""BBG Final Call Sheet — cross-reference reservations with Stripe payments, generate HTML + PDF."""

import json
from pathlib import Path
from datetime import datetime

RESERVATIONS_PATH = Path.home() / "Desktop/REX/CC_bbg_reservations.json"
HTML_PATH = Path.home() / "Desktop/REX/bbg_final.html"
PDF_PATH = Path.home() / "Desktop/REX/bbg_final.pdf"

DEPOSIT_RATE = 45  # $45/person

# ── Stripe payments (pre-extracted) ──────────────────────────────────────────
PAYMENTS = [
    ("maxikny@gmail.com",          540.00, "Max Goldenko"),
    ("kirill.likovv@gmail.com",    225.00, "Kirill Likov"),
    ("alexander.zhik@gmail.com",   225.00, "Alexander Zhik"),
    ("stevenr303@gmail.com",        90.00, "Steven Reyser"),
    ("benjaminwmourier@gmail.com", 180.00, "Benjamin Mourier"),
    ("ednovo64@gmail.com",         540.00, "Edward Novogrudsky"),
    ("valery013013@gmail.com",     360.00, "Valery Streltsov"),
    ("cashcashwinnie@gmail.com",   135.00, "Ping"),
    ("romanice9999@gmail.com",      90.00, "Roman Melnyk"),
    ("bossangeles1@yahoo.com",      90.00, "Anjelika Boss"),
    ("eleonorapankratova@gmail.com",45.00, "Eleonora Pankratova"),
    ("spivas@gmail.com",           315.00, "Vasile Spinei"),
    ("anevryanskiy@gmail.com",      41.00, ""),
    ("kahany15@aim.com",           680.00, ""),
    ("jamiemichellecohen@gmail.com",40.00, ""),
    ("lucia_stein@yahoo.com",       15.46, ""),
    ("aquace4@yahoo.com",          106.38, ""),
]

# ── Payment-to-reservation matching rules ────────────────────────────────────
# (payment_index, reservation_id) — manually determined
MATCHES = [
    (0,  29),   # maxikny@gmail.com → Max (id:29, 8p)
    (1,   4),   # kirill.likovv@gmail.com → Kirril (id:4, 5p)
    (2,  21),   # alexander.zhik@gmail.com → Alex Zhik (id:21, 7p)
    (4,  19),   # benjaminwmourier@gmail.com → Benjamin M (id:19, 4p)
    (6,   3),   # valery013013@gmail.com → Valery (id:3, 7p)
    (7,  22),   # cashcashwinnie@gmail.com → Ping (id:22, 3p)
    (8,  27),   # romanice9999@gmail.com → Roman (id:27, 4p)
    (9,  10),   # bossangeles1@yahoo.com → Angelica (id:10, 4p)
]

# ── Load & filter reservations ───────────────────────────────────────────────
with open(RESERVATIONS_PATH) as f:
    all_res = json.load(f)

TODAY = "2026-07-19"
reservations = [r for r in all_res if r.get("reservation_date") == TODAY]

# ── Build match lookup ───────────────────────────────────────────────────────
# reservation_id → (payment_email, amount, payee, deposited_for)
res_payment = {}
for pi, rid in MATCHES:
    email, amt, payee = PAYMENTS[pi]
    deposited_for = round(amt / DEPOSIT_RATE)  # integer number of people
    res_payment[rid] = (email, amt, payee, deposited_for)

# Track which payment indices are used
used_payments = set(pi for pi, rid in MATCHES)

# ── Build rows ───────────────────────────────────────────────────────────────
rows = []

for r in reservations:
    rid = r["id"]
    name = r["party_name"]
    phone = r.get("phone", "")
    email = r.get("email", "")
    time_str = r["reservation_time"]
    party_size = r["party_size"]
    notes = r.get("notes", "")
    source = r.get("source", "")

    # Extract email from notes if not in email field
    if not email and "Email:" in notes:
        email = notes.split("Email:")[1].split("|")[0].strip()

    payment_info = res_payment.get(rid)

    if payment_info:
        pay_email, pay_amt, payee, deposited_for = payment_info
        diff = deposited_for - party_size
        status = "PAID"
        payment_str = f"${pay_amt:,.2f}"
    else:
        pay_email = ""
        pay_amt = 0
        payee = ""
        deposited_for = 0
        diff = -party_size  # all unpaid people
        status = "UNPAID"
        payment_str = "$0.00"

    rows.append({
        "name": name,
        "phone": phone,
        "email": email,
        "time": time_str,
        "reserved": party_size,
        "deposited_for": deposited_for,
        "diff": diff,
        "payment": payment_str,
        "payee": payee,
        "pay_email": pay_email,
        "status": status,
        "notes": notes,
        "source": source,
        "rid": rid,
    })

# ── Add payment-only rows (no reservation match) ────────────────────────────
for pi, (email, amt, payee) in enumerate(PAYMENTS):
    if pi in used_payments:
        continue
    deposited_for = round(amt / DEPOSIT_RATE)
    rows.append({
        "name": payee if payee else f"(Payment: {email})",
        "phone": "",
        "email": email,
        "time": "—",
        "reserved": 0,
        "deposited_for": deposited_for,
        "diff": deposited_for,  # all deposited, no reservation
        "payment": f"${amt:,.2f}",
        "payee": payee,
        "pay_email": email,
        "status": "PAID (no res)",
        "notes": "NO RESERVATION FOUND — walk-in or different date",
        "source": "stripe",
        "rid": None,
    })

# ── Sort: UNPAID first, then by time ────────────────────────────────────────
def sort_key(row):
    status_order = 0 if row["status"] == "UNPAID" else (1 if "PAID" in row["status"] else 2)
    # Parse time for sorting
    try:
        t = datetime.strptime(row["time"], "%I:%M %p")
        time_sort = t.hour * 60 + t.minute
    except ValueError:
        time_sort = 9999  # "—" goes to the end
    return (status_order, time_sort, row["name"])

rows.sort(key=sort_key)

# ── Compute counts ───────────────────────────────────────────────────────────
total = len(rows)
paid_count = sum(1 for r in rows if r["status"] == "PAID")
paid_no_res_count = sum(1 for r in rows if r["status"] == "PAID (no res)")
unpaid_count = sum(1 for r in rows if r["status"] == "UNPAID")
with_phone = sum(1 for r in rows if r["phone"] and r["phone"].strip())
no_phone = sum(1 for r in rows if not r["phone"] or not r["phone"].strip())
masked_phone = sum(1 for r in rows if "****" in r["phone"])
total_guests = sum(r["reserved"] for r in rows)
total_deposited = sum(r["deposited_for"] for r in rows)

# ── Generate HTML ────────────────────────────────────────────────────────────
html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>BBG Final Call Sheet — {TODAY}</title>
<style>
  @page {{
    size: landscape;
    margin: 0.5in;
  }}
  * {{
    margin: 0;
    padding: 0;
    box-sizing: border-box;
  }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif;
    font-size: 11px;
    color: #1a1a1a;
    background: #fff;
    padding: 20px;
  }}
  h1 {{
    font-size: 20px;
    margin-bottom: 2px;
    color: #111;
  }}
  .summary {{
    display: flex;
    gap: 24px;
    margin: 8px 0 16px;
    flex-wrap: wrap;
  }}
  .stat {{
    background: #f5f5f5;
    padding: 6px 14px;
    border-radius: 6px;
    font-size: 12px;
  }}
  .stat strong {{
    color: #1a1a1a;
  }}
  .stat.paid {{ border-left: 3px solid #22c55e; }}
  .stat.unpaid {{ border-left: 3px solid #ef4444; }}
  .stat.info {{ border-left: 3px solid #3b82f6; }}

  table {{
    width: 100%;
    border-collapse: collapse;
    font-size: 10px;
  }}
  th {{
    background: #1a1a1a;
    color: white;
    padding: 8px 6px;
    text-align: left;
    font-weight: 600;
    font-size: 10px;
    white-space: nowrap;
    position: sticky;
    top: 0;
  }}
  td {{
    padding: 6px 6px;
    border-bottom: 1px solid #e5e5e5;
    vertical-align: top;
  }}
  tr.paid-row {{
    background: #f0fdf4;
  }}
  tr.paid-row:hover {{
    background: #dcfce7;
  }}
  tr.unpaid-row {{
    background: #fef2f2;
  }}
  tr.unpaid-row:hover {{
    background: #fee2e2;
  }}
  tr.paid-no-res {{
    background: #eff6ff;
  }}
  tr.paid-no-res:hover {{
    background: #dbeafe;
  }}
  .badge {{
    display: inline-block;
    padding: 2px 8px;
    border-radius: 10px;
    font-size: 9px;
    font-weight: 700;
    text-transform: uppercase;
  }}
  .badge-paid {{ background: #22c55e; color: white; }}
  .badge-unpaid {{ background: #ef4444; color: white; }}
  .badge-warn {{ background: #f59e0b; color: white; }}
  .diff-pos {{ color: #16a34a; font-weight: 700; }}
  .diff-neg {{ color: #dc2626; font-weight: 700; }}
  .diff-zero {{ color: #6b7280; }}
  .notes-cell {{
    max-width: 200px;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    color: #6b7280;
    font-style: italic;
  }}
  .phone-masked {{
    color: #9ca3af;
  }}
  .section-header {{
    background: #f9fafb !important;
    font-weight: 700;
    font-size: 11px;
    color: #374151;
    border-top: 2px solid #d1d5db;
  }}
  .section-header td {{
    padding: 10px 6px;
  }}
  .col-name {{ min-width: 130px; }}
  .col-phone {{ min-width: 110px; }}
  .col-email {{ min-width: 160px; }}
  .col-time {{ min-width: 70px; }}
  .col-res {{ min-width: 55px; text-align: center; }}
  .col-dep {{ min-width: 70px; text-align: center; }}
  .col-diff {{ min-width: 55px; text-align: center; }}
  .col-pay {{ min-width: 70px; text-align: right; }}
  .col-payee {{ min-width: 120px; }}
  .col-status {{ min-width: 70px; text-align: center; }}
  .col-notes {{ min-width: 150px; }}

  @media print {{
    body {{ padding: 0; }}
    table {{ font-size: 9px; }}
    th, td {{ padding: 4px 4px; }}
  }}
</style>
</head>
<body>

<h1>🍻 BBG Final Call Sheet — {TODAY}</h1>

<div class="summary">
  <div class="stat info"><strong>{total}</strong> total entries</div>
  <div class="stat paid"><strong>{paid_count}</strong> PAID</div>
  <div class="stat unpaid"><strong>{unpaid_count}</strong> UNPAID</div>
  <div class="stat info"><strong>{total_guests}</strong> guests reserved</div>
  <div class="stat info"><strong>{total_deposited}</strong> guests deposited</div>
  <div class="stat info"><strong>{with_phone}</strong> with phone</div>
  <div class="stat info"><strong>{no_phone}</strong> no phone</div>
  <div class="stat info"><strong>{masked_phone}</strong> masked phone</div>
</div>

<table>
<thead>
  <tr>
    <th class="col-name">NAME</th>
    <th class="col-phone">PHONE</th>
    <th class="col-email">EMAIL</th>
    <th class="col-time">TIME</th>
    <th class="col-res">RESERVED</th>
    <th class="col-dep">DEPOSITED FOR</th>
    <th class="col-diff">DIFF</th>
    <th class="col-pay">PAYMENT</th>
    <th class="col-payee">PAYEE</th>
    <th class="col-status">STATUS</th>
    <th class="col-notes">NOTES</th>
  </tr>
</thead>
<tbody>
"""

# Track sections
current_status = None
section_names = {"UNPAID": "🔴 UNPAID — needs follow-up", "PAID": "🟢 PAID — confirmed", "PAID (no res)": "🔵 PAID (no matching reservation)"}

for row in rows:
    if row["status"] != current_status:
        current_status = row["status"]
        section_label = section_names.get(current_status, current_status)
        html += f"""  <tr class="section-header"><td colspan="11">{section_label} ({sum(1 for r in rows if r['status'] == current_status)} entries)</td></tr>
"""

    row_class = {"UNPAID": "unpaid-row", "PAID": "paid-row", "PAID (no res)": "paid-no-res"}.get(row["status"], "")

    badge_class = {"UNPAID": "badge-unpaid", "PAID": "badge-paid", "PAID (no res)": "badge-warn"}.get(row["status"], "")

    # Diff styling
    diff_val = row["diff"]
    if diff_val > 0:
        diff_class = "diff-pos"
        diff_str = f"+{diff_val}"
    elif diff_val < 0:
        diff_class = "diff-neg"
        diff_str = str(diff_val)
    else:
        diff_class = "diff-zero"
        diff_str = "0"

    # Phone styling
    phone_display = row["phone"] if row["phone"] else "—"
    phone_class = "phone-masked" if "****" in row["phone"] else ""

    # Email
    email_display = row["email"] if row["email"] else "—"

    # Notes
    notes_display = row["notes"] if row["notes"] else "—"

    # Time
    time_display = row["time"]

    html += f"""  <tr class="{row_class}">
    <td class="col-name"><strong>{row['name']}</strong></td>
    <td class="col-phone {phone_class}">{phone_display}</td>
    <td class="col-email" style="font-size:9px;">{email_display}</td>
    <td class="col-time">{time_display}</td>
    <td class="col-res">{row['reserved']}</td>
    <td class="col-dep">{row['deposited_for']}</td>
    <td class="col-diff"><span class="{diff_class}">{diff_str}</span></td>
    <td class="col-pay">{row['payment']}</td>
    <td class="col-payee">{row['payee']}</td>
    <td class="col-status"><span class="badge {badge_class}">{row['status']}</span></td>
    <td class="col-notes notes-cell" title="{notes_display}">{notes_display}</td>
  </tr>
"""

html += """</tbody>
</table>

<div style="margin-top: 16px; padding: 12px; background: #f9fafb; border-radius: 8px; font-size: 10px; color: #6b7280;">
  <strong>Legend:</strong>
  <span style="display:inline-block;width:12px;height:12px;background:#f0fdf4;border:1px solid #22c55e;border-radius:2px;margin:0 4px 0 12px;vertical-align:middle;"></span> PAID —
  <span style="display:inline-block;width:12px;height:12px;background:#fef2f2;border:1px solid #ef4444;border-radius:2px;margin:0 4px 0 12px;vertical-align:middle;"></span> UNPAID —
  <span style="display:inline-block;width:12px;height:12px;background:#eff6ff;border:1px solid #3b82f6;border-radius:2px;margin:0 4px 0 12px;vertical-align:middle;"></span> PAID (no matching reservation)
  &nbsp;|&nbsp; Deposit rate: $45/person
  &nbsp;|&nbsp; DIFF = DEPOSITED_FOR − RESERVED
  &nbsp;|&nbsp; Generated {datetime.now().strftime('%b %d, %Y at %I:%M %p')}
</div>

</body>
</html>"""

# ── Write HTML ───────────────────────────────────────────────────────────────
HTML_PATH.write_text(html)
print(f"✅ HTML written: {HTML_PATH} ({len(html):,} bytes)")

# ── Print summary ────────────────────────────────────────────────────────────
print(f"""
📊 BBG FINAL CALL SHEET SUMMARY — {TODAY}
{'='*55}
  Total entries:       {total}
  PAID:                {paid_count}
  PAID (no res):       {paid_no_res_count}
  UNPAID:              {unpaid_count}
  Total guests:        {total_guests}
  Total deposited for: {total_deposited}
  With phone:          {with_phone}
  No phone:            {no_phone}
  Masked phone:        {masked_phone}
{'='*55}
""")

# ── Print detailed breakdown ─────────────────────────────────────────────────
print("🔴 UNPAID RESERVATIONS:")
for row in rows:
    if row["status"] == "UNPAID":
        print(f"  {row['time']} | {row['name']:25s} | {row['reserved']}p | {row['phone'] or '—':20s} | {row['notes'][:50]}")

print(f"\n🟢 PAID RESERVATIONS:")
for row in rows:
    if row["status"] == "PAID":
        diff_str = f"+{row['diff']}" if row['diff'] > 0 else str(row['diff'])
        print(f"  {row['time']} | {row['name']:25s} | {row['reserved']}p | dep:{row['deposited_for']} | diff:{diff_str} | {row['payment']} | {row['payee']}")

print(f"\n🔵 PAYMENT-ONLY (no reservation match):")
for row in rows:
    if row["status"] == "PAID (no res)":
        print(f"  {row['name']:30s} | {row['payment']:>8s} | dep:{row['deposited_for']} | {row['email']}")
