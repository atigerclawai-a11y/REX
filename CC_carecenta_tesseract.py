#!/usr/bin/env python3
"""Pass 2: local tesseract OCR over the image-only CARECENTA scans in staging.
Renders page 1-2 via PyMuPDF pixmap -> local tesseract -> date regexes.
STAGING ONLY (updates carecenta_staging.json). No cloud. No live-table writes."""
import sys, json, re, io, os, subprocess, tempfile, pathlib
sys.path.insert(0, '/Users/mainsobhelper/Desktop/REX')
os.environ.setdefault("TESSDATA_PREFIX", "/opt/homebrew/share/tessdata")
import importlib.util
spec = importlib.util.spec_from_file_location("ing", "/Users/mainsobhelper/Desktop/REX/CC_goj_drive_ingest.py")
ing = importlib.util.module_from_spec(spec); spec.loader.exec_module(ing)
import fitz
from googleapiclient.http import MediaIoBaseDownload

OUT = pathlib.Path("/Users/mainsobhelper/Desktop/REX/state/carecenta_staging.json")
TESS = os.path.expanduser("~/.local/bin/tesseract")
DATE_RES = [
    re.compile(r"(?:through|thru|to|end(?:ing)?(?:\s*date)?|expir\w*)[:\s]*?(\d{1,2})[/.-](\d{1,2})[/.-](\d{2,4})", re.I),
    re.compile(r"(\d{1,2})[/.](\d{1,2})[/.](\d{4})\s*[-–]\s*(\d{1,2})[/.](\d{1,2})[/.](\d{4})"),
]
def norm(mo, dy, yr):
    yr = int(yr); yr = yr+2000 if yr < 100 else yr
    try: return f"{yr:04d}-{int(mo):02d}-{int(dy):02d}"
    except Exception: return None

staging = json.loads(OUT.read_text())
targets = [fid for fid, v in staging.items() if v.get("status") == "image_only_needs_tesseract"]
print(f"{len(targets)} image-only scans to OCR locally", flush=True)
svc = ing.get_services()
done = 0
for fid in targets:
    rec = staging[fid]
    try:
        buf = io.BytesIO(); dl = MediaIoBaseDownload(buf, svc["drive"].files().get_media(fileId=fid))
        d = False
        while not d: _, d = dl.next_chunk()
        doc = fitz.open(stream=buf.getvalue(), filetype="pdf")
        text = ""
        for p in list(doc)[:2]:
            pix = p.get_pixmap(dpi=200)
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tf:
                tf.write(pix.tobytes("png")); tmp = tf.name
            r = subprocess.run([TESS, tmp, "stdout", "-l", "eng", "--psm", "6"],
                               capture_output=True, text=True, timeout=60)
            text += r.stdout or ""
            os.unlink(tmp)
        dates = set()
        for rx in DATE_RES:
            for m in rx.finditer(text):
                g = m.groups()
                c = norm(g[-3], g[-2], g[-1]) if len(g) >= 3 else None
                if c and c > "2024-01-01": dates.add(c)
        rec["dates_found"] = sorted(dates)[-4:]
        rec["status"] = "tesseract_dates_found" if dates else "tesseract_no_dates"
    except Exception as e:
        rec["status"] = f"tesseract_error: {str(e)[:60]}"
    done += 1
    if done % 20 == 0:
        OUT.write_text(json.dumps(staging, indent=1)); print(f"  {done}/{len(targets)} OCR'd…", flush=True)
OUT.write_text(json.dumps(staging, indent=1))
from collections import Counter
print("PASS-2 DONE:", dict(Counter(v["status"].split(":")[0] for v in staging.values())), flush=True)
