#!/usr/bin/env python3
"""
Supervised email-PDF OCR run.
Fetches every PDF attachment in Gmail since a cutoff date (default: this Monday),
drops them into the OCR scans/ folder, runs the (fixed) CC_ocr_pipeline on each,
and reports what staged / went to the review queue.

SUPERVISED: defaults to OCR_AUTO_FLOOR=2.0 → NOTHING auto-promotes to attendance_log;
every extracted row lands in the review queue for human approval. Raise confidence
trust later by lowering OCR_AUTO_FLOOR (0.85 is the normal auto-promote floor).

Creds are read from ~/.hermes-cloud/.env (EMAIL_ADDRESS + EMAIL_PASSWORD = a Gmail
App Password). Never hardcoded.

Usage:
  OCR_AUTO_FLOOR=2.0 python3 CC_supervised_email_ocr.py [--since 29-Jun-2026]
"""
import os, sys, imaplib, email, re
from pathlib import Path
from datetime import date, timedelta

REX = Path(__file__).resolve().parent
SCANS = Path.home() / "Documents" / "goj files" / "scans"
ENV = Path.home() / ".hermes-cloud" / ".env"
os.environ.setdefault("OCR_AUTO_FLOOR", "2.0")  # supervised default: review everything


def _env(name):
    if os.environ.get(name):
        return os.environ[name]
    if ENV.exists():
        for l in ENV.read_text().splitlines():
            if l.strip().startswith(name + "="):
                return l.split("=", 1)[1].strip().strip('"').strip("'")
    return None


def _monday_imap():
    t = date.today()
    mon = t - timedelta(days=t.weekday())
    return mon.strftime("%d-%b-%Y")


def fetch_pdfs(since):
    addr, pw = _env("EMAIL_ADDRESS"), _env("EMAIL_PASSWORD")
    if not (addr and pw):
        sys.exit("No EMAIL_ADDRESS/EMAIL_PASSWORD in ~/.hermes-cloud/.env")
    M = imaplib.IMAP4_SSL("imap.gmail.com", 993)
    try:
        M.login(addr, pw)
    except imaplib.IMAP4.error as e:
        sys.exit(f"IMAP login failed ({e}). Generate a fresh Gmail App Password and set EMAIL_PASSWORD.")
    M.select("INBOX")
    SCANS.mkdir(parents=True, exist_ok=True)
    # Gmail raw search: PDF attachments only since the cutoff — far fewer fetches than SINCE-all.
    try:
        import datetime as _dt
        gd = _dt.datetime.strptime(since, "%d-%b-%Y").strftime("%Y/%m/%d")
        _, data = M.search(None, 'X-GM-RAW', f'has:attachment filename:pdf after:{gd}')
    except Exception:
        _, data = M.search(None, f'(SINCE {since})')
    saved = []
    for mid in data[0].split():
        _, md = M.fetch(mid, "(RFC822)")
        msg = email.message_from_bytes(md[0][1])
        for part in msg.walk():
            fn = part.get_filename()
            if fn and fn.lower().endswith(".pdf"):
                safe = re.sub(r"[^A-Za-z0-9._-]", "_", fn)
                dest = SCANS / f"email_{mid.decode()}_{safe}"
                dest.write_bytes(part.get_payload(decode=True))
                saved.append(dest)
    M.logout()
    return saved


def main():
    since = _monday_imap()
    if "--since" in sys.argv:
        since = sys.argv[sys.argv.index("--since") + 1]
    print(f"Fetching Gmail PDF attachments since {since} (supervised, OCR_AUTO_FLOOR={os.environ['OCR_AUTO_FLOOR']})")
    pdfs = fetch_pdfs(since)
    print(f"  downloaded {len(pdfs)} PDF(s) → {SCANS}")
    if not pdfs:
        print("  nothing to process."); return
    sys.path.insert(0, str(REX))
    import CC_ocr_pipeline as ocr
    totals = {"staged": 0, "review_queued": 0, "auto_promoted": 0, "menu_rows": 0}
    for p in pdfs:
        r = ocr.process_file(str(p))
        db = ocr.write_to_db(r) if r.get("type") not in (None, "template") and "error" not in r else {}
        print(f"  {p.name}: type={r.get('type')} staged={db.get('staged',0)} "
              f"review_queued={db.get('review_queued',0)} menu_rows={db.get('menu_rows',0)}")
        for k in totals:
            totals[k] += db.get(k, 0) or 0
    print(f"\nSUPERVISED RESULT: {totals}")
    print("Review + approve at: https://hub.hermestigerclaw.com  (OCR review queue). "
          "Nothing entered attendance_log automatically.")


if __name__ == "__main__":
    main()
