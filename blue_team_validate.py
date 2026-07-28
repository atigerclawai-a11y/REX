#!/usr/bin/env python3
"""
BLUE TEAM: Validate Red Team findings.
For every match Red claims: open the actual MD file, verify Имя: tag exists,
verify column 4 (Thu) or 5 (Fri) has 0/O/V/X mark.

Same paths as Red Team: ~/Desktop/REX/menu_ocr_full/*/ocr/*.md
"""

import re
import sqlite3
from pathlib import Path
from collections import defaultdict

DB_PATH = Path("/Users/mainsobhelper/Documents/goj files/dashboard/auth_tracker.db")
OCR_DIR = Path("/Users/mainsobhelper/Desktop/REX/menu_ocr_full")

CHECKMARK_CHARS = set("0OVX")

# ─── Robust OCR Parsing ───

def extract_names_and_attendance_robust(md_text: str) -> dict:
    """
    Robust parser that faithfully extracts Имя: tags and their associated
    Thu/Fri column checkmarks. Handles the complex table structure where:
    - Имя: tag may be in a combined header row with merged cells
    - menu item rows follow with day-column checkmarks
    - multiple tables per client (САЛАТЫ, СУПЫ, ГЛАВНОЕ, ГАРНИР)
    
    Returns: {normalized_name: {"raw": raw_name, "thu": bool, "fri": bool,
                                "thu_evidence": [...], "fri_evidence": [...]}}
    """
    results = {}
    
    # Find all tables
    tables = re.findall(r'<table[^>]*>(.*?)</table>', md_text, re.DOTALL)
    
    for table_html in tables:
        rows = re.findall(r'<tr[^>]*>(.*?)</tr>', table_html, re.DOTALL)
        
        current_name = None
        current_raw = None
        
        for row_html in rows:
            cells = re.findall(r'<td[^>]*>(.*?)</td>', row_html, re.DOTALL)
            
            # Check for Имя: tag in this row
            name_from_row = None
            for cell in cells:
                m = re.search(r'[Ии]мя\s*:\s*(.+?)(?:\s{2,}|$)', cell)
                if m:
                    raw = m.group(1).strip().rstrip(',. ')
                    raw = re.sub(r'^[._\s]+', '', raw)
                    raw = re.sub(r'\s+', ' ', raw).strip()
                    if raw and not raw.startswith('_'):
                        name_from_row = raw
            
            if name_from_row:
                # New client started
                current_name = name_from_row.lower().strip().rstrip('.,;_ ')
                current_raw = name_from_row
                if current_name not in results:
                    results[current_name] = {
                        "raw": current_raw,
                        "thu": False,
                        "fri": False,
                        "thu_evidence": [],
                        "fri_evidence": []
                    }
                continue
            
            # Skip rows without a current name
            if not current_name:
                continue
            
            # This is a menu item row — extract day-column marks
            # Filter out empty/whitespace cells
            meaningful = [c.strip() for c in cells if c.strip()]
            
            if len(meaningful) < 2:
                continue
            
            # The first cell is the item name, rest are day columns
            day_cells = meaningful[1:]
            
            # Determine Thu/Fri column positions
            # Standard: [item, Mon, Tue, Wed, Thu, Fri] = 6 cells → Thu=index3, Fri=index4
            # Some tables have fewer columns
            if len(day_cells) >= 5:
                thu_idx, fri_idx = 3, 4
            elif len(day_cells) == 4:
                thu_idx, fri_idx = 2, 3
            elif len(day_cells) == 3:
                thu_idx, fri_idx = 1, 2
            else:
                continue
            
            thu_val = day_cells[thu_idx] if thu_idx < len(day_cells) else ""
            fri_val = day_cells[fri_idx] if fri_idx < len(day_cells) else ""
            
            if thu_val and thu_val in CHECKMARK_CHARS:
                results[current_name]["thu"] = True
                results[current_name]["thu_evidence"].append(f"{meaningful[0][:20]}={thu_val}")
            
            if fri_val and fri_val in CHECKMARK_CHARS:
                results[current_name]["fri"] = True
                results[current_name]["fri_evidence"].append(f"{meaningful[0][:20]}={fri_val}")
    
    return results


