#!/usr/bin/env python3
"""
CC_chairman_notify.py — text Kato a call-run summary at +1-347-587-9913.

GOJ (Victoria) is DE-IDENTIFIED: counts only, no client names — safe over SMS.
Dry-run by default (prints). Use --send to actually text. Optional date arg YYYY-MM-DD.

Sends from the GHS Twilio number via the Messages API (creds from ~/.hermes/.env).
"""
import os, sys, json, base64, sqlite3, urllib.request, urllib.parse, datetime
from pathlib import Path

KATO = "+13475879913"
PROP = Path.home() / "Documents" / "goj files" / "proprietary" / "goj_proprietary.db"


def henv(key: str) -> str:
    v = os.environ.get(key, "")
    if v:
        return v
    for p in (Path.home() / ".hermes/.env", Path.home() / ".hermes-cloud/.env"):
        if p.exists():
            for line in p.read_text().splitlines():
                s = line.strip()
                if s.startswith(key + "="):
                    return s.split("=", 1)[1].strip().strip('"')
    return ""


def goj_summary(date: str) -> str:
    # Outcome lives in att_status (confirmed/declined/no_answer/requested_staff/
    # voice_answered); `status` is just the call lifecycle (ended/not_connected).
    conn = sqlite3.connect(str(PROP))
    d = dict(conn.execute(
        "SELECT att_status, COUNT(*) FROM victoria_calls WHERE call_date=? GROUP BY att_status",
        (date,),
    ).fetchall())
    total = conn.execute(
        "SELECT COUNT(*) FROM victoria_calls WHERE call_date=?", (date,)).fetchone()[0]
    answered = conn.execute(
        "SELECT COUNT(*) FROM victoria_calls WHERE call_date=? AND picked_up='yes'",
        (date,)).fetchone()[0]
    conn.close()
    if total == 0:
        return f"GOJ Victoria — {date}: no calls recorded."
    return (
        f"GOJ Victoria — {date}: {total} calls, {answered} answered | "
        f"{d.get('confirmed', 0)} confirmed, {d.get('declined', 0)} declined, "
        f"{d.get('no_answer', 0)} no-answer, {d.get('requested_staff', 0)} staff. (de-identified)"
    )


def send_sms(to: str, body: str) -> dict:
    sid, tok = henv("TWILIO_ACCOUNT_SID"), henv("TWILIO_AUTH_TOKEN")
    frm = henv("TWILIO_NUMBER") or "+18777682887"
    if not (sid and tok):
        return {"error": "twilio creds missing in ~/.hermes/.env"}
    auth = base64.b64encode(f"{sid}:{tok}".encode()).decode()
    data = urllib.parse.urlencode({"To": to, "From": frm, "Body": body}).encode()
    r = urllib.request.Request(
        f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json",
        data=data, headers={"Authorization": f"Basic {auth}"},
    )
    return json.load(urllib.request.urlopen(r, timeout=20))


def main() -> int:
    send = "--send" in sys.argv
    date = datetime.date.today().isoformat()
    for a in sys.argv[1:]:
        if a.count("-") == 2 and not a.startswith("--"):
            date = a
    msg = goj_summary(date)
    print(msg)
    if send:
        res = send_sms(KATO, msg)
        print("[sms]", "sent ✅" if res.get("sid") else res)
        return 0 if res.get("sid") else 2
    print("[dry-run] not sent. Add --send to text Kato at", KATO)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
