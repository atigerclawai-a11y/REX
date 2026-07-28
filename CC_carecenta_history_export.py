#!/usr/bin/env python3
"""
CC_carecenta_history_export.py — OBJ-023: Carecenta full history export
=========================================================================
Exports ALL historical attendance + billing data for every GOJ client from
goj.daycenta.com BEFORE Carecenta cancellation (Sept 2026).

Carecenta has NO API — this drives Kato's Chrome via chrome-cli.

PAGE STRUCTURE (discovered 2026-07-27, pilot on client 206578):
  Login page      : https://goj.daycenta.com/  (NOT /login.aspx — that 404s)
  Logout URL      : /Default.aspx?p=mp&lo=1   (kills poisoned sessions)
  Client hub      : /Client.aspx?ID={cid}     (DOB, phone, address, auths)
  Authorizations  : /Client_Billing.aspx?ID={cid}&S=billing
  Open balances   : /ClientBillingPayments.aspx?ID={cid}&S=billing&Show=Balances
  REPORTS (bulk)  : /Reports.aspx?Rep=1203    Client Attendance (DateFrom/To, RUN)
                    /Reports.aspx?Rep=1180    Invoices by Dates of Service
  Report fields   : #fDateFrom #fDateTo, RUN = input[type=submit][value=RUN]
  Report results  : biggest <table>, header row contains 'ClientID'.
                    Renders take 15-25s for a month; poll until stable.
  Attendance cols : #, Client, ClientID, Payer, Route, Date, Scheduled,
                    CheckIn, Pickup, Arrival, Departure, DropOff, Location
  Billing cols    : #, Client Name, ClientID, Provider, InsuranceID, InvDate,
                    InvoiceID, DOS, BillCode, Units, Billed, Allowed, Paid,
                    Adjusted, PayStatus, Branch Location, Notes

DATA BOUNDARIES (probed 2026-07-27):
  Billing  : starts Dec 2025 (49 rows), full from Jan 2026
  Attendance: starts Jan 2026 (48 rows, sparse), full from Feb-Mar 2026
  Nothing before 2025-12 in either report (verified 2022/2023/2024 = empty).

LOGIN (HARD RULE): password FIRST (#password), then ID (#login), then click
#ctl00_Content_btnLogin. ID-first triggers Stripe hCaptcha redirect.
Creds: ~/.hermes/profiles/work/secrets/carecenta.json (user allen.khiger).

chrome-cli PITFALL (battle-tested 2026-07-27): JS return values that are
numbers/booleans CRASH chrome-cli (NSInvalidArgumentException __NSCFNumber
UTF8String). EVERY execute must return String(...) or JSON.stringify(...).

MODES:
  --discover CID   Dump link map + table shapes (debugging)
  --pilot          1 small report chunk + 3 clients, verbose, then load DB
  --full           Everything: all report chunks + all clients, resumable
  --reports        Phase A only (bulk reports)
  --clients        Phase B only (per-client pages)
  --load-db        Rebuild SQLite from existing JSONL
  --summary        Counts + date ranges

WINDOW GUARDS: pause 13:45-14:30 and 18:45-20:30 (crons drive Chrome), and
Sun 17:55-18:45 (weekly refresh). Refuses to start if the weekly-refresh
checkpoint is <40 min old.

OUTPUT (local only — PHI never leaves the machine):
  ~/Desktop/REX/carecenta_history/history.jsonl        typed records, checkpoint
  ~/Desktop/REX/carecenta_history/carecenta_history.db SQLite
  ~/Desktop/REX/carecenta_history/run.log
  (carecenta_history/ excluded from rex_code_backup.sh — verified 2026-07-27)
"""

import argparse
import json
import re
import sqlite3
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

OUT_DIR = Path.home() / "Desktop" / "REX" / "carecenta_history"
JSONL = OUT_DIR / "history.jsonl"
DB = OUT_DIR / "carecenta_history.db"
RUNLOG = OUT_DIR / "run.log"
SCHED_DB = Path.home() / "Desktop" / "REX" / "signin_lists" / "ghs_schedule.db"
IDS_CACHE = Path("/tmp/carecenta_all_ids.json")
REFRESH_CP = Path("/tmp/carecenta_refresh_checkpoint.json")
CREDS = Path.home() / ".hermes/profiles/work/secrets/carecenta.json"

BASE = "https://goj.daycenta.com"
REPORTS = {"attendance": 1203, "billing": 1180}
REPORT_START = {"attendance": (2026, 1), "billing": (2025, 12)}  # probed

CLIENT_PAGES = [
    ("hub", "/Client.aspx?ID={cid}"),
    ("auth", "/Client_Billing.aspx?ID={cid}&S=billing"),
    ("balances", "/ClientBillingPayments.aspx?ID={cid}&S=billing&Show=Balances"),
]

PAGE_TIMEOUT = 12
NAV_WAIT = 2.2
MAX_RELOGINS = 5
BLOCKED_WINDOWS = [((13, 45), (14, 30)), ((18, 45), (20, 30))]
RELOGINS = 0


