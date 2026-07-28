#!/usr/bin/env python3
"""
CC_menu_checkmark_detector.py
Hybrid OCR: MinerU text + Tesseract checkmark detection + auth_tracker cross-ref
"""

import re, json, sys, sqlite3, subprocess
from pathlib import Path
from collections import defaultdict

HOME = Path.home()

# ── 1. Checkmark Detection ──────────────────────────────────────────────

def has_checkmark(image_path, bbox=None):
    """
    Detect if a cropped cell contains a checkmark/circle.
    Uses pixel density analysis: checked cells have significantly more
    dark pixels than empty cells.
    """
    try:
        from PIL import Image
        img = Image.open(image_path)
        if bbox:
            img = img.crop(bbox)
        
        # Convert to grayscale and threshold
        gray = img.convert('L')
        pixels = list(gray.getdata())
        
        # Count dark pixels (value < 128 = dark)
        total = len(pixels)
        dark = sum(1 for p in pixels if p < 140)
        
        # If >10% of pixels are dark, likely a mark
        ratio = dark / total if total > 0 else 0
        return ratio > 0.08, ratio
        
    except Exception as e:
        return False, 0

# ── 2. Menu Table Parser ────────────────────────────────────────────────

def find_menu_grid(md_path, page_images_dir):
    """
    For a MinerU MD file, locate menu tables and detect checkmarks.
    Falls back to pixel analysis when HTML tables are broken.
    """
    if not md_path.exists():
        return {}
    
    text = md_path.read_text()
    results = {}
    
    # Strategy 1: Parse colspan tables (the hard cases)
    # Strategy 2: Use MinerU's image output + pixel analysis
    
    # Find all Имя: lines and their positions
    clients = {}
    
    # Pattern: имя: Name [Неделя:]
    name_pattern = re.compile(r'(?i)имя[:\s_]+(.+?)(?:\s*Недел|</t)', re.DOTALL)
    for match in name_pattern.finditer(text):
        name = re.sub(r'<[^>]+>', '', match.group(1)).strip().split('\n')[0]
        name = re.sub(r'\s+П[HН].*$', '', name).strip()
        if name and len(name) > 3:
            pos = match.start()
            clients[name] = {'pos': pos, 'name': name}
    
    # Also: Week · Name · Shift pattern
    week_pattern = re.compile(r'(?:Week \d+|Go[jJ])\s*[•·]\s*([^•·\n]+?)\s*[•·]', re.DOTALL)
    for match in week_pattern.finditer(text):
        name = re.sub(r'<[^>]+>', '', match.group(1)).strip()
        name = re.sub(r'BLANK', '', name).strip()
        if name and len(name) > 3:
            pos = match.start()
            clients[name] = {'pos': pos, 'name': name}
    
    return clients

# ── 3. Colspan Table Parser ─────────────────────────────────────────────

def parse_colspan_table(chunk, day_index=2):
    """
    Parse a colspan-based table. day_index: 0=Mon, 1=Tue, 2=Wed, 3=Thu, 4=Fri
    The column structure is: Item | colspan=2 | colspan=2 | colspan=2 | colspan=2 | colspan=2
    Checkmarks are at odd cell indices (1, 3, 5, 7, 9) for Mon-Fri.
    Wednesday = cell index 5 (0-indexed).
    """
    rows = re.findall(r'<tr>(.*?)</tr>', chunk, re.DOTALL)
    wed_items = []
    cat = None
    
    for row in rows:
        cells = re.findall(r'<td[^>]*>(.*?)</td>', row, re.DOTALL)
        cells_t = [re.sub(r'<[^>]+>', '', c).strip() for c in cells]
        full = ' '.join(cells_t)
        
        if any(w in full for w in ['САЛАТ', 'САПАТ']): cat = 'salads'; continue
        if any(w in full.upper() for w in ['СУП', 'CYП', 'СУПb', 'CYПb']): cat = 'soups'; continue
        if 'ГЛАВНОЕ' in full.upper() and 'ПРОДОЛЖ' not in full: cat = 'mains'; continue
        if 'ГАРНИР' in full.upper(): cat = 'sides'; continue
        if 'Имя' in full or 'ПН' in full or 'Недел' in full: continue
        
        item = cells_t[0] if cells_t else ''
        if len(item) < 2: continue
        
        # Check Wednesday: position 5 for colspan=2 pattern, or position 3 for simple
        wed_i = None
        if len(cells_t) > 5:
            wed_i = 5  # colspan=2 pattern
        elif len(cells_t) > 3:
            wed_i = 3  # simple 5-column pattern
        
        if wed_i and wed_i < len(cells_t):
            mark = cells_t[wed_i].strip()
            if mark and mark not in ['□', '']:
                wed_items.append((mark, item, cat))
    
    return wed_items

# ── 4. Name matching ────────────────────────────────────────────────────

def load_roster():
    db_path = HOME / "Documents/goj files/dashboard/auth_tracker.db"
    if not db_path.exists():
        return []
    db = sqlite3.connect(str(db_path))
    rows = db.execute("SELECT name FROM clients WHERE active=1").fetchall()
    db.close()
    return [r[0] for r in rows]

def match_name(ocr_name, roster):
    if not ocr_name or not roster: return None
    norm = lambda s: s.lower().replace(' ', '').replace('-', '')
    n = norm(ocr_name)
    for r in roster:
        rn = norm(r)
        if n == rn: return r
        parts = ocr_name.split()
        for p in parts:
            if len(p) >= 4 and p.lower() in rn: return r
        rparts = r.split()
        for rp in rparts:
            if len(rp) >= 4 and rp.lower() in n: return r
    return None

# ── 5. Main Pipeline ────────────────────────────────────────────────────

def process_md(md_path, day='Wed'):
    """Full pipeline on one MinerU MD file."""
    day_map = {'Mon': 0, 'Tue': 1, 'Wed': 2, 'Thu': 3, 'Fri': 4}
    di = day_map.get(day, 2)
    
    text = md_path.read_text()
    roster = load_roster()
    
    if not roster:
        return {"error": "No roster loaded"}
    
    # Find all client names
    name_pattern = re.compile(
        r'(?i)(?:имя[:\s_]+|Week \d+\s*[•·]\s*|Go[jJ]\s*[•·]\s*)'
        r'([^\n<•·]+?)(?:\s*(?:Недел|</t|[•·]|Shift|\n))',
        re.DOTALL
    )
    
    results = {}
    
    for match in name_pattern.finditer(text):
        raw_name = re.sub(r'<[^>]+>', '', match.group(1)).strip()
        raw_name = re.sub(r'\s+П[HН].*$', '', raw_name).strip()
        raw_name = re.sub(r'BLANK', '', raw_name).strip()
        
        if len(raw_name) < 3:
            continue
        
        roster_match = match_name(raw_name, roster)
        if not roster_match:
            continue
        
        # Extract menu data from colspan table after this name
        pos = match.end()
        chunk = text[pos:pos+6000]
        
        wed_items = parse_colspan_table(chunk, day_index=di)
        
        if wed_items:
            results[roster_match] = {
                'raw_ocr': raw_name,
                'wed_items': wed_items,
                'file': str(md_path.name)
            }
    
    return results

# ── CLI ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 CC_menu_checkmark_detector.py <mineru_md_file>")
        sys.exit(1)
    
    path = Path(sys.argv[1])
    results = process_md(path)
    
    for name, data in results.items():
        items = data['wed_items']
        if items:
            print(f"\n{name}:")
            for mark, item, cat in items:
                print(f"  {mark} {item} ({cat})")
    
    print(f"\nTotal clients extracted: {len(results)}")
