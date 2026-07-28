#!/usr/bin/env python3
"""
GOJ Paperless Menu Extractor
─────────────────────────────
Fetches OCR'd menu PDFs from Paperless-NGX, parses Russian menu forms,
and builds GOJ_Menu_Orders.json on the Desktop.

Run: python3 ~/Desktop/REX/paperless_menu_extract.py
"""

import json, re, sys, urllib.request, urllib.error, urllib.parse
from pathlib import Path
from datetime import datetime, date
from collections import defaultdict

# ── Config ────────────────────────────────────────────────────────────────────
PAPERLESS_URL   = "http://100.99.86.60:8000"
PAPERLESS_TOKEN = "583e819be1146b96b935007c6ad7f584a3a1b1b7"
CUTOFF_DATE     = "2026-03-30"   # only menus on or after this date
WEEK_START      = "2026-03-31"   # Mon of the menu week

OUTPUT_JSON     = Path.home() / "Desktop" / "GOJ_Menu_Orders.json"
BACKUP_JSON     = Path.home() / "Desktop" / "REX" / "GOJ_Menu_Orders.json"
LOG_PATH        = Path.home() / "Desktop" / "REX" / "paperless_menu_extract_log.txt"

HEADERS = {
    "Authorization": f"Token {PAPERLESS_TOKEN}",
    "Content-Type": "application/json",
}

def api_get(path):
    url = PAPERLESS_URL + path
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        print(f"  HTTP {e.code} for {path}: {e.read()[:200]}")
        return None
    except Exception as e:
        print(f"  Error fetching {path}: {e}")
        return None

# ── Fetch all documents matching menu criteria ─────────────────────────────────
def fetch_menu_documents():
    """Return list of Paperless document objects that look like menu scans."""
    all_docs = []
    page = 1
    while True:
        data = api_get(f"/api/documents/?page_size=100&page={page}&ordering=-created")
        if not data or "results" not in data:
            break
        results = data["results"]
        if not results:
            break
        all_docs.extend(results)
        print(f"  Fetched page {page}: {len(results)} docs (total so far: {len(all_docs)})")
        if not data.get("next"):
            break
        page += 1

    # Filter to menu-relevant docs added after cutoff
    cutoff = datetime.strptime(CUTOFF_DATE, "%Y-%m-%d")
    menu_docs = []
    for doc in all_docs:
        created_str = doc.get("created") or doc.get("added") or ""
        title = (doc.get("title") or "").lower()
        # Match docs from goj3152 scanner (doc00XXXXX pattern) or menu keywords
        is_scanner_doc = bool(re.search(r'doc00\d{5}', title))
        is_menu_doc    = any(k in title for k in ["menu", "меню", "мен", "garden"])
        try:
            # Paperless dates can be "2026-03-30T..." or "2026-03-30"
            created = datetime.fromisoformat(created_str[:10])
            after_cutoff = created >= cutoff
        except:
            after_cutoff = True  # include if date unclear

        if (is_scanner_doc or is_menu_doc) and after_cutoff:
            menu_docs.append(doc)

    return all_docs, menu_docs

# ── Fetch OCR content for a document ─────────────────────────────────────────
def fetch_doc_content(doc_id):
    """Get the OCR text for a document. Tries content field first, then download."""
    # The full document details include 'content' (OCR text)
    detail = api_get(f"/api/documents/{doc_id}/")
    if detail and detail.get("content"):
        return detail["content"]
    return ""

# ── Russian menu parsing ──────────────────────────────────────────────────────
# Menu items known from GOJ Russian weekly form
SALADS = [
    "Оливье", "Мимоза", "Свекольный", "Цезарь",
    "Капустный", "Морковный", "Греческий", "Весенний",
    "Сельдь под шубой", "Винегрет",
]
SOUPS = [
    "Борщ красный", "Щи", "Куриный суп", "Гороховый",
    "Рассольник", "Суп лапша", "Рыбный суп", "Окрошка",
    "Минестроне", "Суп харчо",
]
MAINS = [
    "Котлеты куриные", "Котлеты говяжьи", "Котлеты рыбные",
    "Курица тушёная", "Говядина тушёная", "Рыба запечёная",
    "Голубцы", "Пельмени", "Вареники", "Рыба жареная",
    "Курица запечёная", "Куриные бёдра", "Куриная грудка",
]
SIDES = [
    "Гречка", "Рис", "Картошка пюре", "Картошка варёная",
    "Картошка жареная", "Макароны", "Тушёные овощи", "Перловка",
    "Картофель запечёный", "Фасоль",
]