def log(msg):
    line = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(line, flush=True)
    try:
        with RUNLOG.open("a") as f:
            f.write(line + "\n")
    except Exception:
        pass


# ── chrome helpers ───────────────────────────────────────────────────────────
def chrome_exec(js, timeout=PAGE_TIMEOUT):
    r = subprocess.run(["chrome-cli", "execute", js],
                       capture_output=True, text=True, timeout=timeout)
    return r.stdout.strip()


def chrome_info():
    try:
        r = subprocess.run(["chrome-cli", "info"],
                           capture_output=True, text=True, timeout=8)
        return r.stdout
    except Exception:
        return ""


def current_url():
    for line in chrome_info().splitlines():
        if line.startswith("Url:"):
            return line[4:].strip()
    return ""


def wait_loaded(max_s=12):
    deadline = time.time() + max_s
    while time.time() < deadline:
        if "Loading: No" in chrome_info():
            try:
                if chrome_exec("document.readyState", timeout=5) == "complete":
                    return True
            except Exception:
                pass
        time.sleep(0.4)
    return False


def chrome_nav(url, wait=NAV_WAIT):
    wait_loaded(max_s=8)
    try:
        chrome_exec(f'window.location.href = "{url}"; ""')
    except Exception as e:
        log(f"  nav warn: {e}")
    time.sleep(wait)
    wait_loaded(max_s=10)


# ── session state ────────────────────────────────────────────────────────────
LOGIN_FORM_JS = "String(!!document.querySelector(\"input[name='txtLogin']\"))"
BLANK_CHECK_JS = "String(document.documentElement.outerHTML.length)"


def page_is_blank():
    try:
        return int(chrome_exec(BLANK_CHECK_JS, timeout=5) or 0) < 100
    except Exception:
        return False


def on_login_page():
    try:
        return chrome_exec(LOGIN_FORM_JS, timeout=5) == "true"
    except Exception:
        return False


def page_state(max_s=10):
    """Stable state: healthy | login | blank. State must persist across polls
    (a mid-load blank is transient — fixes the 2026-07-27 false-poison loop)."""
    deadline = time.time() + max_s
    last, stable = None, 0
    while time.time() < deadline:
        if on_login_page():
            state = "login"
        elif page_is_blank():
            state = "blank"
        else:
            state = "healthy"
        if state == last:
            stable += 1
            need = 1 if state in ("healthy", "login") else 3
            if stable >= need:
                return state
        else:
            stable = 0
        last = state
        time.sleep(1.0)
    return last or "blank"


def do_login():
    """Password-first login (hCaptcha bypass)."""
    creds = json.loads(CREDS.read_text())
    user, pw = creds["email"], creds["password"]
    esc_pw = pw.replace("\\", "\\\\").replace('"', '\\"')
    chrome_exec(f"""
var p = document.getElementById('password') ||
        document.querySelector("input[name='Password']");
if (p) {{ p.focus(); p.value = "{esc_pw}";
  p.dispatchEvent(new Event('input', {{bubbles:true}}));
  p.dispatchEvent(new Event('change', {{bubbles:true}})); }}
"pw_done";""", timeout=8)
    time.sleep(0.8)
    chrome_exec(f"""
var u = document.getElementById('login') ||
        document.querySelector("input[name='txtLogin']");
if (u) {{ u.focus(); u.value = "{user}";
  u.dispatchEvent(new Event('input', {{bubbles:true}}));
  u.dispatchEvent(new Event('change', {{bubbles:true}})); }}
"user_done";""", timeout=8)
    time.sleep(0.8)
    chrome_exec("var b=document.getElementById('ctl00_Content_btnLogin');"
                "if(b) b.click(); 'clicked'", timeout=8)
    time.sleep(4)
    deadline = time.time() + 25
    while time.time() < deadline:
        wait_loaded(max_s=4)
        if page_state(max_s=3) == "healthy":
            return
        time.sleep(1.5)


def ensure_logged_in():
    global RELOGINS
    state = page_state()
    if state == "healthy":
        return True
    if RELOGINS >= MAX_RELOGINS:
        raise RuntimeError("too many re-logins — aborting")
    RELOGINS += 1
    if state == "blank":
        log(f"session POISONED (confirmed) — logout + re-login #{RELOGINS}")
        chrome_nav(BASE + "/Default.aspx?p=mp&lo=1", wait=4)
    else:
        log(f"session expired — re-login #{RELOGINS} (password FIRST)")
    if page_state(max_s=6) != "login":
        chrome_nav(BASE + "/", wait=4)
    do_login()
    if page_state(max_s=8) != "healthy":
        raise RuntimeError("re-login FAILED")
    log(f"re-login OK -> {current_url()}")
    return True


# ── window guards ────────────────────────────────────────────────────────────
def in_blocked_window():
    now = datetime.now()
    hm = (now.hour, now.minute)
    for (sh, sm), (eh, em) in BLOCKED_WINDOWS:
        if (sh, sm) <= hm <= (eh, em):
            return True, f"{sh:02d}:{sm:02d}-{eh:02d}:{em:02d}"
    if now.weekday() == 6 and (17, 55) <= hm <= (18, 45):
        return True, "Sun 17:55-18:45 (weekly refresh)"
    return False, ""


