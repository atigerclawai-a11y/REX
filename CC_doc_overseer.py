#!/usr/bin/env python3
"""CC_doc_overseer.py — GHS file naming & documentation watchdog.
Observe only. Never deletes, moves, or modifies any file.
  --once    single scan (default, used by launchd)
  --report  print formatted summary, no logging or alerts
"""
import argparse, hashlib, json, logging, os, urllib.request
from datetime import datetime, timezone
from pathlib import Path

# — Config —
REX            = Path.home() / "Desktop" / "REX"
LOG_FILE       = REX / "logs" / "doc_overseer.log"
STATE_FILE     = REX / "logs" / ".doc_overseer_state.json"
WHITELIST_FILE = REX / ".doc_overseer_whitelist"
CUTOFF         = datetime(2026, 6, 1, tzinfo=timezone.utc)
LOG_LIMIT      = 50 * 1024 * 1024   # 50 MB
HASH_LIMIT     = 10 * 1024 * 1024   # 10 MB
CHAT_ID        = "5587703834"
TELEGRAM_API   = "https://api.telegram.org/bot{}/sendMessage"
REF_DOCS       = ["CC_MASTER_BUILD_LOG.md", "CC_PHASE_STATUS.md"]

SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv",
             ".continue", "QUARANTINE_COMMANDS_2026_04_14"}

# Subdirs exempt from CC_ naming (system-generated output, third-party config)
NAMING_EXEMPT = {"logs", "launchd", "menus", "paperless",
                 "scheduled_task_logs", "training_reports"}


# — Setup —
def _setup_log():
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(filename=str(LOG_FILE), level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")
    return logging.getLogger("overseer")

def _load_whitelist():
    if not WHITELIST_FILE.exists():
        return set()
    return {l.strip() for l in WHITELIST_FILE.read_text().splitlines()
            if l.strip() and not l.startswith("#")}


# — File helpers —
def _is_new(p):
    try:
        return datetime.fromtimestamp(p.stat().st_mtime, tz=timezone.utc) >= CUTOFF
    except OSError:
        return False

def _parts(p):
    try:
        return p.relative_to(REX).parts[:-1]
    except ValueError:
        return ()

def _in_cc_archive(p):
    """True if p lives inside a CC_-prefixed directory."""
    return any(pt.startswith("CC_") for pt in _parts(p))

def _skip_naming(p):
    """True when p is exempt from the CC_ naming rule."""
    for pt in _parts(p):
        if pt.startswith("CC_") or pt in NAMING_EXEMPT:
            return True
    return False

def _all_files():
    result = []
    for root, dirs, files in os.walk(REX):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith(".")]
        for name in files:
            if not name.startswith((".", "~")):
                result.append(Path(root) / name)
    return result

def _sha256(p):
    try:
        return None if p.stat().st_size > HASH_LIMIT else \
               hashlib.sha256(p.read_bytes()).hexdigest()
    except OSError:
        return None

def _rel(p):
    try:
        return f"~/{p.relative_to(Path.home())}"
    except ValueError:
        return str(p)

def _v(vtype, p, detail):
    return {"type": vtype, "path": str(p), "detail": detail}


# — Checks —
def check_naming(files, wl):
    return [_v("naming", p, f"No CC_ prefix — {_rel(p)}")
            for p in files
            if p.name not in wl and not _skip_naming(p)
            and _is_new(p) and not p.name.startswith("CC_")]

def check_duplicates(files):
    seen, out = {}, []
    for p in files:
        if _in_cc_archive(p):
            continue
        h = _sha256(p)
        if h is None:
            continue
        if h in seen:
            out.append(_v("duplicate", p, f"Same content as {seen[h].name}"))
        else:
            seen[h] = p
    return out

def check_orphan_docs(wl):
    refs = "".join((REX / d).read_text(errors="ignore")
                   for d in REF_DOCS if (REX / d).exists())
    return [_v("orphan_doc", p,
               "Not referenced in CC_MASTER_BUILD_LOG.md or CC_PHASE_STATUS.md")
            for p in REX.glob("*.md")
            if p.name not in wl and _is_new(p) and p.name not in refs]

