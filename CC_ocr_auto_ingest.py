#!/usr/bin/env python3
"""
CC_ocr_auto_ingest.py — Unified GOJ OCR Auto-Ingestion Pipeline
================================================================
ONE module that replaces the scattered intake flow. It:
  1. Polls 3 Gmail accounts (IMAP) for PDF/image attachments
  2. Watches ~/Documents/goj files/scans/ for new files
  3. SHA-256 dedups against a JSONL manifest
  4. Routes new files to the existing CC_ocr_worker for OCR
  5. Moves originals into scans/processed/ (NEVER deletes)
  6. Writes a timestamped audit log of every action
  7. Checkpoints after every file → fully resumable on restart

Usage
-----
    python3 CC_ocr_auto_ingest.py            # run the perpetual watch loop
    python3 CC_ocr_auto_ingest.py --once     # run a single poll cycle and exit
    python3 CC_ocr_auto_ingest.py --status   # print manifest + checkpoint summary

Environment variables
---------------------
    GOJ_GMAIL_ACCOUNTS   JSON list of {email, app_password} dicts. Required for
                         IMAP intake. If absent, Gmail polling is skipped (folder
                         watch still works).  Example:
                         '[{"email":"a@x.com","app_password":"xxxx xxxx xxxx xxxx"}]'
    GOJ_SCAN_WATCH_DIR   Directory to watch for new scans.
                         Default: ~/Documents/goj files/scans
    GOJ_POLL_INTERVAL    Seconds between poll cycles (default: 60).
    GOJ_DATA_MODE        'synthetic' (permissive, raw logs) or 'real' (redact PHI
                         in audit log).  Default: 'real'.
    GOJ_IMAP_HOST        IMAP host (default: imap.gmail.com).
    GOJ_IMAP_PORT        IMAP port (default: 993).
    GOJ_IMAP_LOOKBACK    Days back to scan if no checkpoint exists (default: 14).
    GOJ_OCR_MODE         OCR mode passed to CC_ocr_worker: hybrid|local
                         (default: hybrid).
    GOJ_WORKER_PYTHON    Python interpreter for the worker subprocess fallback.
                         Default: sys.executable.

Files written
-------------
    ~/Desktop/REX/CC_ocr_manifest.json           JSONL — one record per file
    ~/Desktop/REX/CC_ocr_email_checkpoint.json   per-account last-seen UID map
    ~/Desktop/REX/CC_ocr_auto_ingest.log         audit log
    ~/Documents/goj files/scans/                 incoming staging dir
    ~/Documents/goj files/scans/processed/       moved originals (never deleted)
"""

from __future__ import annotations

import argparse
import email
import hashlib
import imaplib
import json
import logging
import os
import re
import shutil
import signal
import subprocess
import sys
import time
import traceback
from datetime import datetime, timedelta
from email.header import decode_header
from pathlib import Path
from typing import Any, Iterable

# ── Constants & paths ──────────────────────────────────────────────────────
HOME       = Path.home()
REX_DIR    = HOME / "Desktop" / "REX"
SCAN_DIR   = Path(os.environ.get(
    "GOJ_SCAN_WATCH_DIR",
    str(HOME / "Documents" / "goj files" / "scans"),
)).expanduser()
PROCESSED_DIR = SCAN_DIR / "processed"
MANIFEST_PATH = REX_DIR / "CC_ocr_manifest.json"
CHECKPOINT_PATH = REX_DIR / "CC_ocr_email_checkpoint.json"
LOG_PATH      = REX_DIR / "CC_ocr_auto_ingest.log"

ALLOWED_ACCOUNTS = {
    "atigerclawai@gmail.com",
    "goj3152.scans@gmail.com",
    "allen@gardenofjoybrooklyn.com",
}

PDF_EXT   = {".pdf"}
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".heic", ".webp", ".bmp"}
ACCEPTED_EXT = PDF_EXT | IMAGE_EXT

POLL_INTERVAL = int(os.environ.get("GOJ_POLL_INTERVAL", "60"))
DATA_MODE     = os.environ.get("GOJ_DATA_MODE", "real").strip().lower()
IMAP_HOST     = os.environ.get("GOJ_IMAP_HOST", "imap.gmail.com")
IMAP_PORT     = int(os.environ.get("GOJ_IMAP_PORT", "993"))
IMAP_LOOKBACK = int(os.environ.get("GOJ_IMAP_LOOKBACK", "14"))
OCR_MODE      = os.environ.get("GOJ_OCR_MODE", "hybrid").strip().lower()
WORKER_PY     = os.environ.get("GOJ_WORKER_PYTHON", sys.executable)