def respect_windows():
    while True:
        blocked, label = in_blocked_window()
        if not blocked:
            return
        log(f"blocked window {label} — pausing 5 min")
        time.sleep(300)


def check_refresh_not_running():
    if REFRESH_CP.exists():
        age_m = (time.time() - REFRESH_CP.stat().st_mtime) / 60
        if age_m < 40:
            raise RuntimeError(
                f"weekly refresh checkpoint {age_m:.0f} min old — may be "
                "running. Wait and retry.")


# ── report engine (Phase A) ──────────────────────────────────────────────────
def month_chunks(start_y, start_m):
    """(d1, d2, key) monthly from start to current month, MM/DD/YYYY."""
    y, m = start_y, start_m
    now = datetime.now()
    while (y, m) <= (now.year, now.month):
        if m == 12:
            ny, nm = y + 1, 1
        else:
            ny, nm = y, m + 1
        last_day = datetime(ny, nm, 1) - __import__("datetime").timedelta(days=1)
        d2 = min(last_day, now)
        yield (f"{m:02d}/01/{y}", f"{d2.month:02d}/{d2.day:02d}/{d2.year}",
               f"{y}-{m:02d}")
        y, m = ny, nm


BEST_TABLE_JS = r"""
var ts=document.querySelectorAll('table'); var best=null;
for(var t=0;t<ts.length;t++){
  var rows=Array.from(ts[t].querySelectorAll('tr'))
    .filter(function(r){return r.closest('table')===ts[t];});
  if(rows.length>3&&(!best||rows.length>best.length)) best=rows;}
if(!best){ JSON.stringify({rows:[], n:0}); }
else {
  var out=[];
  for(var i=0;i<best.length;i++){
    var cells=Array.from(best[i].querySelectorAll('th,td'))
      .filter(function(c){return c.closest('tr')===best[i];});
    var c=[];
    for(var j=0;j<cells.length;j++)
      c.push(cells[j].innerText.replace(/\s+/g,' ').trim());
    out.push(c);
  }
  JSON.stringify({rows:out, n:out.length});
}
"""


def wait_report_render(max_s=120):
    """Poll until biggest-table row count + body length are stable twice."""
    last_sig, stable = None, 0
    deadline = time.time() + max_s
    while time.time() < deadline:
        time.sleep(4)
        try:
            sig_raw = chrome_exec(
                "String((function(){var ts=document.querySelectorAll('table');"
                "var best=0; for(var t=0;t<ts.length;t++){var rs=ts[t].querySelectorAll('tr');"
                " if(rs.length>best)best=rs.length;} return best+'|'+document.body.innerText.length;})())",
                timeout=10)
            sig = sig_raw
        except Exception:
            sig = None
        if sig and sig == last_sig:
            stable += 1
            if stable >= 2:
                return True
        else:
            stable = 0
        last_sig = sig
    return False


# ── regex fallback for Concatenated Carecenta report tables ──────────────────
# Carecenta's attendance/billing reports often render with merged cells that
# confuse the DOM table parser. The data IS present but all in one <td> as a
# text blob. This fallback splits the blob into rows using the known format.
#
# Row-start pattern: {idx} {LastName, FirstName} {6-digit ID}
# After that: {payer words...} [{single-letter route}] {MM/DD/YYYY} {HH:MM-HH:MM} {-- fields}
ROW_START_RE = re.compile(
    r"(\d+)\s+([A-Za-z'-]+,\s*[A-Za-z '-]+?)\s+(\d{5,6})\s+")


def _find_data_section(text):
    """Locate the start of actual data rows in Carecenta report text."""
    for marker in ("Location Name ", "DropOff Location ", "ClientID "):
        idx = text.find(marker)
        if idx >= 0:
            return text[idx + len(marker):]
    return text


def _fallback_parse_rows(data_text):
    """Split concatenated report text into rows, parse fields per row."""
    row_starts = list(ROW_START_RE.finditer(data_text))
    rows = []
    for i, m in enumerate(row_starts):
        start = m.end()
        end = row_starts[i + 1].start() if i + 1 < len(row_starts) else len(data_text)
        payload = data_text[start:end].strip()
        parts = payload.split()

        # Find the date (MM/DD/YYYY) — anchor point for field boundaries
        date_idx = None
        for j, p in enumerate(parts):
            if re.match(r"\d{2}/\d{2}/\d{4}", p):
                date_idx = j
                break
        if date_idx is None:
            continue

        # Route (if present) is a single uppercase letter just before the date
        route = ""
        payer_end = date_idx
        if date_idx > 0 and re.match(r"^[A-Z]$", parts[date_idx - 1]):
            route = parts[date_idx - 1]
            payer_end = date_idx - 1

        payer = " ".join(parts[:payer_end]).strip()
        date = parts[date_idx]
        remaining = parts[date_idx + 1:]

        # Scheduled time (HH:MM-HH:MM or HH:MM)
        sched = ""
        if remaining and re.match(r"\d{2}:\d{2}", remaining[0]):
            sched = remaining[0]
            remaining = remaining[1:]

        # Next 5 fields: checkin, pickup, arrival, departure, dropoff
        fields = remaining[:5]
        # Location may be multi-word
        location = " ".join(remaining[5:]) if len(remaining) > 5 else ""

        rows.append([
            m.group(1),                # idx
            m.group(2).strip(),        # client_name
            m.group(3),                # carecenta_id
            payer, route, date, sched,
            fields[0] if len(fields) > 0 else "",
            fields[1] if len(fields) > 1 else "",
            fields[2] if len(fields) > 2 else "",
            fields[3] if len(fields) > 3 else "",
            fields[4] if len(fields) > 4 else "",
            location,
        ])
    return rows


