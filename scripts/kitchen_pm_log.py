#!/usr/bin/env python3
"""Morning +/- log for kitchen staff (Kato 2026-07-28): adds/removes vs yesterday's
printed sheets + dish quantity deltas for today. Emails Kato a kitchen-ready summary.

REBUILT 2026-08-03 from Blue #191 recovered strings + verified email format
(+166/-0 (S1=72 S2=94)) — original deleted in the 05:01 scripts/ wipe.
"""
import json
import smtplib
import sqlite3
from datetime import date, timedelta
from collections import Counter
from email.mime.text import MIMEText

AUTH = '/Users/mainsobhelper/Documents/goj files/dashboard/auth_tracker.db'
PROP = '/Users/mainsobhelper/Documents/goj files/proprietary/goj_proprietary.db'
SNAPSHOT = '/Users/mainsobhelper/Desktop/REX/output/roster_snapshot.json'
DAYCOLS = {
    0: 'day_M_actual', 1: 'day_T_actual', 2: 'day_W_actual',
    3: 'day_TH_actual', 4: 'day_F_actual', 6: 'day_Su_actual',
}

TODAY = date.today().isoformat()
wd = date.fromisoformat(TODAY).weekday()
col = DAYCOLS.get(wd)


def main():
    if col is None:
        print(f'{TODAY}: weekend (weekday {wd}), no attendance column — skipped')
        return

    a = sqlite3.connect(f'file:{AUTH}?mode=ro', uri=True)
    rows = a.execute(f'SELECT name, day_M_actual, day_T_actual, day_W_actual, day_TH_actual, day_F_actual, day_Su_actual FROM clients WHERE active=1 AND {col} IN (1,2)').fetchall()
    a.close()
    names = [r[0] for r in rows]
    # shift for today is the value of today's column (index: Mon=1..Fri=5, Sun=6)
    shift_idx = wd + 1  # Mon..Fri → 1..5; Sun(6) → 7 which is out of range, handled below
    if wd == 6:
        shift_idx = 6
    s1 = sum(1 for r in rows if r[shift_idx] == 1)
    s2 = sum(1 for r in rows if r[shift_idx] == 2)

    # compare vs last printed snapshot
    try:
        prev = json.load(open(SNAPSHOT))
        prev_names = set(prev.get('names', []))
    except Exception:
        prev_names = set()
    cur_names = set(names)
    added = sorted(cur_names - prev_names)
    removed = sorted(prev_names - cur_names)

    # dish quantity deltas for today
    p = sqlite3.connect(f'file:{PROP}?mode=ro', uri=True)
    today_counter = Counter()
    for shift in ('1', '2'):
        for salad, soup, main, side in p.execute('SELECT salad, soup, main, side FROM client_menus WHERE menu_date=? AND shift=?', (TODAY, shift)):
            for dish in (salad, soup, main, side):
                if dish and str(dish).strip():
                    today_counter[str(dish).strip()] += 1
    p.close()

    lines = []
    lines.append(f'KITCHEN +/- LOG — {TODAY}')
    lines.append(f'HEAD COUNT: S1={s1} S2={s2} (total {len(names)})')
    lines.append(f'+ ADDED ({len(added)}): {", ".join(added) if added else "none"}')
    lines.append(f'- REMOVED ({len(removed)}): {", ".join(removed) if removed else "none"}')
    lines.append('QUANTITIES:')
    for dish, n in today_counter.most_common():
        lines.append(f'  {dish}: {n} x')

    body = '\n'.join(lines)

    # save snapshot for tomorrow's comparison
    import os
    os.makedirs(os.path.dirname(SNAPSHOT), exist_ok=True)
    json.dump({'date': TODAY, 'names': sorted(names)}, open(SNAPSHOT, 'w'))

    # email Kato
    try:
        creds = json.load(open('/Users/mainsobhelper/.rex_gmail_imap.json'))
        msg = MIMEText(body)
        msg['From'] = creds['email']
        msg['To'] = creds['email']
        msg['Subject'] = f'GOJ Kitchen +/- {TODAY} — +{len(added)}/-{len(removed)} (S1={s1} S2={s2})'
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as s:
            s.login(creds['email'], creds['app_password'])
            s.send_message(msg)
        print(f'emailed: {msg["Subject"]}')
    except Exception as e:
        print(f'email failed: {e}')
    print(body)


if __name__ == '__main__':
    main()
