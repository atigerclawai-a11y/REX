#!/usr/bin/env python3
"""Build the BBG Diagnostic HTML Report from bridge JSON and generate PDF."""
import json, subprocess, sys
from pathlib import Path
from datetime import datetime, timezone

DEPOSIT_PER_PERSON = 45
OUTPUT_DIR = Path.home() / "Desktop/REX/output"
timestamp = datetime.now().strftime("%Y%m%d_%H%M")
today_str = datetime.now().strftime("%B %d, %Y")

# Load bridge JSON
json_path = OUTPUT_DIR / "bbg_payments_20260719_2350.json"
with open(json_path) as f:
    entries = json.load(f)

# Fix Yan — $41 is NOT a $45 deposit multiple
for e in entries:
    if e["name"] == "Yan" and e["amount_paid"] == 41.0:
        e["payment"] = "UNPAID"
        e["amount_paid"] = 0.0
        e["still_owed"] = e["expected"]
        e["paid_for"] = 0
        e["stripe_id"] = ""
        e["notes"] = (e.get("notes", "") + " | ⚠️ $41 Stripe charge NOT a deposit (not $45x multiple)").strip(" |")

# Categorize
paid = [e for e in entries if e["payment"] == "PAID" and e["still_owed"] <= 0]
underpaid = [e for e in entries if e["payment"] in ("PAID", "CASH") and e["still_owed"] > 0]
unpaid = [e for e in entries if e["payment"] == "UNPAID"]
cash_entries = [e for e in entries if e["payment"] == "CASH"]

# Also move CASH entries that are fully paid to PAID section
fully_paid_cash = [e for e in cash_entries if e["still_owed"] == 0]
underpaid_cash = [e for e in cash_entries if e["still_owed"] > 0]
paid.extend(fully_paid_cash)
underpaid.extend(underpaid_cash)

# Remove from unpaid any that should be uncontactable
uncontactable = [e for e in unpaid if not e.get("phone") and not e.get("email")]
unpaid_contactable = [e for e in unpaid if e.get("phone") or e.get("email")]

# Compute summary
total_res = len(entries)
total_guests = sum(e["size"] for e in entries)
total_paid_amount = sum(e["amount_paid"] for e in entries if e["payment"] in ("PAID", "CASH"))
total_expected = sum(e["expected"] for e in entries)
total_owed = total_expected - total_paid_amount
paid_count = len(paid)
underpaid_count = len(underpaid)
unpaid_count = len(unpaid)
uncontactable_count = len(uncontactable)

# Format helpers
def fmt_phone(p):
    if not p:
        return ""
    if "****" in p:
        return f'<span class="nc">{p}</span>'
    return p

def fmt_amount(amt):
    if amt == 0:
        return "$0"
    return f"${amt:,.0f}"

def fmt_badge(status):
    badges = {
        "PAID": '<span class="badge badge-paid">PAID</span>',
        "CASH": '<span class="badge badge-cash">CASH</span>',
        "UNDERPAID": '<span class="badge badge-under">UNDER</span>',
        "UNPAID": '<span class="badge badge-unpaid">UNPAID</span>',
        "UNCONTACTABLE": '<span class="badge badge-unpaid" style="background:#999">NO CONTACT</span>',
    }
    return badges.get(status, "")

def fmt_method(e):
    if e.get("payment") == "CASH":
        return "CASH"
    if e.get("stripe_id"):
        return "STRIPE"
    return "—"

def build_row(e, css_class):
    status = e["payment"]
    if status == "UNPAID" and not e.get("phone") and not e.get("email"):
        status = "UNCONTACTABLE"
    elif status == "PAID" and e["still_owed"] > 0:
        status = "UNDERPAID"
    elif status == "CASH" and e["still_owed"] > 0:
        status = "UNDERPAID"
    
    coverage = f"{e['paid_for']}/{e['size']}" if e['paid_for'] > 0 else "0"
    return f"""<tr class="{css_class}">
    <td>{e['name']}</td>
    <td>{fmt_phone(e.get('phone', ''))}</td>
    <td>{e.get('email', '')}</td>
    <td>{e.get('time', '')}</td>
    <td style="text-align:center">{e['size']}</td>
    <td style="text-align:right">{fmt_amount(e['amount_paid'])}</td>
    <td style="text-align:center">{coverage}</td>
    <td style="text-align:center">{fmt_method(e)}</td>
    <td style="text-align:right">{fmt_amount(e['still_owed'])}</td>
    <td>{fmt_badge(status)}</td>
    <td style="font-size:7px;color:#999">{e.get('stripe_id', '')}</td>
</tr>"""

