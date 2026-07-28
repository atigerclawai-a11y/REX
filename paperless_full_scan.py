#!/usr/bin/env python3
"""
Paperless Full Scan — finds ALL documents containing GARDEN OF JOY menu text,
regardless of date. Downloads OCR for each and counts forms.
"""
import json, re, urllib.request, urllib.error, urllib.parse, datetime
from pathlib import Path

PAPERLESS_URL   = "http://localhost:8010"
PAPERLESS_TOKEN = "51420bd5c9d61208b331d09a528019d50a70520b"
HEADERS = {"Authorization": f"Token {PAPERLESS_TOKEN}"}
OUT_OCR  = Path.home() / "Desktop" / "REX" / "paperless_all_menu_ocr.json"
OUT_RPT  = Path.home() / "Desktop" / "REX" / "paperless_full_scan_report.txt"

def api_get(path):
    req = urllib.request.Request(PAPERLESS_URL + path, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=45) as r:
            return json.loads(r.read())
    except Exception as e:
        print(f"  ERROR {path}: {e}")
        return None

# ── 1. Use Paperless full-text search for "GARDEN OF JOY" ────────────────────
print("Searching Paperless for 'GARDEN OF JOY'...")
search_results = []
page = 1
while True:
    query = urllib.parse.quote("GARDEN OF JOY")
    data = api_get(f"/api/documents/?page_size=100&page={page}&query={query}&ordering=-created")
    if not data or not data.get("results"):
        break
    search_results.extend(data["results"])
    print(f"  Page {page}: {len(data['results'])} results (total {len(search_results)})")
    if not data.get("next"):
        break
    page += 1

print(f"\nTotal docs matching 'GARDEN OF JOY': {len(search_results)}\n")

# ── 2. For each, fetch full OCR content ───────────────────────────────────────
menu_docs = []
for doc in search_results:
    doc_id  = doc['id']
    title   = doc.get('title', '')
    fname   = doc.get('original_file_name', '')
    created = (doc.get('created') or '')[:10]

    detail  = api_get(f"/api/documents/{doc_id}/")
    content = (detail.get('content') or '') if detail else ''

    # Count forms = split on GARDEN OF JOY ADULT DAYCARE
    forms = re.split(r'GARDEN OF JOY ADULT DAYCARE', content)
    forms = [f for f in forms if len(f.strip()) > 80]

    menu_docs.append({
        "doc_id":   doc_id,
        "title":    title,
        "filename": fname,
        "created":  created,
        "content_len": len(content),
        "form_count": len(forms),
        "content":  content,
    })
    print(f"  [{doc_id:4d}] {created}  forms={len(forms):3d}  chars={len(content):6d}  {title[:50]}")

# ── 3. Save combined OCR ───────────────────────────────────────────────────────
OUT_OCR.write_text(json.dumps(menu_docs, indent=2, ensure_ascii=False))

total_chars = sum(d['content_len'] for d in menu_docs)
total_forms = sum(d['form_count'] for d in menu_docs)

rpt = [
    f"Paperless Full Scan Report — {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}",
    f"{'='*60}",
    f"Documents found: {len(menu_docs)}",
    f"Total OCR chars: {total_chars:,}",
    f"Total forms (splits): {total_forms}",
    f"",
    f"Per-document breakdown:",
]
for d in menu_docs:
    rpt.append(f"  [{d['doc_id']:4d}] {d['created']}  forms={d['form_count']:3d}  "
               f"chars={d['content_len']:6d}  {d['title'][:50]}")
rpt.append(f"\nOCR data saved to: {OUT_OCR}")
OUT_RPT.write_text('\n'.join(rpt))

print(f"\n{'='*50}")
print(f"TOTAL docs:  {len(menu_docs)}")
print(f"TOTAL forms: {total_forms}")
print(f"TOTAL chars: {total_chars:,}")
print(f"\nReport saved to {OUT_RPT}")
print(f"OCR data  saved to {OUT_OCR}")
print(f"\nDone.")