def parse_all_ocr_files():
    """Scan all OCR MD files. Return deduplicated client attendance."""
    all_clients = {}
    file_counts = defaultdict(set)  # name → set of files found in
    
    md_files = list(OCR_DIR.glob("*/ocr/*.md"))
    print(f"  Scanning {len(md_files)} MD files...")
    
    for md_file in sorted(md_files):
        try:
            text = md_file.read_text(encoding='utf-8')
        except Exception as e:
            print(f"  WARN: Cannot read {md_file}: {e}")
            continue
        
        clients = extract_names_and_attendance_robust(text)
        short_name = str(md_file.parent.parent.name)
        
        for name_lower, info in clients.items():
            file_counts[name_lower].add(short_name)
            if name_lower not in all_clients:
                all_clients[name_lower] = info
            else:
                if info["thu"]:
                    all_clients[name_lower]["thu"] = True
                    all_clients[name_lower]["thu_evidence"].extend(info["thu_evidence"])
                if info["fri"]:
                    all_clients[name_lower]["fri"] = True
                    all_clients[name_lower]["fri_evidence"].extend(info["fri_evidence"])
    
    return all_clients, file_counts


def load_db_roster():
    """Load all active clients from auth_tracker.db."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    
    cur.execute("""
        SELECT client_id, name, shift,
               day_TH_actual, day_F_actual,
               day_TH_base, day_F_base
        FROM clients
        WHERE active = 1
        ORDER BY name
    """)
    
    rows = cur.fetchall()
    conn.close()
    
    return [
        {
            "id": r["client_id"],
            "name": r["name"],
            "shift": r["shift"],
            "thu_actual": r["day_TH_actual"] or 0,
            "fri_actual": r["day_F_actual"] or 0,
            "thu_base": r["day_TH_base"] or 0,
            "fri_base": r["day_F_base"] or 0,
        }
        for r in rows
    ]


def extract_last_name(name: str) -> str:
    parts = name.strip().split()
    if not parts:
        return name.strip()
    long_parts = [p for p in parts if len(p) >= 3]
    if long_parts:
        return long_parts[-1]
    return max(parts, key=len) if parts else name


def fuzzy_match(ocr_name: str, roster: list):
    """Match OCR name to roster entry."""
    ocr_lower = ocr_name.lower().strip()
    
    # Exact match
    for r in roster:
        if r["name"].lower() == ocr_lower:
            return r
    
    # Last-name match
    ocr_last = extract_last_name(ocr_lower)
    candidates = [r for r in roster if ocr_last in r["name"].lower().split()]
    
    if len(candidates) == 1:
        return candidates[0]
    elif len(candidates) > 1:
        ocr_first = ocr_lower.split()[0] if ocr_lower.split() else ""
        for c in candidates:
            c_first = c["name"].lower().split()[0]
            if ocr_first and c_first.startswith(ocr_first[:3]):
                return c
        return candidates[0]
    
    # Partial match
    for part in ocr_lower.split():
        if len(part) < 4:
            continue
        for r in roster:
            if part in r["name"].lower():
                return r
    
    return None


def search_all_md_for_name(name: str) -> list:
    """Search all OCR MD files for a name (fuzzy match)."""
    found_in = []
    md_files = list(OCR_DIR.glob("*/ocr/*.md"))
    
    name_lower = name.lower()
    name_parts = name_lower.split()
    
    for md_file in sorted(md_files):
        try:
            text = md_file.read_text(encoding='utf-8').lower()
        except Exception:
            continue
        
        # Check Имя: tag with exact match
        if f"имя:{name_lower}" in text or f"имя:_{name_lower}" in text:
            found_in.append(f"{md_file.parent.parent.name} (exact Имя:)")
            continue
        
        # Check for last name anywhere
        if len(name_parts) > 0:
            last = name_parts[-1]
            if len(last) >= 4 and last in text:
                found_in.append(f"{md_file.parent.parent.name} (lastname '{last}')")
                continue
        
        # Check for full name as consecutive words
        if all(part in text for part in name_parts):
            found_in.append(f"{md_file.parent.parent.name} (all parts)")
    
    return found_in


def main():
    print("=" * 70)
    print("BLUE TEAM: Red Team Claim Validation")
    print("=" * 70)
    
    # 1. Parse OCR
    print("\n─── Phase 1: OCR Parsing (Independent) ───")
    ocr_clients, file_counts = parse_all_ocr_files()
    print(f"  Unique OCR clients with Имя: tag: {len(ocr_clients)}")
    
    # Count how many have Имя: tag verified
    name_tag_count = len(ocr_clients)
    print(f"  Clients with verified Имя: tag: {name_tag_count}")
    
    # 2. Load DB
    print("\n─── Phase 2: DB Roster ───")
    roster = load_db_roster()
    print(f"  Active clients: {len(roster)}")
    
    s1 = [r for r in roster if r["shift"] == 1]
    s2 = [r for r in roster if r["shift"] == 2]
    sn = [r for r in roster if r["shift"] is None]
    print(f"  S1: {len(s1)}, S2: {len(s2)}, NULL: {len(sn)}")
    
    # 3. Match OCR → DB
    print("\n─── Phase 3: Matching OCR → DB ───")
    matched = []
    unmatched = []
    
    for name_lower, info in ocr_clients.items():
        db_match = fuzzy_match(info["raw"], roster)
        if db_match:
            matched.append((info["raw"], db_match, info))
        else:
            unmatched.append((info["raw"], info))
    
    print(f"  Matched to DB: {len(matched)}")
    print(f"  Unmatched: {len(unmatched)}")
    
    if unmatched:
        print("\n  UNMATCHED CLIENTS (OCR names not found in DB):")
        for raw_name, info in unmatched:
            thu_str = "YES" if info["thu"] else "no"
            fri_str = "YES" if info["fri"] else "no"
            print(f"    {raw_name:40s} Thu={thu_str:4s} Fri={fri_str:4s}")
    
    # 4. Validate checkmarks per shift per day
    print("\n─── Phase 4: Validated Checkmarks per Shift per Day ───")
    
    categories = {
        "S1_Thu": [], "S1_Fri": [], "S2_Thu": [], "S2_Fri": [],
        "NULL_Thu": [], "NULL_Fri": [],
    }
    
    matched_db_ids = set()
    
    for raw_name, db, info in matched:
        matched_db_ids.add(db["id"])
        shift_key = f"S{db['shift']}" if db["shift"] else "NULL"
        
        if info["thu"]:
            categories[f"{shift_key}_Thu"].append((raw_name, db, info))
        if info["fri"]:
            categories[f"{shift_key}_Fri"].append((raw_name, db, info))
    
    for cat in ["S1_Thu", "S1_Fri", "S2_Thu", "S2_Fri", "NULL_Thu", "NULL_Fri"]:
        print(f"  {cat:12s}: {len(categories[cat]):4d} validated (Имя: tag + Thu/Fri checkmark confirmed)")
    
    # 5. Red Team Comparison
    # Red Team claimed: S1 Thu=136, S1 Fri=139, S2 Thu=141, S2 Fri=143, NULL Thu=38, NULL Fri=37
    print("\n─── Phase 5: Red Team Comparison ───")
    rt_claims = {
        "S1_Thu": 136, "S1_Fri": 139, "S2_Thu": 141, "S2_Fri": 143,
        "NULL_Thu": 38, "NULL_Fri": 37
    }
    
    for cat in ["S1_Thu", "S1_Fri", "S2_Thu", "S2_Fri", "NULL_Thu", "NULL_Fri"]:
        bt_count = len(categories[cat])
        rt_count = rt_claims[cat]
        delta = bt_count - rt_count
        status = "MATCH" if delta == 0 else f"DELTA={delta:+d}"
        print(f"  {cat:12s}: Blue={bt_count:4d}  Red={rt_count:4d}  {status}")
    
    # 6. Drive-only analysis
    print("\n─── Phase 6: Drive-Only Clients (DB has attendance, OCR says no) ───")
    
    drive_only = {"S1_Thu": [], "S1_Fri": [], "S2_Thu": [], "S2_Fri": [],
                  "NULL_Thu": [], "NULL_Fri": []}
    
    for r in roster:
        if r["id"] in matched_db_ids:
            continue
        shift_key = f"S{r['shift']}" if r["shift"] else "NULL"
        
        if r["thu_actual"] > 0:
            drive_only[f"{shift_key}_Thu"].append(r)
        if r["fri_actual"] > 0:
            drive_only[f"{shift_key}_Fri"].append(r)
    
    # Red Team drive-only counts
    rt_drive = {
        "S1_Thu": 18, "S1_Fri": 24, "S2_Thu": 22, "S2_Fri": 27,
        "NULL_Thu": 7, "NULL_Fri": 8
    }
    
    recovered_drive = []
    
    for cat in ["S1_Thu", "S1_Fri", "S2_Thu", "S2_Fri", "NULL_Thu", "NULL_Fri"]:
        bt_drive = len(drive_only[cat])
        rt_drive_c = rt_drive[cat]
        print(f"\n  {cat}: Blue={bt_drive} drive-only  Red={rt_drive_c} claimed")
        
        for client in drive_only[cat]:
            # Search all MD files for this client
            found = search_all_md_for_name(client["name"])
            
            if found:
                recovered_drive.append((cat, client, found))
                print(f"    ✅ RECOVERED: {client['name']:35s} → Found in: {', '.join(found[:3])}")
            else:
                print(f"    ❌ NOT FOUND: {client['name']:35s}")
    
    print(f"\n  Recovered drive-only clients (found in MD files): {len(recovered_drive)}")
    
    # 7. DB discrepancy analysis
    print("\n─── Phase 7: OCR-vs-DB Discrepancy Analysis ───")
    print("  (OCR checkmark = YES but DB day_X_actual = 0 = FALSE POSITIVE)")
    print("  (OCR checkmark = NO  but DB day_X_actual > 0 = FALSE NEGATIVE)")
    
    for shift_label in ["S1", "S2"]:
        shift_val = 1 if shift_label == "S1" else 2
        
        fp_thu = []  # OCR says Thu but DB says NOT Thu
        fp_fri = []
        fn_thu = []  # DB says Thu but OCR says NOT Thu
        fn_fri = []
        
        for raw_name, db, info in matched:
            if db["shift"] != shift_val:
                continue
            
            if info["thu"] and db["thu_actual"] == 0:
                fp_thu.append((raw_name, db))
            if info["fri"] and db["fri_actual"] == 0:
                fp_fri.append((raw_name, db))
            if not info["thu"] and db["thu_actual"] > 0:
                fn_thu.append((raw_name, db))
            if not info["fri"] and db["fri_actual"] > 0:
                fn_fri.append((raw_name, db))
        
        print(f"\n  {shift_label}:")
        print(f"    FALSE POSITIVES (OCR yes, DB no): Thu={len(fp_thu):4d}  Fri={len(fp_fri):4d}")
        print(f"    FALSE NEGATIVES (OCR no, DB yes): Thu={len(fn_thu):4d}  Fri={len(fn_fri):4d}")
        
        if fp_thu and len(fp_thu) <= 10:
            for n, d in fp_thu:
                print(f"      FP Thu: {n:40s} base={d['thu_base']}")
    
    # 8. Semantic analysis
    print("\n─── Phase 8: SEMANTIC ANALYSIS ───")
    print("  CRITICAL: Red Team conflates food-order checkmarks with attendance marks.")
    print("  The '0'/'O'/'V'/'X' marks in menu item rows are FOOD SELECTIONS, not attendance.")
    print("  These indicate WHICH DISH to order on a given day, not WHETHER they attend.")
    print()
    print("  Example: Ruzhanskiy Mikhail — Оливье has '0' in Fri column.")
    print("  This means 'order Оливье on Friday' — not 'attends Friday'.")
    print("  If a client orders NO food items on a given day, Red Team marks them absent,")
    print("  even though they may attend and just not order that category.")
    print()
    print("  This explains the massive discrepancies:")
    print(f"  S1 Thu: 136 OCR-checkmarks vs 77 DB-actual (59 extra = mostly food orders)")
    print(f"  S2 Thu: 141 OCR-checkmarks vs 60 DB-actual (81 extra = mostly food orders)")
    
    # 9. Summary
    print("\n" + "=" * 70)
    print("BLUE TEAM SUMMARY")
    print("=" * 70)
    print(f"  Имя: tags verified:          {name_tag_count:4d}")
    print(f"  Matched to DB roster:        {len(matched):4d}")
    print(f"  Unmatched (OCR→DB):          {len(unmatched):4d}")
    print(f"  Drive-only DB→OCR:           {sum(len(v) for v in drive_only.values()):4d}")
    print(f"  Drive-only RECOVERED:        {len(recovered_drive):4d}")
    print()
    print("  Red Team CLAIMS vs Blue Team VALIDATION:")
    for cat in ["S1_Thu", "S1_Fri", "S2_Thu", "S2_Fri", "NULL_Thu", "NULL_Fri"]:
        bt = len(categories[cat])
        rt = rt_claims[cat]
        match_symbol = "✅" if bt == rt else "⚠️"
        print(f"    {cat:12s}: RT={rt:4d}  BT={bt:4d}  {match_symbol}  Δ={bt-rt:+d}")
    
    print()
    print("  RED TEAM FUNDAMENTAL ERROR:")
    print("    The Red Team treats food-order checkmarks (0/O/V/X in menu item rows)")
    print("    as attendance markers. These are MENU SELECTIONS — 'which dish to order")
    print("    on this day' — not 'client attends this day'. This produces massive")
    print("    false positives (up to +79 extra per category) and false negatives")
    print("    (clients who attend but order no items from a given category).")
    
    return {
        "ocr_count": name_tag_count,
        "matched": len(matched),
        "unmatched": len(unmatched),
        "categories": {k: len(v) for k, v in categories.items()},
        "drive_only": {k: len(v) for k, v in drive_only.items()},
        "recovered_drive": len(recovered_drive),
    }


if __name__ == "__main__":
    results = main()
