#!/usr/bin/env python3
"""CC_carecenta_extract — STAGING-ONLY local extraction of auth data from the 751
date-less CARECENTA PDFs. Downloads each PDF, extracts text LOCALLY (PyMuPDF; no cloud),
finds client name + expiry/service dates, writes candidates to carecenta_staging.json.
NEVER writes to the authorization table — Kato reviews staging first."""
import sys, json, re, io, time, pathlib
sys.path.insert(0, '/Users/mainsobhelper/Desktop/REX')
import importlib.util
spec = importlib.util.spec_from_file_location("ing", "/Users/mainsobhelper/Desktop/REX/CC_goj_drive_ingest.py")
ing = importlib.util.module_from_spec(spec); spec.loader.exec_module(ing)
import fitz
from googleapiclient.http import MediaIoBaseDownload

OUT = pathlib.Path("/Users/mainsobhelper/Desktop/REX/state/carecenta_staging.json")
FOLDER = "14AVRfWJH9aAuvHec0dRoZ3DgP6MWNJJt"
NAME_RE = re.compile(r"^(?P<name>[A-Z][A-Z .'-]*?)\s+(?:(TR|VIS|TR VIS|VIS TR|F)\s+)?(\d{1,2})\.(\d{1,2})\.(\d{2})", re.I)
DATE_RES = [
    re.compile(r"(?:through|thru|to|end(?:ing)?(?:\s*date)?|expir\w*)[:\s]*?(\d{1,2})[/.-](\d{1,2})[/.-](\d{2,4})", re.I),
    re.compile(r"(\d{1,2})[/.](\d{1,2})[/.](\d{4})\s*[-–]\s*(\d{1,2})[/.](\d{1,2})[/.](\d{4})"),
]
def norm_date(mo, dy, yr):
    yr = int(yr); yr = yr+2000 if yr < 100 else yr
    try: return f"{yr:04d}-{int(mo):02d}-{int(dy):02d}"
    except Exception: return None

svc = ing.get_services()
files, tok = [], None
while True:
    r = svc["drive"].files().list(q=f"'{FOLDER}' in parents and trashed=false and mimeType='application/pdf'",
        fields="nextPageToken,files(id,name,modifiedTime)", pageSize=500, pageToken=tok).execute()
    files += r.get("files", []); tok = r.get("nextPageToken")
    if not tok: break
targets = [f for f in files if not NAME_RE.match(f["name"])]
print(f"{len(files)} PDFs total; {len(targets)} date-less to extract", flush=True)

staging = json.loads(OUT.read_text()) if OUT.exists() else {}
done = 0
for i, f in enumerate(targets):
    if f["id"] in staging: continue
    rec = {"file_name": f["name"], "modified": f.get("modifiedTime","")[:10], "dates_found": [], "status": "no_text"}
    try:
        buf = io.BytesIO(); dl = MediaIoBaseDownload(buf, svc["drive"].files().get_media(fileId=f["id"]))
        d = False
        while not d: _, d = dl.next_chunk()
        doc = fitz.open(stream=buf.getvalue(), filetype="pdf")
        text = "".join(p.get_text() for p in doc)[:20000]
        if len(text.strip()) < 30:
            rec["status"] = "image_only_needs_tesseract"
        else:
            dates = set()
            for rx in DATE_RES:
                for m in rx.finditer(text):
                    g = m.groups()
                    cand = norm_date(g[-3], g[-2], g[-1]) if len(g) >= 3 else None
                    if cand and cand > "2024-01-01": dates.add(cand)
            rec["dates_found"] = sorted(dates)[-4:]
            rec["status"] = "dates_found" if dates else "text_no_dates"
            stem = re.split(r"\d|\.pdf", f["name"], 1, re.I)[0].strip()
            rec["name_guess"] = stem.title()
    except Exception as e:
        rec["status"] = f"error: {str(e)[:80]}"
    staging[f["id"]] = rec; done += 1
    if done % 25 == 0:
        OUT.write_text(json.dumps(staging, indent=1)); print(f"  {done}/{len(targets)} staged…", flush=True)
OUT.write_text(json.dumps(staging, indent=1))
from collections import Counter
c = Counter(v["status"].split(":")[0] for v in staging.values())
print("DONE:", dict(c), f"-> {OUT}", flush=True)
