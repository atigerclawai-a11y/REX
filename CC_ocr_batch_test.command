#!/bin/bash
set -e
LOG_DIR="$HOME/Desktop/REX/logs"
mkdir -p "$LOG_DIR"
LOG="$LOG_DIR/ocr_batch_test_$(date +%Y%m%d_%H%M%S).log"
exec > >(tee "$LOG") 2>&1

echo "=== Full 4-Engine OCR Batch Test — $(date) ==="
echo ""

source ~/debate-chamber/.venv/bin/activate

# Step 1: Check Drive scope — exit with message if not ready
python3 - <<'PYEOF'
import json, sys
from pathlib import Path
p = Path.home() / '.rex_google_token.json'
if not p.exists():
    print("❌ ~/.rex_google_token.json not found. Run CC_google_oauth_fix.command first.")
    sys.exit(1)
token = json.loads(p.read_text())
scopes = token.get('scopes', [])
if 'https://www.googleapis.com/auth/drive.file' not in scopes:
    print(f"❌ Drive token scope is: {scopes}")
    print("Missing drive.file — run CC_google_oauth_fix.command, then re-run this test.")
    sys.exit(1)
print(f"✅ Drive token OK — scopes: {scopes}")
PYEOF

# Step 2: Engine health check (quick)
echo ""
echo "=== Engine Health ==="
tesseract --version 2>&1 | head -1
tesseract --list-langs 2>&1 | grep -E "rus|eng" | tr '\n' ' '
echo ""
curl -s -o /dev/null -w "Paperless API: HTTP %{http_code}\n" \
  -H "Authorization: Token 204f4af0226532176058cd174abec7a73311728a" \
  http://localhost:8010/api/
python3 -c "
import os, json
from pathlib import Path
cfg = Path.home() / '.rex' / 'config.json'
if cfg.exists():
    key = json.loads(cfg.read_text()).get('anthropic_api_key','')
    print(f'Claude Vision key: {key[:8]}... OK' if key else 'Claude Vision key: MISSING')
"

# Step 3: Run process_signin_sheet on all sign-in PDFs
echo ""
echo "=== Sign-in Sheet Batch OCR ==="
python3 - <<'PYEOF'
import sys, json, logging
from pathlib import Path
logging.basicConfig(level=logging.WARNING)
sys.path.insert(0, str(Path.home() / 'Desktop' / 'REX'))
from CC_signin_ocr import process_signin_sheet

# Collect all sign-in PDFs (samples + full pull)
search_dirs = [
    Path.home() / 'Desktop' / 'REX' / 'signin_samples',
    Path.home() / 'Desktop' / 'REX' / 'signin_all_pdfs',
]
pdfs = []
for d in search_dirs:
    if d.exists():
        pdfs.extend(sorted(d.glob('*.pdf')))

# Deduplicate by filename stem
seen = set()
unique_pdfs = []
for p in pdfs:
    if p.stem not in seen:
        seen.add(p.stem)
        unique_pdfs.append(p)

print(f"Found {len(unique_pdfs)} unique sign-in PDFs\n")

total_rows = total_matched = total_signed = 0
failed = []
results = []

for pdf in unique_pdfs:
    print(f"  {pdf.name[:60]}", end=' ', flush=True)
    try:
        stats = process_signin_sheet(pdf)
        rows    = stats.get('rows_detected', 0)
        matched = stats.get('matched', 0)
        signed  = stats.get('signed', 0)
        pct = int(100 * matched / rows) if rows else 0
        print(f"→ rows={rows} matched={matched} ({pct}%) signed={signed}")
        total_rows += rows; total_matched += matched; total_signed += signed
        results.append({'pdf': pdf.name, 'rows': rows, 'matched': matched, 'pct': pct, 'signed': signed})
    except Exception as e:
        print(f"→ FAILED: {e}")
        failed.append(pdf.name)

overall = int(100 * total_matched / total_rows) if total_rows else 0
print(f"\n{'='*50}")
print(f"PDFs processed: {len(unique_pdfs) - len(failed)}")
print(f"PDFs failed:    {len(failed)}")
print(f"Total rows:     {total_rows}")
print(f"Total matched:  {total_matched} ({overall}%)")
print(f"Total signed:   {total_signed}")

# Save report
report = {
    'run_at': __import__('datetime').datetime.now().isoformat(),
    'pdfs_processed': len(unique_pdfs) - len(failed),
    'pdfs_failed': len(failed),
    'total_rows': total_rows,
    'total_matched': total_matched,
    'match_pct': overall,
    'total_signed': total_signed,
    'results': results,
    'failed': failed
}
out = Path.home() / 'Desktop' / 'REX' / 'logs' / 'ocr_batch_test_latest.json'
out.write_text(__import__('json').dumps(report, indent=2))
print(f"\nReport saved: {out}")
PYEOF

echo ""
echo "=== Done — $(date) ==="
echo "Log: $LOG"