# ── Ensure dirs exist ──────────────────────────────────────────────────────
REX_DIR.mkdir(parents=True, exist_ok=True)
SCAN_DIR.mkdir(parents=True, exist_ok=True)
PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

# ── Logging setup (audit log) ──────────────────────────────────────────────
_logger = logging.getLogger("cc_ocr_auto_ingest")
_logger.setLevel(logging.INFO)
if not _logger.handlers:
    _fmt = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")
    _fh  = logging.FileHandler(LOG_PATH)
    _fh.setFormatter(_fmt)
    _sh  = logging.StreamHandler()
    _sh.setFormatter(_fmt)
    _logger.addHandler(_fh)
    _logger.addHandler(_sh)


# ── PHI redaction ──────────────────────────────────────────────────────────
_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_PHONE_RE = re.compile(r"\b\d{3}[-.\s]?\d{3}[-.\s]?\d{4}\b")
_DOB_RE   = re.compile(r"\b(0?[1-9]|1[0-2])[/-](0?[1-9]|[12]\d|3[01])[/-](19|20)\d{2}\b")

def redact(text: str) -> str:
    """Redact PHI from a log message when GOJ_DATA_MODE=='real'."""
    if DATA_MODE == "synthetic" or not text:
        return text
    s = _EMAIL_RE.sub("<email>", str(text))
    s = _PHONE_RE.sub("<phone>", s)
    s = _DOB_RE.sub("<dob>", s)
    return s

def log(level: str, msg: str) -> None:
    getattr(_logger, level.lower(), _logger.info)(redact(msg))


# ── Manifest (JSONL) ───────────────────────────────────────────────────────
def _read_manifest() -> list[dict]:
    if not MANIFEST_PATH.exists():
        return []
    rows: list[dict] = []
    with MANIFEST_PATH.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows

def _seen_hashes() -> set[str]:
    return {r.get("sha256") for r in _read_manifest() if r.get("sha256")}

def _append_manifest(record: dict) -> None:
    record.setdefault("received_at", datetime.utcnow().isoformat() + "Z")
    with MANIFEST_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