def check_oversized_logs(files):
    out = []
    for p in files:
        if not (p.suffix == ".log" or "log" in p.name.lower()):
            continue
        try:
            sz = p.stat().st_size
            if sz > LOG_LIMIT:
                out.append(_v("oversized_log", p, f"{sz/1048576:.1f} MB (limit 50 MB)"))
        except OSError:
            pass
    return out

def check_empty(files, wl):
    out = []
    for p in files:
        if p.name in wl or _in_cc_archive(p):
            continue
        try:
            if p.stat().st_size == 0:
                out.append(_v("empty_file", p, "0 bytes"))
        except OSError:
            pass
    return out


# — State —
def _load_state():
    try:
        return json.loads(STATE_FILE.read_text()) if STATE_FILE.exists() else {}
    except Exception:
        return {}

def _save_state(violations):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(
        {"violations": violations, "last_scan": datetime.now().isoformat(),
         "total": len(violations)}, indent=2))

def _new_only(current, state):
    known = {v["path"] + v["type"] for v in state.get("violations", [])}
    return [v for v in current if v["path"] + v["type"] not in known]


# — Telegram —
def _telegram(msg):
    token = os.environ.get("HERMES_BOT_TOKEN", "")
    if not token:
        return
    try:
        data = json.dumps({"chat_id": CHAT_ID, "text": msg,
                            "parse_mode": "HTML"}).encode()
        req = urllib.request.Request(TELEGRAM_API.format(token), data=data,
                                     headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=10)
    except Exception as exc:
        logging.getLogger("overseer").warning("Telegram failed: %s", exc)


# — Report —
_LABELS = {
    "naming":        "🔴 Missing CC_ prefix",
    "duplicate":     "🟡 Duplicate content",
    "orphan_doc":    "🔵 Orphaned doc",
    "oversized_log": "🟠 Oversized log (>50 MB)",
    "empty_file":    "⚪ Empty file (0 bytes)",
}

def _format(violations):
    if not violations:
        return "✅ No violations found."
    by_type = {}
    for v in violations:
        by_type.setdefault(v["type"], []).append(v)
    lines = [f"⚠️  GHS DOC OVERSEER — {datetime.now():%Y-%m-%d %H:%M}",
             f"Total: {len(violations)} violation(s)", ""]
    for vtype, items in by_type.items():
        lines.append(f"{_LABELS.get(vtype, vtype)}  ({len(items)})")
        for v in items:
            lines.append(f"  {_rel(Path(v['path']))}  —  {v['detail']}")
        lines.append("")
    return "\n".join(lines)


# — Run —
def run(report_mode=False):
    wl    = _load_whitelist()
    files = _all_files()

    violations = (check_naming(files, wl) + check_duplicates(files)
                  + check_orphan_docs(wl) + check_oversized_logs(files)
                  + check_empty(files, wl))

    if report_mode:
        print(_format(violations))
        return

    log = _setup_log()   # create log file only when actually writing

    state = _load_state()
    new_v = _new_only(violations, state)
    log.info("Scan complete: %d total, %d new", len(violations), len(new_v))
    for v in new_v:
        log.warning("NEW %s: %s — %s", v["type"].upper(), v["path"], v["detail"])

    if new_v:
        msg = (f"⚠️ <b>GHS Doc Overseer</b> — {len(new_v)} new violation(s) "
               f"in ~/Desktop/REX\n")
        for v in new_v[:10]:
            msg += f"\n• [{v['type']}] {_rel(Path(v['path']))}"
        if len(new_v) > 10:
            msg += f"\n…+{len(new_v) - 10} more. See logs/doc_overseer.log"
        _telegram(msg)

    _save_state(violations)


def main():
    ap = argparse.ArgumentParser(
        description="GHS Doc Overseer — observe only, never modify files")
    ap.add_argument("--once",   action="store_true",
                    help="Single scan and exit (same as default)")
    ap.add_argument("--report", action="store_true",
                    help="Print formatted report; no logging or alerts")
    run(report_mode=ap.parse_args().report)


if __name__ == "__main__":
    main()