# Build HTML
html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
<title>BBG Diagnostic — {today_str}</title>
<style>
body{{font-family:-apple-system,BlinkMacSystemFont,sans-serif;font-size:10px;margin:15px;color:#1a1a2e}}
h1{{font-size:18px;margin-bottom:2px}}
.sub{{color:#888;margin-bottom:12px;font-size:11px}}
h2{{font-size:13px;border-bottom:2px solid #1a1a2e;padding-bottom:3px;margin-top:18px}}
table{{width:100%;border-collapse:collapse;margin-bottom:14px}}
th{{background:#1a1a2e;color:#fff;padding:5px 4px;text-align:left;font-size:8px;text-transform:uppercase}}
td{{padding:4px;border-bottom:1px solid #ddd;font-size:9px}}
tr.paid{{background:#f0fff4}}tr.underpaid{{background:#fff8e1}}tr.unpaid{{background:#fff5f5}}
tr.stripe-dep{{background:#f0f4ff}}
.badge{{padding:2px 6px;border-radius:8px;font-size:8px;font-weight:700;color:#fff;white-space:nowrap}}
.badge-paid{{background:#22c55e}}.badge-under{{background:#f59e0b}}.badge-unpaid{{background:#ef4444}}
.badge-stripe{{background:#635bff}}.badge-cash{{background:#10b981}}
.summary-box{{background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;padding:12px;margin-bottom:14px;display:flex;flex-wrap:wrap;gap:10px}}
.stat{{text-align:center;min-width:75px;padding:4px 8px}}
.stat .num{{font-size:22px;font-weight:bold}}
.stat .label{{font-size:8px;color:#888;text-transform:uppercase}}
.stat.green .num{{color:#22c55e}}.stat.yellow .num{{color:#f59e0b}}.stat.red .num{{color:#ef4444}}
.nc{{color:#999;font-style:italic}}.highlight{{font-weight:bold}}
.footer{{color:#888;font-size:8px;margin-top:18px;border-top:1px solid #eee;padding-top:8px}}
</style></head><body>
<h1>🏖️ Boardwalk Beer Garden — Diagnostic Report</h1>
<div class="sub">{today_str} | 💵 $45/person deposit | Stripe acct_1SOMQnIC68Kv9IV5 | 48h window</div>

<div class="summary-box">
  <div class="stat"><div class="num">{total_res}</div><div class="label">Reservations</div></div>
  <div class="stat"><div class="num">{total_guests}</div><div class="label">Guests</div></div>
  <div class="stat green"><div class="num">{paid_count}</div><div class="label">PAID IN FULL</div></div>
  <div class="stat yellow"><div class="num">{underpaid_count}</div><div class="label">UNDERPAID</div></div>
  <div class="stat red"><div class="num">{unpaid_count}</div><div class="label">UNPAID</div></div>
  <div class="stat"><div class="num">{uncontactable_count}</div><div class="label">NO CONTACT</div></div>
  <div class="stat green"><div class="num">{fmt_amount(total_paid_amount)}</div><div class="label">Collected</div></div>
  <div class="stat red"><div class="num">{fmt_amount(total_owed)}</div><div class="label">Still Owed</div></div>
  <div class="stat"><div class="num">{fmt_amount(total_expected)}</div><div class="label">Expected Total</div></div>
</div>

<h2>✅ PAID IN FULL ({len(paid)})</h2>
<table>
<tr><th>Name</th><th>Phone</th><th>Email</th><th>Time</th><th>Sz</th><th>Paid</th><th>Cov</th><th>Mtd</th><th>Owed</th><th>Status</th><th>Stripe ID</th></tr>
{"".join(build_row(e, "paid") for e in paid)}
</table>

<h2>⚠️ UNDERPAID ({len(underpaid)})</h2>
<table>
<tr><th>Name</th><th>Phone</th><th>Email</th><th>Time</th><th>Sz</th><th>Paid</th><th>Cov</th><th>Mtd</th><th>Owed</th><th>Status</th><th>Stripe ID</th></tr>
{"".join(build_row(e, "underpaid") for e in underpaid)}
</table>

<h2>📞 UNPAID — Contact Info Available ({len(unpaid_contactable)})</h2>
<table>
<tr><th>Name</th><th>Phone</th><th>Email</th><th>Time</th><th>Sz</th><th>Paid</th><th>Cov</th><th>Mtd</th><th>Owed</th><th>Status</th><th>Notes</th></tr>
{"".join(build_row(e, "unpaid") for e in unpaid_contactable)}
</table>

<h2>🚫 UNCONTACTABLE — No Phone or Email ({len(uncontactable)})</h2>
<table>
<tr><th>Name</th><th>Phone</th><th>Email</th><th>Time</th><th>Sz</th><th>Paid</th><th>Cov</th><th>Mtd</th><th>Owed</th><th>Status</th><th>Notes</th></tr>
{"".join(build_row(e, "unpaid") for e in uncontactable)}
</table>

<div class="footer">
Generated {datetime.now().strftime("%B %d, %Y at %I:%M %p")} EDT | 
💰 Deposit rate: $45/person | 🔒 48-hour payment window (Jul 18–19) | 
⚠️ Yan's $41 Stripe charge excluded (not a $45 deposit multiple) | 
⚠️ Alex Zhik / Alex Kaplun / Alex share pi_3TulN9 (credited to first match)
</div>
</body></html>"""

# Write HTML
html_path = OUTPUT_DIR / f"bbg_diagnostic_{timestamp}.html"
html_path.write_text(html)
print(f"✅ HTML: {html_path}")

# Convert to PDF via Chrome headless
pdf_path = OUTPUT_DIR / f"bbg_diagnostic_{timestamp}.pdf"

# Kill any existing headless Chrome first
subprocess.run(["pkill", "-f", "Google Chrome.*headless"], capture_output=True)

result = subprocess.run([
    '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
    '--headless', '--disable-gpu', '--no-sandbox', '--no-first-run',
    '--disable-extensions', '--disable-background-networking',
    f'--print-to-pdf={pdf_path.resolve()}',
    f'file://{html_path.resolve()}'
], capture_output=True, text=True, timeout=20)

if pdf_path.exists():
    size_kb = pdf_path.stat().st_size / 1024
    print(f"✅ PDF: {pdf_path} ({size_kb:.1f} KB)")
else:
    print(f"❌ PDF generation failed: {result.stderr[:500]}")
    sys.exit(1)

# Output summary for email body
print(f"\n--- SUMMARY ---")
print(f"Reservations: {total_res} | Guests: {total_guests}")
print(f"PAID: {paid_count} (${total_paid_amount:,.0f})")
print(f"UNDERPAID: {underpaid_count}")
print(f"UNPAID: {unpaid_count} ({uncontactable_count} uncontactable)")
print(f"Still owed: ${total_owed:,.0f}")
print(f"PDF: {pdf_path}")
print(f"--- END SUMMARY ---")
