#!/usr/bin/env python3
"""
CC_menu_ocr_pipeline.py — Complete menu OCR pipeline.
Stage 1: MinerU (already done) → Stage 2: Smart parser → Stage 3: Cross-ref
"""

import re, json, sys, sqlite3
from pathlib import Path
from collections import defaultdict

HOME = Path.home()
AUTH_DB = HOME / "Documents/goj files/dashboard/auth_tracker.db"

# ── Stage 2: Smart Parser ──────────────────────────────────────────────

def parse_mineru_md(md_path):
    """Parse MinerU markdown output. Handles colspan tables."""
    if not md_path.exists():
        return {}
    
    text = md_path.read_text()
    clients = {}
    current_client = None
    
    # Method A: Имя: tags
    for match in re.finditer(r'(?i)имя[:\s_]+(.+?)(?:Недел|</t)', text):
        name = re.sub(r'<[^>]+>', '', match.group(1)).strip()
        name = re.sub(r'\s+П[HН].*$', '', name).strip()
        if name and len(name) > 3:
            current_client = name
    
    # Method B: Week · Name · Shift headers
    for match in re.finditer(r'(?:Week \d+|Go[jJ])\s*[•·]\s*([^•·\n]+?)\s*[•·]\s*.*?(?:Shift|p\.)', text):
        name = re.sub(r'<[^>]+>', '', match.group(1)).strip()
        name = re.sub(r'BLANK', '', name).strip()
        if name and len(name) > 3 and 'Имя' not in name:
            current_client = name
    
    # Method C: Goj • Name • p1 headers
    for match in re.finditer(r'Go[jJ]\s*[•·]\s*([^•·\n]+?)\s*[•·]\s*p', text):
        name = re.sub(r'<[^>]+>', '', match.group(1)).strip()
        name = re.sub(r'BLANK', '', name).strip()
        if name and len(name) > 3 and 'Имя' not in name:
            current_client = name
    
    # Method D: Name embedded in column headers
    for match in re.finditer(r'(?i)(?:имя|Name)[:\s]*([A-ZА-Я][a-zа-яё]+(?:\s+[A-ZА-Я][a-zа-яё]+)+)', text):
        name = re.sub(r'<[^>]+>', '', match.group(1)).strip()
        if name and len(name) > 5:
            current_client = name
    
    return {"client_names": [], "status": "parsed"}

# ── Stage 3: Cross-Reference ────────────────────────────────────────────

def load_auth_tracker():
    """Get all active client names from auth_tracker."""
    if not AUTH_DB.exists():
        return []
    db = sqlite3.connect(str(AUTH_DB))
    rows = db.execute("SELECT name FROM clients WHERE active=1").fetchall()
    db.close()
    return [r[0] for r in rows]

def fuzzy_match(name, roster):
    """Match OCR name to roster using multiple strategies."""
    if not name or not roster:
        return None
    
    name_lower = name.lower().replace(' ', '')
    
    # Exact match
    for r in roster:
        if name_lower == r.lower().replace(' ', ''):
            return r
    
    # Last name match
    parts = name.split()
    for part in parts:
        if len(part) < 3:
            continue
        part_lower = part.lower()
        for r in roster:
            r_lower = r.lower().replace(' ', '')
            if part_lower in r_lower:
                # Also check first name if available
                if len(parts) >= 2:
                    first = parts[0].lower()
                    if first in r_lower:
                        return r
                else:
                    return r
    
    # Contains match
    for r in roster:
        r_lower = r.lower().replace(' ', '')
        if len(name_lower) >= 5 and name_lower in r_lower:
            return r
        if len(r_lower) >= 5 and r_lower in name_lower:
            return r
    
    return None

# ── Main ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if len(sys.argv) > 1:
        path = Path(sys.argv[1])
        if path.suffix == '.md':
            result = parse_mineru_md(path)
            print(json.dumps(result, indent=2))
    else:
        print("Usage: python3 CC_menu_ocr_pipeline.py <mineru_output.md>")