def run_report_chunk(rep_name, d1, d2):
    """Run one report for a date range; return list of data rows (arrays)."""
    rep_id = REPORTS[rep_name]
    chrome_nav(f"{BASE}/Reports.aspx?Rep={rep_id}", wait=3)
    if page_state() != "healthy":
        ensure_logged_in()
        chrome_nav(f"{BASE}/Reports.aspx?Rep={rep_id}", wait=3)
    out = chrome_exec(f"""
var d1=document.getElementById('fDateFrom'); d1.value='{d1}';
d1.dispatchEvent(new Event('change',{{bubbles:true}}));
var d2=document.getElementById('fDateTo'); d2.value='{d2}';
d2.dispatchEvent(new Event('change',{{bubbles:true}}));
var b=Array.from(document.querySelectorAll('input[type=submit]')).find(x=>x.value=='RUN');
if(b) b.click();
"run_clicked";""", timeout=10)
    if "run_clicked" not in out:
        raise RuntimeError("RUN button not found")
    wait_report_render()
    # Also grab full body text for regex fallback
    body_text = ""
    try:
        body_text = chrome_exec("document.body.innerText", timeout=10) or ""
    except Exception:
        pass
    raw = chrome_exec(BEST_TABLE_JS, timeout=30)
    data = json.loads(raw) if raw else {"rows": []}
    rows = data.get("rows", [])
    # locate header row (contains ClientID); data rows follow it
    hdr_idx = None
    for i, r in enumerate(rows[:5]):
        if any("ClientID" in c for c in r):
            hdr_idx = i
            break
    if hdr_idx is None:
        # Table parser failed — try regex fallback on body text
        data_section = _find_data_section(body_text)
        fallback = _fallback_parse_rows(data_section)
        if fallback:
            header = (ATT_KEYS[1:] if rep_name == "attendance"
                      else BILL_KEYS[1:])
            log(f"  {rep_name} {d1}-{d2}: table parser returned 0 rows, "
                f"regex fallback found {len(fallback)} rows")
            return header, fallback
        return [], []
    header = rows[hdr_idx]
    data_rows = [r for r in rows[hdr_idx + 1:]
                 if len(r) >= len(header) - 1 and any(c.strip() for c in r)]
    return header, data_rows


# ── per-client engine (Phase B) ──────────────────────────────────────────────
TABLES_JS = r"""
var tables = document.querySelectorAll("table");
var out = [];
for (var t=0; t<tables.length; t++) {
  var trs = Array.from(tables[t].querySelectorAll("tr"))
    .filter(function(r){return r.closest("table")===tables[t];});
  var rows = [];
  for (var r=0; r<trs.length; r++) {
    var tds = Array.from(trs[r].querySelectorAll("th,td"))
      .filter(function(c){return c.closest("tr")===trs[r];});
    var cells = [];
    for (var c=0; c<tds.length; c++)
      cells.push(tds[c].innerText.replace(/\s+/g," ").trim());
    if (cells.length) rows.push(cells);
  }
  if (rows.length > 1) out.push({index:t, rows:rows});
}
JSON.stringify(out);
"""


def get_tables():
    try:
        return json.loads(chrome_exec(TABLES_JS, timeout=15) or "[]")
    except Exception:
        return []


def scrape_client(cid, name):
    rec = {"type": "client", "carecenta_id": cid, "name": name,
           "scraped_at": datetime.now().isoformat(timespec="seconds"),
           "pages": {}, "errors": []}
    for label, tmpl in CLIENT_PAGES:
        url = BASE + tmpl.format(cid=cid)
        try:
            chrome_nav(url)
            if page_state() != "healthy":
                ensure_logged_in()
                chrome_nav(url)
            rec["pages"][label] = {
                "url": current_url(),
                "text": chrome_exec("document.body.innerText",
                                    timeout=PAGE_TIMEOUT)[:20000],
                "tables": get_tables(),
            }
        except subprocess.TimeoutExpired:
            rec["errors"].append(f"{label}: timeout — skipped")
        except Exception as e:
            rec["errors"].append(f"{label}: {str(e)[:120]}")
    return rec