DAYS_RU = {
    "ПН": "Mon", "ВТ": "Tue", "СР": "Wed", "ЧТ": "Thu", "ПТ": "Fri",
    "пн": "Mon", "вт": "Tue", "ср": "Wed", "чт": "Thu", "пт": "Fri",
}

def extract_name(text):
    """Extract client name from 'Имя:' line."""
    # Try Имя: Name pattern
    m = re.search(r'[Ии]мя\s*[:\-]\s*(.+)', text)
    if m:
        name = m.group(1).strip()
        # Clean up — take only first line
        name = name.split('\n')[0].strip()
        # Remove trailing junk
        name = re.sub(r'[^\w\s\-\.]', '', name).strip()
        if len(name) > 2:
            return name
    # Fallback: ФИО: pattern
    m = re.search(r'[Фф][ИиЙй][Оо]\s*[:\-]\s*(.+)', text)
    if m:
        name = m.group(1).strip().split('\n')[0].strip()
        if len(name) > 2:
            return name
    return None

def find_checked_item(text, items, col_start, col_end):
    """
    Given a text block, look for which item has a check mark (X, ✓, +, v, ×, •)
    in the column range col_start..col_end.
    This is a simplified heuristic for tabular OCR output.
    """
    # OCR often represents checked boxes as X, ✓, v, +, ×, ■, x
    CHECK_CHARS = set('Xx✓✗×+■v•√')

    lines = text.split('\n')
    for item in items:
        # Find the line containing this item
        for i, line in enumerate(lines):
            if item.lower() in line.lower():
                # Look for a check character in this line around the column position
                # Since OCR columns are approximate, scan from col_start to col_end
                segment = line[col_start:col_end] if col_end <= len(line) else line[col_start:]
                if any(c in CHECK_CHARS for c in segment):
                    return item
                # Also check next line (OCR sometimes splits)
                if i + 1 < len(lines):
                    next_line = lines[i + 1]
                    seg2 = next_line[col_start:col_end] if col_end <= len(next_line) else next_line[col_start:]
                    if any(c in CHECK_CHARS for c in seg2):
                        return item
    return None