# ── Email checkpoint (per-account last-seen UID) ───────────────────────────
def load_checkpoint() -> dict:
    if not CHECKPOINT_PATH.exists():
        return {}
    try:
        return json.loads(CHECKPOINT_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        log("warning", f"Checkpoint corrupt at {CHECKPOINT_PATH} — starting fresh")
        return {}

def save_checkpoint(ckpt: dict) -> None:
    tmp = CHECKPOINT_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(ckpt, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(CHECKPOINT_PATH)


# ── Hashing & file utilities ───────────────────────────────────────────────
def sha256_file(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            buf = f.read(chunk)
            if not buf:
                break
            h.update(buf)
    return h.hexdigest()

def is_accepted_file(path: Path) -> bool:
    return path.is_file() and path.suffix.lower() in ACCEPTED_EXT

def safe_filename(name: str) -> str:
    name = name.replace("/", "_").replace("\\", "_").strip()
    return name or f"file_{int(time.time())}"

def unique_path(dest_dir: Path, filename: str) -> Path:
    base = safe_filename(filename)
    p = dest_dir / base
    if not p.exists():
        return p
    stem, ext = Path(base).stem, Path(base).suffix
    i = 1
    while True:
        cand = dest_dir / f"{stem}__{i}{ext}"
        if not cand.exists():
            return cand
        i += 1


# ── Gmail IMAP intake ──────────────────────────────────────────────────────
def _load_gmail_accounts() -> list[dict]:
    raw = os.environ.get("GOJ_GMAIL_ACCOUNTS", "").strip()
    if not raw:
        log("info", "GOJ_GMAIL_ACCOUNTS not set — skipping Gmail intake")
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        log("error", f"GOJ_GMAIL_ACCOUNTS is not valid JSON: {e}")
        return []
    if not isinstance(data, list):
        log("error", "GOJ_GMAIL_ACCOUNTS must be a JSON list of {email, app_password}")
        return []
    valid: list[dict] = []
    for acct in data:
        if not isinstance(acct, dict):
            continue
        em = (acct.get("email") or "").strip().lower()
        pw = acct.get("app_password") or acct.get("password")
        if not em or not pw:
            log("warning", f"Skipping malformed account entry: {redact(str(acct))}")
            continue
        if em not in ALLOWED_ACCOUNTS:
            log("warning", f"Account {em} not in ALLOWED_ACCOUNTS — skipping")
            continue
        valid.append({"email": em, "app_password": pw})
    return valid

def _decode_header(value: str | None) -> str:
    if not value:
        return ""
    parts = decode_header(value)
    out = []
    for txt, enc in parts:
        if isinstance(txt, bytes):
            try:
                out.append(txt.decode(enc or "utf-8", errors="replace"))
            except LookupError:
                out.append(txt.decode("utf-8", errors="replace"))
        else:
            out.append(txt)
    return "".join(out)

def _imap_search_uids(M: imaplib.IMAP4_SSL, since_date: str) -> list[bytes]:
    """Search for messages with attachments since `since_date` (dd-Mon-YYYY)."""
    typ, data = M.uid("search", None, f'(SINCE "{since_date}")')
    if typ != "OK" or not data or not data[0]:
        return []
    return data[0].split()

def _extract_attachments(msg: email.message.Message) -> list[tuple[str, bytes]]:
    out: list[tuple[str, bytes]] = []
    for part in msg.walk():
        if part.is_multipart():
            continue
        disp = (part.get("Content-Disposition") or "").lower()
        ctype = (part.get_content_type() or "").lower()
        fname = _decode_header(part.get_filename() or "")
        # Accept by extension OR by content-type
        is_pdf  = ctype == "application/pdf" or fname.lower().endswith(".pdf")
        is_img  = ctype.startswith("image/") or (
            fname and Path(fname).suffix.lower() in IMAGE_EXT
        )
        if not (is_pdf or is_img):
            continue
        if "attachment" not in disp and not fname:
            # inline image without filename — synthesize one
            ext = (ctype.split("/")[-1] or "bin").split(";")[0]
            fname = f"inline_{int(time.time()*1000)}.{ext}"
        payload = part.get_payload(decode=True)
        if not payload:
            continue
        out.append((safe_filename(fname), payload))
    return out

def poll_gmail_account(account: dict, checkpoint: dict) -> list[Path]:
    """
    Poll one Gmail IMAP account for new PDF/image attachments.
    Saves attachments into SCAN_DIR, updates checkpoint, returns new file paths.
    """
    em = account["email"]
    pw = account["app_password"]
    saved: list[Path] = []

    acct_ckpt = checkpoint.setdefault(em, {"last_uid": 0})
    last_uid  = int(acct_ckpt.get("last_uid", 0) or 0)
    since     = (datetime.utcnow() - timedelta(days=IMAP_LOOKBACK)).strftime("%d-%b-%Y")

    log("info", f"[gmail] connecting to {IMAP_HOST}:{IMAP_PORT} as {em}")
    try:
        M = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT)
        M.login(em, pw)
    except Exception as e:
        log("error", f"[gmail] login failed for {em}: {e}")
        return saved

    try:
        M.select("INBOX")
        uids = _imap_search_uids(M, since)
        new_uids = [u for u in uids if int(u) > last_uid]
        log("info", f"[gmail] {em}: {len(uids)} since {since}, "
                    f"{len(new_uids)} newer than UID {last_uid}")

        max_uid_seen = last_uid
        for uid_b in sorted(new_uids, key=lambda x: int(x)):
            uid_int = int(uid_b)
            try:
                typ, data = M.uid("fetch", uid_b, "(RFC822)")
                if typ != "OK" or not data or not data[0]:
                    max_uid_seen = max(max_uid_seen, uid_int)
                    continue
                msg = email.message_from_bytes(data[0][1])
                subj = _decode_header(msg.get("Subject", ""))
                sender = _decode_header(msg.get("From", ""))
                atts = _extract_attachments(msg)
                if atts:
                    log("info", f"[gmail] uid={uid_int} from={sender} "
                                f"subj={subj!r} attachments={len(atts)}")
                for fname, payload in atts:
                    target = unique_path(SCAN_DIR, f"gmail_{em.split('@')[0]}_{uid_int}_{fname}")
                    target.write_bytes(payload)
                    log("info", f"[gmail] saved {target.name} ({target.stat().st_size} bytes)")
                    saved.append(target)
            except Exception as fetch_err:
                log("warning", f"[gmail] uid={uid_int} fetch failed: {fetch_err}")
            finally:
                max_uid_seen = max(max_uid_seen, uid_int)
                # Checkpoint after EVERY message — fully idempotent
                acct_ckpt["last_uid"] = max_uid_seen
                acct_ckpt["last_checked"] = datetime.utcnow().isoformat() + "Z"
                save_checkpoint(checkpoint)
    finally:
        try:
            M.logout()
        except Exception:
            pass

    return saved


# ── Worker routing ────────────────────────────────────────────────────────
def _route_via_import(pdf_path: Path) -> tuple[bool, str]:
    """Try to enqueue+process via direct import of CC_ocr_worker. Returns (ok, detail)."""
    try:
        sys.path.insert(0, str(REX_DIR))
        from CC_ocr_queue import enqueue_scan  # type: ignore
        import CC_ocr_worker  # type: ignore
        job_id = enqueue_scan(str(pdf_path), OCR_MODE)
        detail = f"enqueued job_id={job_id} mode={OCR_MODE}"
        CC_ocr_worker.process_queue()
        return True, detail
    except Exception as e:
        return False, f"import-route failed: {e}"

def _route_via_subprocess(pdf_path: Path) -> tuple[bool, str]:
    """Fallback: subprocess-call CC_ocr_worker.py with --file/--mode."""
    worker = REX_DIR / "CC_ocr_worker.py"
    if not worker.exists():
        return False, f"worker missing at {worker}"
    cmd = [WORKER_PY, str(worker), "--file", str(pdf_path), "--mode", OCR_MODE]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        ok = r.returncode == 0
        tail = (r.stdout or "")[-400:] + (r.stderr or "")[-400:]
        return ok, f"rc={r.returncode} tail={tail.strip()[:600]}"
    except subprocess.TimeoutExpired:
        return False, "worker subprocess timeout"
    except Exception as e:
        return False, f"subprocess failed: {e}"

def route_to_worker(pdf_path: Path) -> tuple[bool, str]:
    """Send a file to the existing CC_ocr_worker. Import-first, subprocess-fallback."""
    ok, detail = _route_via_import(pdf_path)
    if ok:
        return True, detail
    log("warning", f"[route] import path failed: {detail} — using subprocess")
    return _route_via_subprocess(pdf_path)


# ── Core ingest of a single file ──────────────────────────────────────────
def ingest_file(path: Path, source: str, seen: set[str]) -> dict:
    """Hash → dedup → route to worker → move to processed/. Returns manifest row."""
    record = {
        "source":       source,
        "filename":     path.name,
        "sha256":       None,
        "received_at":  datetime.utcnow().isoformat() + "Z",
        "processed_at": None,
        "status":       "pending",
        "output_path":  None,
        "detail":       "",
    }
    try:
        if not is_accepted_file(path):
            record["status"] = "skipped_unsupported"
            record["detail"] = f"ext={path.suffix}"
            log("info", f"[ingest] skip non-accepted file: {path.name}")
            _append_manifest(record)
            return record

        digest = sha256_file(path)
        record["sha256"] = digest

        if digest in seen:
            record["status"] = "skipped_duplicate"
            record["detail"] = "sha256 already in manifest"
            log("info", f"[ingest] dup sha256={digest[:12]}… {path.name}")
            _append_manifest(record)
            return record

        log("info", f"[ingest] new file source={source} name={path.name} sha={digest[:12]}…")
        ok, detail = route_to_worker(path)
        record["detail"] = detail

        # Move original to processed/ (NEVER delete)
        dest = unique_path(PROCESSED_DIR, path.name)
        try:
            shutil.move(str(path), str(dest))
            record["output_path"] = str(dest)
            log("info", f"[ingest] moved → {dest}")
        except Exception as mv:
            log("warning", f"[ingest] move failed: {mv} — leaving file in place")
            record["output_path"] = str(path)

        record["status"]       = "processed" if ok else "worker_error"
        record["processed_at"] = datetime.utcnow().isoformat() + "Z"
        seen.add(digest)
    except Exception as e:
        record["status"] = "exception"
        record["detail"] = f"{type(e).__name__}: {e}"
        log("error", f"[ingest] exception on {path.name}: {e}\n{traceback.format_exc()}")
    finally:
        _append_manifest(record)
    return record


# ── Folder watch ──────────────────────────────────────────────────────────
def scan_folder(seen: set[str]) -> Iterable[Path]:
    """Yield candidate files from SCAN_DIR (non-recursive, skips processed/)."""
    for child in sorted(SCAN_DIR.iterdir()):
        if child.is_dir():
            continue
        if child.name.startswith("."):
            continue
        if not is_accepted_file(child):
            continue
        # Skip files that are still being written (size unstable)
        try:
            size1 = child.stat().st_size
            time.sleep(0.5)
            size2 = child.stat().st_size
            if size1 != size2 or size1 == 0:
                log("info", f"[watch] skipping unstable file: {child.name}")
                continue
        except FileNotFoundError:
            continue
        yield child


# ── One full poll cycle ───────────────────────────────────────────────────
def poll_once() -> dict:
    t0 = time.time()
    log("info", "=" * 60)
    log("info", f"[poll] cycle start mode={DATA_MODE} scan_dir={SCAN_DIR}")

    seen = _seen_hashes()
    summary: dict[str, Any] = {
        "started_at":      datetime.utcnow().isoformat() + "Z",
        "gmail_saved":     0,
        "folder_ingested": 0,
        "duplicates":      0,
        "errors":          0,
    }

    # 1. Gmail intake
    accounts = _load_gmail_accounts()
    if accounts:
        checkpoint = load_checkpoint()
        for acct in accounts:
            try:
                files = poll_gmail_account(acct, checkpoint)
                summary["gmail_saved"] += len(files)
            except Exception as e:
                log("error", f"[gmail] poll failed for {acct['email']}: {e}")
                summary["errors"] += 1
    else:
        log("info", "[gmail] no accounts configured — skipping IMAP step")

    # 2. Folder watch (catches both Gmail-dropped and externally-dropped files)
    for f in scan_folder(seen):
        rec = ingest_file(f, source="folder", seen=seen)
        if rec["status"] == "processed":
            summary["folder_ingested"] += 1
        elif rec["status"] == "skipped_duplicate":
            summary["duplicates"] += 1
        elif rec["status"] in ("worker_error", "exception"):
            summary["errors"] += 1

    summary["elapsed_sec"] = round(time.time() - t0, 2)
    log("info", f"[poll] cycle done {summary}")
    return summary


# ── Status report ─────────────────────────────────────────────────────────
def print_status() -> None:
    rows = _read_manifest()
    ckpt = load_checkpoint()
    by_status: dict[str, int] = {}
    for r in rows:
        by_status[r.get("status", "?")] = by_status.get(r.get("status", "?"), 0) + 1
    print(f"Manifest: {MANIFEST_PATH}  ({len(rows)} entries)")
    for k, v in sorted(by_status.items()):
        print(f"  {k:24s} {v}")
    print(f"Checkpoint: {CHECKPOINT_PATH}")
    for em, meta in ckpt.items():
        print(f"  {em:40s} last_uid={meta.get('last_uid')}  "
              f"checked={meta.get('last_checked','-')}")
    print(f"Scan dir:    {SCAN_DIR}")
    print(f"Processed:   {PROCESSED_DIR}")
    print(f"Audit log:   {LOG_PATH}")
    print(f"Data mode:   {DATA_MODE}")


# ── Main loop ─────────────────────────────────────────────────────────────
_stop = False
def _handle_sig(signum, _frame):
    global _stop
    _stop = True
    log("info", f"[signal] received {signum} — stopping after current cycle")

def main() -> int:
    parser = argparse.ArgumentParser(description="GOJ unified OCR auto-ingestion pipeline")
    parser.add_argument("--once", action="store_true", help="run one poll cycle and exit")
    parser.add_argument("--status", action="store_true", help="print summary and exit")
    args = parser.parse_args()

    if args.status:
        print_status()
        return 0

    signal.signal(signal.SIGINT,  _handle_sig)
    signal.signal(signal.SIGTERM, _handle_sig)

    log("info", f"[boot] CC_ocr_auto_ingest starting pid={os.getpid()} "
                f"interval={POLL_INTERVAL}s once={args.once} mode={DATA_MODE}")

    if args.once:
        poll_once()
        return 0

    while not _stop:
        try:
            poll_once()
        except Exception as e:
            log("error", f"[main] poll_once crashed: {e}\n{traceback.format_exc()}")
        # Sleep in 1-sec slices so signals stop us promptly
        slept = 0
        while slept < POLL_INTERVAL and not _stop:
            time.sleep(1)
            slept += 1

    log("info", "[boot] CC_ocr_auto_ingest exiting cleanly")
    return 0


if __name__ == "__main__":
    sys.exit(main())