# ── JSONL checkpoint ─────────────────────────────────────────────────────────
def load_done():
    done_chunks, done_clients = set(), set()
    if JSONL.exists():
        with JSONL.open() as f:
            for line in f:
                try:
                    rec = json.loads(line)
                except Exception:
                    continue
                if rec.get("type") == "report_chunk":
                    done_chunks.add((rec["report"], rec["chunk"]))
                elif rec.get("type") == "client":
                    done_clients.add(rec["carecenta_id"])
    return done_chunks, done_clients


def append_jsonl(rec):
    with JSONL.open("a") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


# ── Phase A runner ───────────────────────────────────────────────────────────
def run_reports():
    check_refresh_not_running()
    respect_windows()
    done_chunks, _ = load_done()
    chrome_nav(BASE + "/home.aspx", wait=3)
    if page_state() != "healthy":
        ensure_logged_in()
    for rep_name in ("attendance", "billing"):
        sy, sm = REPORT_START[rep_name]
        for d1, d2, key in month_chunks(sy, sm):
            if (rep_name, key) in done_chunks:
                log(f"  skip {rep_name} {key} (done)")
                continue
            respect_windows()
            t0 = time.time()
            try:
                header, rows = run_report_chunk(rep_name, d1, d2)
                append_jsonl({"type": "report_chunk", "report": rep_name,
                              "chunk": key, "d1": d1, "d2": d2,
                              "header": header, "rows": rows,
                              "scraped_at": datetime.now().isoformat(timespec="seconds")})
                log(f"  {rep_name} {key}: {len(rows)} rows "
                    f"({time.time()-t0:.0f}s)")
            except Exception as e:
                append_jsonl({"type": "report_chunk", "report": rep_name,
                              "chunk": key, "d1": d1, "d2": d2,
                              "header": [], "rows": [],
                              "error": str(e)[:200],
                              "scraped_at": datetime.now().isoformat(timespec="seconds")})
                log(f"  {rep_name} {key}: ERROR {e}")


# ── Phase B runner ───────────────────────────────────────────────────────────
def get_client_ids():
    ids = {}
    if SCHED_DB.exists():
        db = sqlite3.connect(str(SCHED_DB))
        for cid, last, first in db.execute(
                "SELECT carecenta_id, last_name, first_name FROM clients"):
            nm = f"{last}, {first}".strip(", ")
            ids[int(cid)] = re.sub(r"\s*\d{5,}\s*$", "", nm).strip()
        db.close()
    if IDS_CACHE.exists():
        try:
            for cid, nm in json.loads(IDS_CACHE.read_text()).items():
                cid = int(cid)
                if cid not in ids:
                    ids[cid] = re.sub(r"\s*\d{5,}\s*$", "", str(nm)).strip()
        except Exception:
            pass
    return dict(sorted(ids.items()))


def run_clients(limit=None):
    check_refresh_not_running()
    respect_windows()
    clients = get_client_ids()
    _, done_clients = load_done()
    todo = [(cid, nm) for cid, nm in clients.items() if cid not in done_clients]
    if limit:
        todo = todo[:limit]
    log(f"Phase B: {len(todo)} clients to scrape ({len(done_clients)} done)")
    if not todo:
        return
    chrome_nav(BASE + "/home.aspx", wait=3)
    if page_state() != "healthy":
        ensure_logged_in()
    t0 = time.time()
    for i, (cid, nm) in enumerate(todo, 1):
        global RELOGINS
        respect_windows()
        try:
            rec = scrape_client(cid, nm)
            if not rec["errors"]:
                RELOGINS = 0
        except Exception as e:
            rec = {"type": "client", "carecenta_id": cid, "name": nm,
                   "scraped_at": datetime.now().isoformat(timespec="seconds"),
                   "pages": {}, "errors": [f"fatal: {str(e)[:120]}"]}
        append_jsonl(rec)
        rate = (time.time() - t0) / i
        eta_m = rate * (len(todo) - i) / 60
        log(f"[{i}/{len(todo)}] {cid} {nm[:28]:30} pages={len(rec['pages'])}"
            f" err={len(rec['errors'])} | {rate:.1f}s ETA {eta_m:.0f}m")


