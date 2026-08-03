#!/usr/bin/env python3
"""
CC_stripe_bridge.py — Stripe Dashboard Bridge
Scrapes Stripe dashboard via Chrome session for BBG payment data.
Cross-references with reservation DB. No API key needed — uses Chrome cookies.

Usage:
  python3 CC_stripe_bridge.py              # Pull payments, update DB, print report
  python3 CC_stripe_bridge.py --report     # Print report only (no DB update)
  python3 CC_stripe_bridge.py --csv        # Output CSV to output/ directory
"""

import json, csv, re, sqlite3, subprocess, sys, os
from pathlib import Path
from datetime import datetime

REX_DIR = Path.home() / "Desktop" / "REX"
DB = REX_DIR / "CC_bbg_contacts.db"
JSON = REX_DIR / "CC_bbg_reservations.json"
OUT = REX_DIR / "output"
DEPOSIT_PER_PERSON = 45

def scrape_stripe():
    """Scrape Stripe dashboard payments via Chrome."""
    # Navigate Chrome to payments page.
    # NOTE: the ?status=successful filter URL renders a dashboard error
    # ("Something went wrong. Please try again later.") — use the plain
    # /payments URL and filter Succeeded rows client-side instead.
    subprocess.run([
        "osascript", "-e",
        'tell application "Google Chrome" to set URL of active tab of front window to "https://dashboard.stripe.com/payments"'
    ], capture_output=True)
    import time; time.sleep(8)

    # Extract payment data via JavaScript.
    # Raw string keeps regex backslashes intact; the .replace() calls below
    # escape backslashes and double quotes for the AppleScript string literal.
    js_code = r"""
(function() {
  var rows = document.querySelectorAll("tbody tr");
  var payments = [];
  var emailRe = /[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}/;
  for (var i = 0; i < rows.length; i++) {
    var cells = rows[i].querySelectorAll("td");
    var pi_id = "", email = "", amount = "", date = "", time = "", status = "";
    for (var j = 0; j < cells.length; j++) {
      var t = cells[j].textContent.trim();
      if (!pi_id) { var pm = t.match(/pi_[a-zA-Z0-9]{24}/); if (pm) pi_id = pm[0]; }
      if (!email) { var em = t.match(emailRe); if (em && !t.match(/pi_/)) email = em[0]; }
      if (!amount) { var am = t.match(/\$([\d,.]+)/); if (am) amount = am[1]; }
      if (!status) { var sm = t.match(/(Partially reversed|Refunded|Canceled|Succeeded|Failed|Disputed)/); if (sm) status = sm[0]; }
      if (!date) { var dm = t.match(/([A-Z][a-z]{2}\s+\d{1,2},?)/); if (dm) date = dm[0]; }
      if (!time) { var tm = t.match(/(\d{1,2}:\d{2}\s+[AP]M)/); if (tm) time = tm[0]; }
    }
    if (pi_id) {
      payments.push({pi_id: pi_id, email: email, amount: amount, date: date, time: time, status: status});
    }
  }
  return JSON.stringify(payments);
})()
"""
    js_escaped = js_code.replace("\\", "\\\\").replace('"', '\\"')
    result = subprocess.run([
        "osascript", "-e",
        f'tell application "Google Chrome" to execute active tab of front window javascript "{js_escaped}"'
    ], capture_output=True, text=True, timeout=20)

    # Parse the output
    raw = result.stdout.strip()
    try:
        entries = json.loads(raw)
    except json.JSONDecodeError:
        # Try to extract from mangled output
        entries = []
        for match in re.finditer(r'pi_([a-zA-Z0-9]{24}).*?([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}).*?(\d{1,2}:\d{2}\s+[AP]M)', raw):
            entries.append({
                'pi_id': f"pi_{match.group(1)}",
                'email': match.group(2),
                'time': match.group(3),
                'amount': '0',
                'date': '',
                'status': ''
            })

    # Clean up PI IDs and emails
    clean = []
    for entry in entries:
        pi_text = entry.get('pi_id', '')
        email_text = entry.get('email', '')

        pi_match = re.search(r'(pi_[a-zA-Z0-9]{24})', pi_text)
        pi_id = pi_match.group(1) if pi_match else pi_text

        email_match = re.search(r'([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})', email_text)
        email = email_match.group(1) if email_match else email_text

        status = entry.get('status', '')

        if pi_id and pi_id != 'pi_' and status in ('', 'Succeeded'):  # Valid PI ID, successful only
            clean.append({
                'pi_id': pi_id,
                'email': email,
                'amount': float(entry.get('amount', '0').replace(',', '')),
                'date': entry.get('date', ''),
                'time': entry.get('time', ''),
            })

    return clean