def parse_menu_page(text):
    """
    Parse a single OCR'd menu page (Russian).
    Returns dict: {name, Mon: {salad, soup, main, side}, Tue: {...}, ...}

    Strategy: Since column positions vary by OCR quality, we use a
    frequency/proximity approach — find checkmarks near each day column header,
    then match to nearest item row.
    """
    name = extract_name(text)

    # Find column positions for each day by locating day headers
    day_positions = {}
    lines = text.split('\n')

    for i, line in enumerate(lines):
        for ru_day, en_day in DAYS_RU.items():
            if ru_day in line:
                # Approximate column position of this day
                col = line.index(ru_day)
                if en_day not in day_positions:
                    day_positions[en_day] = col

    selections = {}
    CHECK_CHARS = set('Xx✓✗×+■v•√xX')

    # For each section, find which items are checked for each day
    # We'll use a simpler approach: look at the full text for patterns like
    # "ItemName ... X ... X ..." where X positions align with day columns

    def find_selections_for_section(item_list, section_name):
        results = {day: None for day in ["Mon", "Tue", "Wed", "Thu", "Fri"]}

        for item in item_list:
            # Find all lines containing this item (case-insensitive)
            for line_idx, line in enumerate(lines):
                if item.lower() in line.lower():
                    # This line has the item name — scan rest of line for checkmarks
                    # Also look at lines i through i+2 for the checkbox row
                    check_lines = lines[line_idx:line_idx+3]
                    full = ' '.join(check_lines)

                    # Count checkmarks — if any day columns are known, match by position
                    if day_positions:
                        for day, col in sorted(day_positions.items(), key=lambda x: x[1]):
                            # Look for a check character within ±8 chars of column position
                            window_start = max(0, col - 8)
                            window_end   = col + 15
                            for cl in check_lines:
                                segment = cl[window_start:window_end] if window_end <= len(cl) else cl[window_start:]
                                if any(c in CHECK_CHARS for c in segment):
                                    if results[day] is None:
                                        results[day] = item
                    else:
                        # No column positions known — just pick first checked item
                        if any(c in CHECK_CHARS for c in full) and not any(v for v in results.values()):
                            results["Mon"] = item  # fallback
        return results

    salad_sel = find_selections_for_section(SALADS, "САЛАТЫ")
    soup_sel  = find_selections_for_section(SOUPS,  "СУПЫ")
    main_sel  = find_selections_for_section(MAINS,  "ГЛАВНОЕ БЛЮДО")
    side_sel  = find_selections_for_section(SIDES,  "ГАРНИР")

    for day in ["Mon", "Tue", "Wed", "Thu", "Fri"]:
        selections[day] = {
            "salad": salad_sel.get(day),
            "soup":  soup_sel.get(day),
            "main":  main_sel.get(day),
            "side":  side_sel.get(day),
        }

    return {"name": name, "selections": selections}

# ── Build order JSON ──────────────────────────────────────────────────────────
# Map day name → ISO date for week of 2026-03-31
WEEK_DATES = {
    "Mon": "2026-03-31",
    "Tue": "2026-04-01",
    "Wed": "2026-04-02",
    "Thu": "2026-04-03",
    "Fri": "2026-04-04",
}

def build_orders_json(client_menus):
    """Convert list of {name, selections} to GOJ_Menu_Orders.json format."""
    orders = {}
    for day, iso_date in WEEK_DATES.items():
        key = f"{iso_date}_S1"
        day_orders = []
        for client in client_menus:
            sel = client["selections"].get(day, {})
            if any(v for v in sel.values()):  # at least one item selected
                day_orders.append({
                    "name":  client["name"] or "UNKNOWN",
                    "salad": sel.get("salad") or "",
                    "soup":  sel.get("soup")  or "",
                    "main":  sel.get("main")  or "",
                    "side":  sel.get("side")  or "",
                })
        orders[key] = {
            "date":   iso_date,
            "shift":  1,
            "orders": day_orders,
        }
    return orders

# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    log_lines = []
    def log(msg):
        print(msg)
        log_lines.append(msg)

    log("=" * 60)
    log(f"GOJ Paperless Menu Extractor — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    log("=" * 60)

    # 1. Fetch documents
    log("\n[1] Fetching all documents from Paperless...")
    all_docs, menu_docs = fetch_menu_documents()
    log(f"    Total docs in Paperless: {len(all_docs)}")
    log(f"    Menu-related docs (after {CUTOFF_DATE}): {len(menu_docs)}")

    if not menu_docs:
        log("\n  ⚠️  No menu documents found! Showing all recent docs for inspection:")
        for doc in all_docs[:20]:
            log(f"    [{doc['id']}] {doc.get('created','?')[:10]} — {doc.get('title','(no title)')}")
        # Save diagnostic info
        diag = {"all_docs_sample": all_docs[:30], "total": len(all_docs)}
        Path(Path.home() / "Desktop" / "REX" / "paperless_diag.json").write_text(json.dumps(diag, indent=2, ensure_ascii=False))
        log("\n  Diagnostic saved to ~/Desktop/REX/paperless_diag.json")
        log("  STOPPING — check the diagnostic file and re-run with corrected filters.")
        Path(LOG_PATH).write_text('\n'.join(log_lines))
        return

    # 2. Fetch OCR text for each document
    log(f"\n[2] Fetching OCR content for {len(menu_docs)} documents...")
    all_texts = []
    for doc in menu_docs:
        doc_id    = doc["id"]
        doc_title = doc.get("title", f"doc_{doc_id}")
        log(f"    → [{doc_id}] {doc_title[:60]}")
        content = fetch_doc_content(doc_id)
        if content:
            log(f"       OCR text: {len(content)} chars")
            all_texts.append({"doc_id": doc_id, "title": doc_title, "content": content})
        else:
            log(f"       ⚠️  No OCR content found")

    # Save raw OCR for inspection
    raw_ocr_path = Path.home() / "Desktop" / "REX" / "paperless_raw_ocr.json"
    raw_ocr_path.write_text(json.dumps(all_texts, indent=2, ensure_ascii=False))
    log(f"\n    Raw OCR saved to {raw_ocr_path}")

    # Show sample from first document
    if all_texts:
        log("\n[SAMPLE OCR — first 2000 chars of doc 1]")
        log("-" * 50)
        log(all_texts[0]["content"][:2000])
        log("-" * 50)

    # 3. Parse menus — split multi-client documents by "Имя:" occurrences
    log(f"\n[3] Parsing menu forms...")
    client_menus = []
    ocr_failures = 0

    for doc_data in all_texts:
        content = doc_data["content"]
        # Split on "Имя:" to separate individual client forms
        # Each 2-page form starts with client name
        # Split on name marker — try a few variants
        splits = re.split(r'(?=\bИмя\s*[:\-])', content)
        if len(splits) <= 1:
            splits = re.split(r'(?=\bФИО\s*[:\-])', content)
        if len(splits) <= 1:
            splits = [content]  # treat whole doc as one form

        log(f"    Doc [{doc_data['doc_id']}]: {len(splits)} client form(s) found")

        for form_text in splits:
            if len(form_text.strip()) < 50:
                continue
            parsed = parse_menu_page(form_text)
            if parsed["name"]:
                client_menus.append(parsed)
            else:
                ocr_failures += 1
                log(f"      ⚠️  Could not extract name from form (first 100 chars): {form_text[:100]!r}")

    log(f"\n    ✅  Successfully parsed: {len(client_menus)} client menus")
    log(f"    ❌  Parse failures (no name found): {ocr_failures}")

    # Save individual parsed menus for inspection
    parsed_path = Path.home() / "Desktop" / "REX" / "paperless_parsed_menus.json"
    parsed_path.write_text(json.dumps(client_menus, indent=2, ensure_ascii=False))
    log(f"    Parsed menus saved to {parsed_path}")

    # Show 5 sample clients
    log("\n[SAMPLE — first 5 clients]")
    for c in client_menus[:5]:
        log(f"  {c['name']}: {json.dumps(c['selections'], ensure_ascii=False)}")

    # 4. Build output JSON
    log("\n[4] Building GOJ_Menu_Orders.json...")
    orders = build_orders_json(client_menus)
    output_str = json.dumps(orders, indent=2, ensure_ascii=False)

    OUTPUT_JSON.write_text(output_str)
    BACKUP_JSON.parent.mkdir(parents=True, exist_ok=True)
    BACKUP_JSON.write_text(output_str)

    log(f"\n    ✅  Saved to: {OUTPUT_JSON}")
    log(f"    ✅  Backup to: {BACKUP_JSON}")

    # Summary
    log("\n" + "=" * 60)
    log("SUMMARY")
    log("=" * 60)
    log(f"  PDFs found in Paperless:    {len(menu_docs)}")
    log(f"  Client menus extracted:     {len(client_menus)}")
    log(f"  Parse failures:             {ocr_failures}")
    log(f"  Days covered:               Mon–Fri (2026-03-31 to 2026-04-04)")
    total_orders = sum(len(v["orders"]) for v in orders.values())
    log(f"  Total daily orders written: {total_orders}")

    # Save log
    Path(LOG_PATH).write_text('\n'.join(log_lines))
    log(f"\nLog saved to {LOG_PATH}")
    log("\n✅ DONE")

if __name__ == "__main__":
    main()