# ── SQLite load (Phase C) ────────────────────────────────────────────────────
SCHEMA = """
CREATE TABLE IF NOT EXISTS clients (
    carecenta_id INTEGER PRIMARY KEY,
    name TEXT, dob TEXT, phone TEXT, address TEXT, coordinator TEXT,
    scraped_at TEXT, status TEXT DEFAULT 'ok', error TEXT
);
CREATE TABLE IF NOT EXISTS attendance (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    carecenta_id INTEGER, client_name TEXT, payer TEXT, route TEXT,
    visit_date TEXT, scheduled TEXT, checkin TEXT, pickup TEXT,
    arrival TEXT, departure TEXT, dropoff TEXT, location TEXT,
    chunk TEXT, scraped_at TEXT, deleted INTEGER DEFAULT 0,
    UNIQUE(carecenta_id, visit_date, scheduled)
);
CREATE TABLE IF NOT EXISTS billing (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    carecenta_id INTEGER, client_name TEXT, provider TEXT, insurance_id TEXT,
    inv_date TEXT, invoice_id TEXT, dos TEXT, bill_code TEXT, units TEXT,
    billed TEXT, allowed TEXT, paid TEXT, adjusted TEXT, pay_status TEXT,
    branch TEXT, notes TEXT, chunk TEXT, scraped_at TEXT,
    deleted INTEGER DEFAULT 0,
    UNIQUE(carecenta_id, invoice_id, dos, bill_code, units)
);
CREATE TABLE IF NOT EXISTS authorizations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    carecenta_id INTEGER, from_date TEXT, to_date TEXT, payer TEXT,
    service TEXT, bill_code TEXT, auth_number TEXT, contract_client_id TEXT,
    raw TEXT, scraped_at TEXT, deleted INTEGER DEFAULT 0,
    UNIQUE(carecenta_id, from_date, to_date, payer, service, auth_number)
);
CREATE TABLE IF NOT EXISTS open_invoices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    carecenta_id INTEGER, invoice_id TEXT, invoice_date TEXT, due_date TEXT,
    status TEXT, balance TEXT, scraped_at TEXT, deleted INTEGER DEFAULT 0,
    UNIQUE(carecenta_id, invoice_id)
);
CREATE TABLE IF NOT EXISTS open_ar_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    carecenta_id INTEGER, svc_date TEXT, payer_code TEXT, bill_code TEXT,
    rate TEXT, units TEXT, billed TEXT, paid TEXT, balance TEXT,
    scraped_at TEXT, deleted INTEGER DEFAULT 0,
    UNIQUE(carecenta_id, svc_date, bill_code, billed)
);
CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT DEFAULT (datetime('now')), action TEXT, detail TEXT
);
CREATE INDEX IF NOT EXISTS idx_att_client ON attendance(carecenta_id);
CREATE INDEX IF NOT EXISTS idx_att_date ON attendance(visit_date);
CREATE INDEX IF NOT EXISTS idx_bill_client ON billing(carecenta_id);
CREATE INDEX IF NOT EXISTS idx_bill_dos ON billing(dos);
CREATE INDEX IF NOT EXISTS idx_auth_client ON authorizations(carecenta_id);
"""

ATT_KEYS = ["idx", "client_name", "carecenta_id", "payer", "route",
            "visit_date", "scheduled", "checkin", "pickup", "arrival",
            "departure", "dropoff", "location"]
BILL_KEYS = ["idx", "client_name", "carecenta_id", "provider", "insurance_id",
             "inv_date", "invoice_id", "dos", "bill_code", "units", "billed",
             "allowed", "paid", "adjusted", "pay_status", "branch", "notes"]

AUTH_RE = re.compile(
    r"(\d{1,2}/\d{1,2}/\d{4})\s+(\d{1,2}/\d{1,2}/\d{4})\s+"
    r"([A-Z][A-Za-z ,.]+?)\s+(visit|transport)\s+([A-Z]\d{4})\b.*?"
    r"Auth #\s*(\d+)\s+Contract Client ID\s*([A-Z0-9]+)", re.S)


def _map_row(keys, row):
    out = {k: "" for k in keys}
    for i, k in enumerate(keys):
        if i < len(row):
            out[k] = row[i]
    return out


