#!/usr/bin/env python3
"""Generate the human-readable CARECENTA staging review report for Kato.
Reads carecenta_staging.json -> writes CARECENTA_REVIEW.md + .html (gold/dark).
Read-only; nothing touches the authorization table."""
import json, pathlib, datetime, re
from collections import Counter

S = pathlib.Path("/Users/mainsobhelper/Desktop/REX/state/carecenta_staging.json")
MD = pathlib.Path("/Users/mainsobhelper/Desktop/GHS_Sessions/CARECENTA_REVIEW.md")
staging = json.loads(S.read_text())
c = Counter(v["status"].split(":")[0] for v in staging.values())
ready = {k:v for k,v in staging.items() if v.get("dates_found")}
noinfo = {k:v for k,v in staging.items() if not v.get("dates_found")}

lines = [f"# CARECENTA Staging Review — {datetime.date.today()}",
 f"\n**{len(staging)} PDFs processed locally (zero cloud). NOTHING written to the authorization table — your approval applies the rows below.**\n",
 f"\nStatus mix: {dict(c)}\n",
 f"\n## ✅ READY — {len(ready)} PDFs with extracted dates (proposed: latest date = service_end_date)\n",
 "| File | Name guess | Dates found | Proposed end date |", "|---|---|---|---|"]
for fid, v in sorted(ready.items(), key=lambda kv: kv[1]["file_name"]):
    nm = v.get("name_guess") or re.split(r"\d|\.pdf", v["file_name"], 1, re.I)[0].strip().title()
    dates = ", ".join(v["dates_found"]); prop = max(v["dates_found"])
    lines.append(f"| {v['file_name'][:48]} | {nm[:28]} | {dates} | **{prop}** |")
lines += [f"\n## ⚠️ NO DATES EXTRACTED — {len(noinfo)} PDFs (need manual/Telegram review)\n",
 "| File | Status |", "|---|---|"]
for fid, v in sorted(noinfo.items(), key=lambda kv: kv[1]["file_name"])[:80]:
    lines.append(f"| {v['file_name'][:60]} | {v['status'][:40]} |")
if len(noinfo) > 80: lines.append(f"| … +{len(noinfo)-80} more | see staging json |")
lines += ["\n## To APPLY the ready rows after your review",
 "Say the word and the agent inserts ONLY the ✅ rows (client_name + proposed end date, dedup on name+date, auth_number=DRIVE-<id>) — same idempotent pattern as the filename parser.",
 f"\nRaw staging: `{S}`"]
MD.write_text("\n".join(lines), encoding="utf-8")
print(f"report: {MD} | ready={len(ready)} noinfo={len(noinfo)} | {dict(c)}")
