"""
paperless_version_check.py
==========================
Checks the Paperless-NGX version and lists what bulk_edit methods
and API features are available on this installation.

Run:
    cd ~/Desktop/REX && source .venv/bin/activate
    python paperless_version_check.py
"""

import json
import urllib.request
import urllib.error
import sys

PAPERLESS_URL   = "http://100.99.86.60:8000"
PAPERLESS_TOKEN = "583e819be1146b96b935007c6ad7f584a3a1b1b7"
HEADERS = {"Authorization": f"Token {PAPERLESS_TOKEN}"}


def get(path):
    url = f"{PAPERLESS_URL}/api/{path.lstrip('/')}"
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read()), r.status
    except urllib.error.HTTPError as e:
        return {"error": e.read().decode()[:200]}, e.code
    except urllib.error.URLError as e:
        print(f"❌  Cannot reach Paperless: {e}")
        sys.exit(1)


def options(path):
    """HTTP OPTIONS to discover what methods/fields are allowed."""
    url = f"{PAPERLESS_URL}/api/{path.lstrip('/')}"
    req = urllib.request.Request(url, headers=HEADERS, method="OPTIONS")
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read()), r.status
    except urllib.error.HTTPError as e:
        return {"error": e.read().decode()[:400]}, e.code
    except Exception:
        return {}, 0


print("=" * 55)
print("  Paperless-NGX Version & Feature Check")
print(f"  {PAPERLESS_URL}")
print("=" * 55)

# ── Version ──────────────────────────────────────────────
data, status = get("")
if status == 200:
    version = data.get("version", "unknown")
    print(f"\n  Version:  {version}")
    for k, v in data.items():
        if k not in ("version",):
            print(f"  {k}: {v}")
else:
    print(f"\n  ❌  Could not read root API (status {status}): {data}")

# ── Discover valid bulk_edit methods ─────────────────────
print("\n🔍  Checking valid bulk_edit methods via OPTIONS...")
opts, ostatus = options("documents/bulk_edit/")
if ostatus == 200 and opts:
    # Django REST Framework returns actions in OPTIONS response
    actions = opts.get("actions", {})
    post_fields = actions.get("POST", {})
    method_field = post_fields.get("method", {})
    choices = method_field.get("choices", [])
    if choices:
        print(f"\n  ✅  Valid bulk_edit methods on this installation:")
        for c in choices:
            val = c.get("value", c) if isinstance(c, dict) else c
            print(f"      • {val}")
    else:
        print(f"  ⚠️   Could not read method choices from OPTIONS response.")
        print(f"       Raw: {json.dumps(opts)[:300]}")
else:
    print(f"  ⚠️   OPTIONS returned {ostatus}: {opts.get('error','')[:100]}")

# ── Check if admin tasks endpoint exists ──────────────────
print("\n🔍  Checking admin endpoints...")
for ep in ["tasks/", "config/", "ui_settings/", "statistics/"]:
    d, s = get(ep)
    icon = "✅" if s == 200 else "❌"
    summary = str(list(d.keys()))[:60] if s == 200 and isinstance(d, dict) else str(d)[:60]
    print(f"  {icon}  /api/{ep}  →  {s}  {summary}")

# ── Doc count by type ─────────────────────────────────────
print("\n📊  Document overview:")
d, s = get("documents/?page_size=1")
if s == 200:
    print(f"      Total documents: {d.get('count', '?')}")
d, s = get("tags/")
if s == 200:
    tags = d.get("results", [])
    print(f"      Tags: {[t['name'] for t in tags[:15]]}")

print()
print("=" * 55)
print("  Re-OCR Options for This Version")
print("=" * 55)
print("""
  OPTION 1 — Paperless Web UI (always works):
    1. Open http://100.99.86.60:8000
    2. Click Documents in the left sidebar
    3. Click the ☰ (filter) icon → filter by Tag = GOJ or Menu
    4. Click the checkbox at the top to select all
    5. Click "Actions" dropdown at the top
    6. Look for "Redo OCR" — click it if present

  OPTION 2 — Upgrade Paperless-NGX:
    Redo OCR via API was added in Paperless-NGX v2.x.
    If your docker-compose.yml pins an older version, update it:
      image: ghcr.io/paperless-ngx/paperless-ngx:latest
    Then: docker-compose pull && docker-compose up -d

  OPTION 3 — Consume folder drop (re-uploads PDF with new OCR):
    Download a PDF from Paperless, drop it in the consume folder,
    Paperless will re-process with current OCR settings.
    Consume folder is usually: /paperless/consume/ inside Docker.

  MEANWHILE — Run the menu processor now:
    The docs already have OCR text (in English). The processor
    can still match many client names even without Russian OCR.
    Run: python goj_menu_ocr_processor.py
""")