def load_db():
    db = sqlite3.connect(str(DB))
    db.executescript(SCHEMA)
    db.execute("INSERT INTO audit_log (action, detail) VALUES ('load_start', '')")
    for t in ("attendance", "billing", "authorizations", "open_invoices",
              "open_ar_items", "clients"):
        db.execute(f"DELETE FROM {t}")
    n_att = n_bill = n_auth = n_inv = n_ar = n_cli = 0

    with JSONL.open() as f:
        for line in f:
            try:
                rec = json.loads(line)
            except Exception:
                continue

            if rec.get("type") == "report_chunk" and rec.get("rows"):
                chunk = rec["chunk"]
                ts = rec.get("scraped_at", "")
                if rec["report"] == "attendance":
                    for row in rec["rows"]:
                        m = _map_row(ATT_KEYS, row)
                        if not m["visit_date"] or not m["carecenta_id"].isdigit():
                            continue  # skip form/help rows
                        db.execute(
                            """INSERT OR IGNORE INTO attendance
                            (carecenta_id, client_name, payer, route, visit_date,
                             scheduled, checkin, pickup, arrival, departure,
                             dropoff, location, chunk, scraped_at)
                            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                            (int(m["carecenta_id"]), m["client_name"], m["payer"],
                             m["route"], m["visit_date"], m["scheduled"],
                             m["checkin"], m["pickup"], m["arrival"],
                             m["departure"], m["dropoff"], m["location"],
                             chunk, ts))
                elif rec["report"] == "billing":
                    for row in rec["rows"]:
                        m = _map_row(BILL_KEYS, row)
                        if not m["dos"] or not m["carecenta_id"].isdigit():
                            continue
                        db.execute(
                            """INSERT OR IGNORE INTO billing
                            (carecenta_id, client_name, provider, insurance_id,
                             inv_date, invoice_id, dos, bill_code, units, billed,
                             allowed, paid, adjusted, pay_status, branch, notes,
                             chunk, scraped_at)
                            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                            (int(m["carecenta_id"]), m["client_name"], m["provider"],
                             m["insurance_id"], m["inv_date"], m["invoice_id"],
                             m["dos"], m["bill_code"], m["units"], m["billed"],
                             m["allowed"], m["paid"], m["adjusted"],
                             m["pay_status"], m["branch"], m["notes"], chunk, ts))

            elif rec.get("type") == "client":
                cid = rec["carecenta_id"]
                ts = rec.get("scraped_at", "")
                status = "ok" if not rec.get("errors") else "error"
                hub_text = rec.get("pages", {}).get("hub", {}).get("text", "")
                dob = phone = addr = coord = ""
                m = re.search(r"Date of Birth\s*\n?\s*(\d{1,2}/\d{1,2}/\d{4})", hub_text)
                if m: dob = m.group(1)
                m = re.search(r"Phone\s*\n?\s*(\+?1?\s*\(?\d{3}\)?[\d\s\-()]{7,})", hub_text)
                if m: phone = m.group(1).strip()
                m = re.search(r"Coordinator\s*\n?\s*([A-Za-z ,]+)", hub_text)
                if m: coord = m.group(1).strip()
                m = re.search(r"LOCATION.*?\n?([0-9]{2,5} [A-Za-z0-9 .]+?, [A-Za-z ]+, NY \d{5})", hub_text, re.S)
                if m: addr = re.sub(r"\s+", " ", m.group(1)).strip()
                db.execute(
                    "INSERT OR REPLACE INTO clients (carecenta_id, name, dob, phone,"
                    " address, coordinator, scraped_at, status, error)"
                    " VALUES (?,?,?,?,?,?,?,?,?)",
                    (cid, rec.get("name", ""), dob, phone, addr, coord, ts,
                     status, "; ".join(rec.get("errors", []))[:300]))
                n_cli += 1

                # authorizations from auth page text
                auth_text = rec.get("pages", {}).get("auth", {}).get("text", "")
                for am in AUTH_RE.finditer(auth_text):
                    db.execute(
                        """INSERT OR IGNORE INTO authorizations
                        (carecenta_id, from_date, to_date, payer, service,
                         bill_code, auth_number, contract_client_id, raw, scraped_at)
                        VALUES (?,?,?,?,?,?,?,?,?,?)""",
                        (cid, am.group(1), am.group(2), am.group(3).strip(),
                         am.group(4), am.group(5), am.group(6), am.group(7),
                         am.group(0)[:400], ts))

                # open invoices + AR items from balances page
                bal = rec.get("pages", {}).get("balances", {})
                bal_text = bal.get("text", "")
                for im in re.finditer(
                        r"INVOICE\s+(\d+)\s+INVOICE DATE\s+(\d{2}/\d{2}/\d{4})\s+"
                        r"DUE DATE\s*(?:(\d{2}/\d{2}/\d{4})\s+)?STATUS\s+(\w+(?:\s\w+)?)\s+"
                        r"OPEN BALANCE\s+(\$[\d,.]+)", bal_text):
                    db.execute(
                        """INSERT OR IGNORE INTO open_invoices
                        (carecenta_id, invoice_id, invoice_date, due_date,
                         status, balance, scraped_at) VALUES (?,?,?,?,?,?,?)""",
                        (cid, im.group(1), im.group(2), im.group(3) or "",
                         im.group(4).strip(), im.group(5), ts))
                for tb in bal.get("tables", []):
                    rows = tb.get("rows", [])
                    for row in rows:
                        if (len(row) >= 10 and row[1]
                                and re.match(r"\d{2}/\d{2}/\d{4}$", row[1])
                                and row[3].startswith(("S", "A", "T"))):
                            db.execute(
                                """INSERT OR IGNORE INTO open_ar_items
                                (carecenta_id, svc_date, payer_code, bill_code,
                                 rate, units, billed, paid, balance, scraped_at)
                                VALUES (?,?,?,?,?,?,?,?,?,?)""",
                                (cid, row[1], row[2], row[3], row[5], row[6],
                                 row[7], row[8], row[9], ts))

    for t, var in (("attendance", "n_att"), ("billing", "n_bill"),
                   ("authorizations", "n_auth"), ("open_invoices", "n_inv"),
                   ("open_ar_items", "n_ar")):
        db.execute(f"SELECT COUNT(*) FROM {t}")
    n_att = db.execute("SELECT COUNT(*) FROM attendance").fetchone()[0]
    n_bill = db.execute("SELECT COUNT(*) FROM billing").fetchone()[0]
    n_auth = db.execute("SELECT COUNT(*) FROM authorizations").fetchone()[0]
    n_inv = db.execute("SELECT COUNT(*) FROM open_invoices").fetchone()[0]
    n_ar = db.execute("SELECT COUNT(*) FROM open_ar_items").fetchone()[0]
    db.execute("INSERT INTO audit_log (action, detail) VALUES (?, ?)",
               ("load_done", f"clients={n_cli} att={n_att} bill={n_bill} "
                             f"auth={n_auth} inv={n_inv} ar={n_ar}"))
    db.commit()
    db.close()
    log(f"DB loaded: clients={n_cli} attendance={n_att} billing={n_bill} "
        f"auths={n_auth} open_inv={n_inv} ar_items={n_ar}")


