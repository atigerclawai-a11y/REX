#!/usr/bin/env python3
"""signin_attendance_backup.py — build a durable attendance backup from the
scanned sign-in PDFs Kato forwards through email.

REPLACES the Drive-sheet CC_signin_snapshot (Kato 2026-08-05: attendance backup
must come from the emailed scanned PDFs, not Drive sheets).

For every sign-in scan in signin_intake/:
  1. Uses the MinerU OCR output (signin_ocr_full/<doc>/ocr/<doc>.md) — runs MinerU
     only if missing.
  2. Parses (date, shift, names) via the same logic as signin_attendance_bridge.
  3. Writes a per-day attendance backup JSON + CSV into
     ~/Desktop/REX/attendance_backups/<date>_S<shift>.{json,csv}
     (client names present, source=signin_ocr, doc_id).

PHI stays local. No cloud. Silent on nothing-new. Retention: keep all (small files).
"""
import csv
import json
import re
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

SIGNIN_DIR = Path.home() / "Desktop" / "REX" / "signin_intake"
OCR_DIR = Path.home() / "Desktop" / "REX" / "signin_ocr_full"
BACKUP_DIR = Path.home() / "Desktop" / "REX" / "attendance_backups"
STATE_FILE = Path.home() / ".hermes" / "profiles" / "work" / "state" / "signin_attendance_backup_state.json"
MINERU = Path.home() / "Desktop" / "REX" / "mineru-venv" / "bin" / "mineru"

for d in [BACKUP_DIR, STATE_FILE.parent]:
    d.mkdir(parents=True, exist_ok=True)

state = json.loads(STATE_FILE.read_text()) if STATE_FILE.exists() else {}


def run_mineru(pdf_path, doc_id):
    ocr_out = OCR_DIR / doc_id
    md_path = ocr_out / "ocr" / f"{doc_id}.md"
    if md_path.exists():
        return md_path
    ocr_out.mkdir(parents=True, exist_ok=True)
    r = subprocess.run(
        [str(MINERU), "-b", "pipeline", "-p", str(pdf_path), "-o", str(ocr_out)],
        capture_output=True, text=True, timeout=1800)
    auto_md = ocr_out / doc_id / "auto" / f"{doc_id}.md"
    if auto_md.exists():
        (ocr_out / "ocr").mkdir(parents=True, exist_ok=True)
        auto_md.replace(md_path)
    return md_path if md_path.exists() else None


def parse_signin_md(md_text, doc_id=None):
    date_match = re.search(r'Date:\s*([A-Za-z]+,\s+[A-Za-z]+\s+\d{1,2},\s+\d{4})', md_text)
    shift_match = re.search(r'Shift:\s*(\d)', md_text)
    dt = None
    if date_match:
        try:
            dt = datetime.strptime(date_match.group(1).strip(), "%A, %B %d, %Y").strftime("%Y-%m-%d")
        except ValueError:
            try:
                dt = datetime.strptime(date_match.group(1).strip(), "%A, %b %d, %Y").strftime("%Y-%m-%d")
            except ValueError:
                pass
    if shift_match is None:
        shift_match = re.search(r'(\d)(?:st|nd|rd|th)\s*shift', md_text, re.I)
    shift = shift_match.group(1) if shift_match else None
    if dt is None:
        wd_match = re.search(r"for the date\s*([A-Za-z]+)", md_text)
        if wd_match and doc_id:
            wd = wd_match.group(1).strip().lower()
            wd_map = {'monday': 0, 'tuesday': 1, 'wednesday': 2, 'thursday': 3,
                      'friday': 4, 'saturday': 5, 'sunday': 6}
            m = re.search(r'doc\d{6}(\d{8})', doc_id or '')
            if wd in wd_map and m:
                scan_d = datetime.strptime(m.group(1), "%Y%m%d")
                for back in range(14):
                    cand = scan_d - timedelta(days=back)
                    if cand.weekday() == wd_map[wd]:
                        dt = cand.strftime("%Y-%m-%d")
                        break
    names = []
    for row in re.finditer(r'<tr>(.*?)</tr>', md_text, re.S):
        tds = re.findall(r'<td[^>]*>(.*?)</td>', row.group(1), re.S)
        if len(tds) < 2:
            continue
        if tds[0].strip().lower() in ('no', 'n') or tds[1].strip().lower() == 'name':
            continue
        num = tds[0].strip()
        if num.isdigit():
            name = re.sub(r'<[^>]+>', '', tds[1]).strip()
        else:
            # name-first format (Member's Daily Attendance Report): td[0]=name, td[1]=plan
            name = re.sub(r'<[^>]+>', '', tds[0]).strip()
        if name and re.match(r"^[A-Za-zА-Яа-яЁё'\- ]+$", name) and len(name.split()) >= 2:
            names.append(name)
    seen, uniq = set(), []
    for n in names:
        if n not in seen:
            seen.add(n)
            uniq.append(n)
    return {"date": dt, "shift": shift, "names": uniq, "name_count": len(uniq)}


def main():
    made = 0
    for pdf in sorted(SIGNIN_DIR.glob("*.pdf")):
        doc_id = pdf.stem
        if state.get(doc_id) == "done":
            continue
        md_path = run_mineru(pdf, doc_id)
        if not md_path:
            state[doc_id] = "ocr_failed"
            continue
        md_text = md_path.read_text(errors="ignore")
        parsed = parse_signin_md(md_text, doc_id)
        if not parsed["date"] or not parsed["shift"] or not parsed["names"]:
            state[doc_id] = "parse_failed"
            continue

        date_str, shift = parsed["date"], parsed["shift"]
        payload = {
            "date": date_str,
            "shift": shift,
            "day_key": {0: "M", 1: "T", 2: "W", 3: "TH", 4: "F", 5: "Sa", 6: "Su"}[
                datetime.fromisoformat(date_str).weekday()],
            "source": "signin_ocr",
            "doc_id": doc_id,
            "name_count": parsed["name_count"],
            "names": sorted(parsed["names"]),
            "backed_up_at": datetime.now().isoformat(),
        }
        jpath = BACKUP_DIR / f"{date_str}_S{shift}.json"
        # merge if exists
        if jpath.exists():
            prev = json.loads(jpath.read_text())
            merged = sorted(set(prev.get("names", [])) | set(payload["names"]))
            prev["names"] = merged
            prev["name_count"] = len(merged)
            prev["doc_ids"] = sorted(set(prev.get("doc_ids", [])) | {doc_id})
            jpath.write_text(json.dumps(prev, ensure_ascii=False, indent=1))
        else:
            payload["doc_ids"] = [doc_id]
            jpath.write_text(json.dumps(payload, ensure_ascii=False, indent=1))
        # CSV
        cpath = BACKUP_DIR / f"{date_str}_S{shift}.csv"
        with open(cpath, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["date", "shift", "client_name"])
            for n in sorted(set(parsed["names"])):
                w.writerow([date_str, shift, n])
        state[doc_id] = "done"
        made += 1
        print(f"[BACKUP] {date_str} S{shift}: {parsed['name_count']} names -> {jpath.name}")

    if made:
        STATE_FILE.write_text(json.dumps(state, indent=1))
        print(f"[BACKUP] {made} sheet(s) backed up to {BACKUP_DIR}")


if __name__ == "__main__":
    main()