def load_reservations():
    """Load today's reservations from JSON."""
    with open(JSON) as f:
        data = json.load(f)
    today = datetime.now().strftime('%Y-%m-%d')
    return [r for r in data if r.get('reservation_date') == today]

def load_crossref():
    """Load existing payment cross-reference."""
    crossref_file = REX_DIR / "bbg_payments_crossref.csv"
    if not crossref_file.exists():
        return {}
    crossref = {}
    with open(crossref_file) as f:
        reader = csv.DictReader(f)
        for row in reader:
            name = row['Name'].strip()
            crossref[name] = {
                'status': row.get('Status', ''),
                'amount': float(row.get('Payment', '0').replace('$', '').replace(',', '') or '0'),
                'stripe_id': row.get('Stripe ID', ''),
                'email': row.get('Payment Email', ''),
            }
    return crossref

def match_payment_to_reservation(payment, reservations):
    """Match a Stripe payment to a reservation by email or name."""
    email = payment['email'].lower()

    for r in reservations:
        r_name = r.get('party_name', '').lower()
        r_email = (r.get('email', '') or '').lower()

        # Direct email match
        if r_email and email and r_email == email:
            return r

        # Email domain match (e.g., gmail.com)
        if r_email and email:
            r_domain = r_email.split('@')[-1] if '@' in r_email else ''
            p_domain = email.split('@')[-1] if '@' in email else ''
            if r_domain and p_domain and r_domain == p_domain:
                r_local = r_email.split('@')[0]
                p_local = email.split('@')[0]
                if r_local[:3] == p_local[:3]:  # Fuzzy local part match
                    return r

    return None

def update_db(payments, reservations):
    """Update reservations DB with payment data."""
    conn = sqlite3.connect(str(DB))
    matched = 0

    for p in payments:
        # Try to find matching reservation
        matched_res = None
        for r in reservations:
            r_email = (r.get('email', '') or '').lower()
            if r_email and r_email == p['email'].lower():
                matched_res = r
                break

        if matched_res:
            matched += 1
            name = matched_res['party_name']
            # Update payment columns
            conn.execute('''
                UPDATE reservations
                SET payment_status = 'paid',
                    stripe_payment_id = ?,
                    amount_paid = ?,
                    paid_at = ?
                WHERE party_name = ? AND reservation_date = ?
            ''', (p['pi_id'], p['amount'], p['date'] or datetime.now().isoformat(), name, matched_res['reservation_date']))

    conn.commit()
    conn.close()
    return matched

def generate_report(payments, reservations, crossref):
    """Generate consolidated payment report."""
    # Build lookup from payments by email
    pay_by_email = {}
    for p in payments:
        email = p['email'].lower()
        if email:
            pay_by_email[email] = p

    report = []
    seen = set()

    for r in reservations:
        name = r.get('party_name', '')
        time = r.get('reservation_time', '')
        size = r.get('party_size', 0)
        phone = r.get('phone', '')
        email = (r.get('email', '') or '').lower()
        notes = r.get('notes', '')
        cash = r.get('deposit_cash')
        cash_ppl = r.get('deposit_persons')

        key = f"{name}|{time}|{size}"
        if key in seen: continue
        seen.add(key)

        # Check for payment
        payment = None
        if email:
            payment = pay_by_email.get(email)

        # Also check crossref
        cr = crossref.get(name, {})

        payment_status = 'UNPAID'
        amount_paid = 0.0
        stripe_id = ''
        paid_email = ''

        if payment:
            payment_status = 'PAID'
            amount_paid = payment['amount']
            stripe_id = payment['pi_id']
            paid_email = payment['email']
        elif cr.get('status') == 'PAID':
            payment_status = 'PAID'
            amount_paid = cr['amount']
            stripe_id = cr['stripe_id']
            paid_email = cr.get('email', '')
        elif cash:
            payment_status = 'CASH'
            amount_paid = cash
            paid_for_cash = cash_ppl or 0
        else:
            paid_for_cash = 0

        expected = size * DEPOSIT_PER_PERSON
        if payment_status in ('PAID', 'CASH'):
            still_owed = max(0, expected - amount_paid)
            paid_for = int(amount_paid / DEPOSIT_PER_PERSON) if DEPOSIT_PER_PERSON else 0
            if cash:
                paid_for = cash_ppl or 0
        else:
            still_owed = expected
            paid_for = 0

        report.append({
            'name': name, 'phone': phone,
            'email': paid_email or email or r.get('email', ''),
            'time': time, 'size': size,
            'payment': payment_status,
            'amount_paid': amount_paid,
            'expected': expected,
            'still_owed': still_owed,
            'paid_for': paid_for,
            'stripe_id': stripe_id,
            'notes': notes,
        })

    report.sort(key=lambda x: x['time'] or '99:99')
    return report