def summary():
    if not DB.exists():
        print("no DB yet")
        return
    db = sqlite3.connect(str(DB))
    print("=== carecenta_history.db summary ===")
    c = db.execute("SELECT COUNT(*) FROM clients").fetchone()[0]
    ce = db.execute("SELECT COUNT(*) FROM clients WHERE status='error'").fetchone()[0]
    a = db.execute("SELECT COUNT(*) FROM attendance WHERE deleted=0").fetchone()[0]
    ac = db.execute("SELECT COUNT(DISTINCT carecenta_id) FROM attendance").fetchone()[0]
    adr = db.execute("SELECT MIN(visit_date), MAX(visit_date) FROM attendance").fetchone()
    ci = db.execute("SELECT COUNT(*) FROM attendance WHERE checkin NOT IN ('','--')").fetchone()[0]
    b = db.execute("SELECT COUNT(*) FROM billing WHERE deleted=0").fetchone()[0]
    bc = db.execute("SELECT COUNT(DISTINCT carecenta_id) FROM billing").fetchone()[0]
    bdr = db.execute("SELECT MIN(dos), MAX(dos) FROM billing").fetchone()
    au = db.execute("SELECT COUNT(*) FROM authorizations").fetchone()[0]
    auc = db.execute("SELECT COUNT(DISTINCT carecenta_id) FROM authorizations").fetchone()[0]
    inv = db.execute("SELECT COUNT(*) FROM open_invoices").fetchone()[0]
    ar = db.execute("SELECT COUNT(*) FROM open_ar_items").fetchone()[0]
    print(f"clients scraped : {c} (errors: {ce})")
    print(f"attendance rows : {a} across {ac} clients | {adr[0]} .. {adr[1]} | with check-in: {ci}")
    print(f"billing rows    : {b} across {bc} clients | {bdr[0]} .. {bdr[1]}")
    print(f"authorizations  : {au} across {auc} clients")
    print(f"open invoices   : {inv} | open AR items: {ar}")
    print("\nattendance per chunk:")
    for ch, n in db.execute("SELECT chunk, COUNT(*) FROM attendance GROUP BY chunk ORDER BY chunk"):
        print(f"  {ch}: {n}")
    print("billing per chunk:")
    for ch, n in db.execute("SELECT chunk, COUNT(*) FROM billing GROUP BY chunk ORDER BY chunk"):
        print(f"  {ch}: {n}")
    db.close()


def discover(cids):
    for cid in cids:
        log(f"=== DISCOVER client {cid} ===")
        chrome_nav(BASE + f"/Client.aspx?ID={cid}", wait=3)
        if page_state() != "healthy":
            ensure_logged_in()
            chrome_nav(BASE + f"/Client.aspx?ID={cid}", wait=3)
        print("hub URL:", current_url())
        for tb in get_tables():
            print(f"  table {tb['index']}: {len(tb['rows'])} rows")
            for row in tb["rows"][:2]:
                print(f"    {str(row)[:180]}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--discover", nargs="+", type=int, metavar="CID")
    ap.add_argument("--pilot", action="store_true")
    ap.add_argument("--full", action="store_true")
    ap.add_argument("--reports", action="store_true")
    ap.add_argument("--clients", action="store_true")
    ap.add_argument("--clients-limit", type=int, default=None)
    ap.add_argument("--load-db", action="store_true")
    ap.add_argument("--summary", action="store_true")
    args = ap.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    if args.discover:
        discover(args.discover)
    elif args.pilot:
        # 1 small report chunk + 3 clients
        log("PILOT: 1 report chunk (attendance 2026-01) + 3 clients")
        header, rows = run_report_chunk("attendance", "01/01/2026", "01/31/2026")
        log(f"PILOT report chunk: {len(rows)} rows, header={header}")
        append_jsonl({"type": "report_chunk", "report": "attendance",
                      "chunk": "2026-01", "d1": "01/01/2026", "d2": "01/31/2026",
                      "header": header, "rows": rows,
                      "scraped_at": datetime.now().isoformat(timespec="seconds")})
        clients = get_client_ids()
        for cid, nm in list(clients.items())[:3]:
            rec = scrape_client(cid, nm)
            append_jsonl(rec)
            log(f"PILOT client {cid} {nm}: pages={list(rec['pages'])} err={rec['errors']}")
        load_db()
        summary()
    elif args.full or (args.reports and args.clients):
        if args.full or args.reports:
            run_reports()
        if args.full or args.clients:
            run_clients()
        load_db()
        summary()
    elif args.reports:
        run_reports()
        load_db()
        summary()
    elif args.clients:
        run_clients(limit=args.clients_limit)
        load_db()
        summary()
    elif args.load_db:
        load_db()
        summary()
    elif args.summary:
        summary()
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