def print_report(report):
    """Print report to stdout."""
    paid = [r for r in report if r['payment'] in ('PAID', 'CASH')]
    unpaid = [r for r in report if r['payment'] not in ('PAID', 'CASH')]

    print(f"\n{'='*90}")
    print(f"  🏖️  BBG PAYMENT REPORT — {datetime.now().strftime('%B %d, %Y %I:%M %p')}")
    print(f"  💵 ${DEPOSIT_PER_PERSON}/person deposit")
    print(f"{'='*90}")
    print(f"  {len(report)} reservations | ✅ {len(paid)} PAID (${sum(r['amount_paid'] for r in paid):,.0f}) | ❌ {len(unpaid)} UNPAID (${sum(r['still_owed'] for r in unpaid):,.0f} owed)")
    print(f"{'='*90}")

    # PAID section
    print(f"\n✅ PAID (${sum(r['amount_paid'] for r in paid):,.0f} collected):")
    for r in paid:
        print(f"  {r['name']:<22} ${r['amount_paid']:>7,.0f} | {r['email']:<35} | {r['paid_for']}/{r['size']}p | {r['phone']}")

    # UNPAID with phone
    unpaid_phone = [r for r in unpaid if r['phone'] and '****' not in r['phone']]
    if unpaid_phone:
        print(f"\n📞 UNPAID — STAFF CAN CALL:")
        for r in unpaid_phone:
            print(f"  {r['name']:<22} ${r['still_owed']:>6,.0f} | {r['phone']:<20} | {r['size']}p | {r['time']}")

    # NO CONTACT
    no_contact = [r for r in unpaid if not r['phone'] and not r['email']]
    if no_contact:
        print(f"\n🚫 NO CONTACT ({len(no_contact)}):")
        for r in no_contact:
            print(f"  {r['name']:<25} {r['size']}p  {r['time']}")

    print(f"\n{'='*90}")

def main():
    import argparse
    parser = argparse.ArgumentParser(description='Stripe Dashboard Bridge for BBG')
    parser.add_argument('--report', action='store_true', help='Print report only (no scrape)')
    parser.add_argument('--csv', action='store_true', help='Save CSV report')
    parser.add_argument('--scrape', action='store_true', help='Force fresh scrape')
    args = parser.parse_args()

    reservations = load_reservations()
    crossref = load_crossref()

    if args.report:
        payments = []  # Use existing data
    elif args.scrape:
        print("Scraping Stripe dashboard...")
        payments = scrape_stripe()
        print(f"Found {len(payments)} payments")
    else:
        # Try to scrape
        print("Scraping Stripe dashboard via Chrome...")
        try:
            payments = scrape_stripe()
            print(f"Found {len(payments)} payments from Stripe")
        except Exception as e:
            print(f"Scrape failed: {e}")
            print("Using cached crossref data only")
            payments = []

    report = generate_report(payments, reservations, crossref)
    print_report(report)

    # Save CSV
    if args.csv or not args.report:
        OUT.mkdir(exist_ok=True)
        csv_path = OUT / f"bbg_payment_report_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"
        with open(csv_path, 'w', newline='') as f:
            w = csv.writer(f)
            w.writerow(['Name', 'Phone', 'Email', 'Time', 'Size', 'Status',
                        'Amount Paid', 'Still Owed', 'Deposits', 'Stripe ID', 'Notes'])
            for r in report:
                w.writerow([r['name'], r['phone'], r['email'], r['time'], r['size'],
                           r['payment'], f"${r['amount_paid']:.0f}", f"${r['still_owed']:.0f}",
                           f"{r['paid_for']}/{r['size']}", r['stripe_id'], r['notes']])
        print(f"\n📄 CSV: {csv_path}")

        # Also save JSON
        json_path = OUT / f"bbg_payments_{datetime.now().strftime('%Y%m%d_%H%M')}.json"
        with open(json_path, 'w') as f:
            json.dump(report, f, indent=2, default=str)
        print(f"📄 JSON: {json_path}")

if __name__ == '__main__':
    main()
