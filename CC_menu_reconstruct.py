#!/usr/bin/env python3
"""CC_menu_reconstruct.py — GOJ menu PDF reconstruction from scanned forms.

WORKFLOW:
1. Extract client names from scanned form (via MinerU or direct PDF text)
2. FUZZY MATCH against 425 known GOJ clients from auth_tracker.db
3. Show me the OCR guesses → I correct anything wrong
4. Generate clean, machine-readable PDF that never needs OCR again

Usage:
    python3 CC_menu_reconstruct.py <scanned_menu.pdf> [--date 2026-07-22] [--shift 1]
"""

import json, re, os, sys, sqlite3
from pathlib import Path
from datetime import datetime

# ── Paths ──
REX_DIR = Path.home() / "Desktop/REX"
OUTPUT_DIR = Path.home() / "Documents/goj files/output_docs"
DB_PATH = Path.home() / "Documents/goj files/dashboard/auth_tracker.db"
MINERU_VENV = REX_DIR / "mineru-venv"

output_dir = REX_DIR / "menu_reconstructed"
output_dir.mkdir(exist_ok=True)

# ── Step 0: Load known clients ──
def load_clients():
    """Load all known GOJ client names from auth_tracker.db."""
    conn = sqlite3.connect(str(DB_PATH))
    rows = conn.execute("SELECT DISTINCT client_name FROM authorization ORDER BY client_name").fetchall()
    conn.close()
    # Also try clients table for the full list
    conn2 = sqlite3.connect(str(DB_PATH))
    rows2 = conn2.execute("SELECT name FROM clients ORDER BY name").fetchall()
    conn2.close()
    
    names = set()
    for r in rows: names.add(r[0].strip() if r[0] else "")
    for r in rows2: names.add(r[0].strip() if r[0] else "")
    names.discard("")
    
    # Build normalized lookup
    known = {}
    for n in sorted(names):
        # Normalize: lowercase, no spaces, no diacritics
        key = n.lower().replace(" ", "").replace("-", "")
        key = key.replace("ё", "е").replace("Ё", "Е")
        known[key] = n
    
    return known, sorted(names)

def fuzzy_match(ocr_name: str, known: dict, known_list: list) -> str:
    """Fuzzy match an OCR-extracted name against known clients."""
    ocr_clean = ocr_name.strip()
    if not ocr_clean:
        return None
    
    # Exact match first
    key = ocr_clean.lower().replace(" ", "").replace("-", "")
    key = key.replace("ё", "е").replace("Ё", "Е")
    if key in known:
        return known[key]
    
    # Token match: does any name contain all the OCR tokens?
    ocr_tokens = ocr_clean.lower().split()
    if len(ocr_tokens) >= 2:
        for known_name in known_list:
            k_lower = known_name.lower()
            if all(t in k_lower for t in ocr_tokens):
                return known_name
    
    # Last resort: simple Levenshtein on first+last initial
    best_score = 0
    best_name = None
    for known_name in known_list:
        k = known_name.lower()
        # Start/prefix match
        if k.startswith(ocr_clean.lower()[:3]):
            return known_name  # Good enough
    
    return None

# ── Step 1: Extract text from PDF ──
def extract_pdf_text(pdf_path: str) -> str:
    """Extract text from PDF (works for already-digital PDFs)."""
    from pypdf import PdfReader
    reader = PdfReader(pdf_path)
    all_text = []
    for page in reader.pages:
        txt = page.extract_text()
        if txt:
            all_text.append(txt)
    return "\n".join(all_text)

# ── Step 1b: Run MinerU for scanned PDFs ──
def run_mineru_ocr(pdf_path: str) -> str:
    """Run MinerU if the PDF has no extractable text."""
    mineru_bin = MINERU_VENV / "bin/mineru"
    out_dir = "/tmp/mineru_reconstruct"
    os.makedirs(out_dir, exist_ok=True)
    
    import subprocess
    result = subprocess.run(
        [str(mineru_bin), "-p", pdf_path, "-o", out_dir],
        capture_output=True, text=True, timeout=600
    )
    if result.returncode != 0:
        raise RuntimeError(f"MinerU failed: {result.stderr[:500]}")
    
    md_files = list(Path(out_dir).rglob("*.md"))
    if not md_files:
        raise RuntimeError("No markdown output from MinerU")
    return md_files[0]

# ── Step 2: Parse names from text ──
def parse_names(text: str) -> list:
    """Extract likely client names from OCR/direct text."""
    names = []
    
    # Pattern: capitalized words (names appear on individual lines)
    # Russian + English name patterns
    lines = text.split("\n")
    for line in lines:
        line = line.strip()
        if not line or len(line) < 3:
            continue
            
        # Skip headers and noise
        if any(x in line.upper() for x in ["GARDEN", "ADULT", "DAYCARE", "SALAD", "SOUP", 
                                             "NH", "BT", "CP", "4T", "NT", "MENU", "SHIFT",
                                             "CATERER", "CLIENT", "PIN", "TABLE"]):
            continue
        
        # Look for name-like patterns: two+ capitalized words
        # Russian: Агаронова Нелия or English: Agaronova Nelia
        words = line.split()
        caps = [w for w in words if w[0].isupper() and len(w) > 1]
        
        if len(caps) >= 2:
            # Could be a name
            name = " ".join(caps)
            # Filter out HTML/noise
            if not re.search(r'[<>\d\[\]{}]', name) and len(name) < 60:
                names.append(name)
    
    # Deduplicate while preserving order
    seen = set()
    unique = []
    for n in names:
        key = n.lower().strip()
        if key not in seen:
            seen.add(key)
            unique.append(n.strip())
    
    return unique

# ── Step 2b: Parse from MinerU markdown ──
def parse_mineru_markdown(md_path: str) -> list:
    """Extract names from MinerU HTML table output."""
    text = Path(md_path).read_text(encoding="utf-8")
    names = []
    
    # HTML table rows: <td>: Name</td><td>Code</td>...
    rows = re.findall(r'<tr>(.*?)</tr>', text, re.DOTALL)
    for row in rows:
        cells = re.findall(r'<td[^>]*>(.*?)</td>', row, re.DOTALL)
        if len(cells) >= 2:
            name_cell = cells[0].strip()
            name = name_cell.replace(":", "").strip()
            # Clean
            name = re.sub(r'<[^>]+>', '', name)
            name = re.sub(r'^[:\sa]+', '', name).strip()
            name = re.sub(r'[^A-Za-zА-Яа-яЁё\s\-]', '', name).strip()
            
            if name and len(name) > 2 and not any(x in name.upper() for x in ["GARDEN", "ADULT", "DAYCARE"]):
                names.append(name)
    
    # Also try markdown table rows
    table_pattern = re.findall(r'\|\s*[:\s]*([A-Za-zА-Яа-яЁё\-]+(?:\s+[A-Za-zА-Яа-яЁё\-]+)+)\s*\|', text)
    for name in table_pattern:
        name = name.strip()
        if name and len(name) > 3 and not any(x in name.upper() for x in ["GARDEN", "ADULT", "DAYCARE", "NH", "BT"]):
            names.append(name)
    
    # Deduplicate
    seen = set()
    unique = []
    for n in names:
        key = n.lower().strip()
        if key not in seen:
            seen.add(key)
            unique.append(n.strip())
    
    return unique

# ── Step 3: Generate clean PDF ──
def generate_clean_pdf(matched: list, date_str: str, shift: int, caterer: str = "Olimp"):
    """Generate a clean, machine-readable menu PDF from matched client data."""
    try:
        from reportlab.lib.pagesizes import letter
        from reportlab.lib import colors
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Spacer, Paragraph
        from reportlab.lib.styles import StyleSheet1, ParagraphStyle
    except ImportError:
        print("Installing reportlab...")
        os.system(f"{sys.executable} -m pip install reportlab")
        from reportlab.lib.pagesizes import letter
        from reportlab.lib import colors
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Spacer, Paragraph
        from reportlab.lib.styles import StyleSheet1, ParagraphStyle
    
    filename = f"GOJ_MENU_{date_str}_S{shift}_cleaned.pdf"
    output = output_dir / filename
    
    doc = SimpleDocTemplate(
        str(output), pagesize=letter,
        leftMargin=24, rightMargin=24, topMargin=24, bottomMargin=24
    )
    
    styles = StyleSheet1()
    styles.add(ParagraphStyle('Title', fontName='Helvetica-Bold', fontSize=14, spaceAfter=4, alignment=1))
    styles.add(ParagraphStyle('Sub', fontName='Helvetica', fontSize=10, spaceAfter=10, alignment=1, textColor=colors.gray))
    
    elements = []
    elements.append(Paragraph("GARDEN OF JOY — MENU ORDER FORM", styles['Title']))
    elements.append(Paragraph(f"{date_str}  |  Shift {shift}  |  Caterer: {caterer}", styles['Sub']))
    elements.append(Spacer(1, 8))
    
    # Sort
    matched = sorted(matched, key=lambda c: c['name'].lower())
    
    # Table
    header = ['#', 'Client Name', 'NH', 'BT', 'CP', '4T', 'NT']
    data = [header]
    for i, c in enumerate(matched, 1):
        row = [str(i), c['name']]
        codes = c.get('codes', [])
        for j in range(5):
            row.append(codes[j] if j < len(codes) else '')
        data.append(row)
    
    # Split into pages by ~35 rows
    page_size = 35
    for page_num, start in enumerate(range(1, len(data), page_size)):
        if page_num > 0:
            elements.append(Spacer(1, 16))
        page_data = [data[0]] + data[start:start + page_size]
        
        t = Table(page_data, colWidths=[22, 190, 50, 50, 50, 50, 50], repeatRows=1)
        style = [
            ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
            ('FONTSIZE', (0,0), (-1,-1), 8),
            ('BACKGROUND', (0,0), (-1,0), colors.Color(0,0.35,0,0.12)),
            ('TEXTCOLOR', (0,0), (-1,0), colors.Color(0,0.3,0)),
            ('ALIGN', (2,0), (-1,-1), 'CENTER'),
            ('ALIGN', (0,0), (0,-1), 'CENTER'),
            ('GRID', (0,0), (-1,-1), 0.5, colors.Color(0,0,0,0.12)),
            ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, colors.Color(0,0.4,0,0.035)]),
            ('TOPPADDING', (0,0), (-1,-1), 3),
            ('BOTTOMPADDING', (0,0), (-1,-1), 3),
        ]
        # Green for checked items
        for ri in range(1, len(page_data)):
            for ci in range(2, 7):
                val = page_data[ri][ci]
                if val and val.strip():
                    style.append(('TEXTCOLOR', (ci, ri), (ci, ri), colors.Color(0,0.5,0)))
                    style.append(('FONTNAME', (ci, ri), (ci, ri), 'Helvetica-Bold'))
        t.setStyle(TableStyle(style))
        elements.append(t)
    
    doc.build(elements)
    return str(output)

# ── Main ──
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Reconstruct GOJ menu PDF from scan")
    parser.add_argument("pdf", nargs="?", help="Scanned menu PDF path")
    parser.add_argument("--date", help="Menu date (YYYY-MM-DD)")
    parser.add_argument("--shift", type=int, default=1, choices=[1, 2])
    args = parser.parse_args()
    
    if not args.pdf:
        # Interactive mode: find latest scan
        print("🔍 No PDF specified. Looking for recent menu scans...")
        import glob
        scans = sorted(Path.home().glob("Documents/goj files/scans/ocr_processed/*.pdf"), key=lambda p: p.stat().st_mtime, reverse=True)
        for i, s in enumerate(scans[:10]):
            print(f"  [{i+1}] {s.name} ({s.stat().st_size//1024}KB)")
        choice = input("Select (1-10) or enter PDF path: ").strip()
        if choice.isdigit() and 1 <= int(choice) <= len(scans):
            args.pdf = str(scans[int(choice)-1])
        else:
            args.pdf = choice
    
    date_str = args.date or datetime.now().strftime("%Y-%m-%d")
    
    print(f"\n{'='*60}")
    print(f"🐢 GOJ MENU RECONSTRUCTION")
    print(f"{'='*60}")
    print(f"PDF:    {args.pdf}")
    print(f"Date:   {date_str}")
    print(f"Shift:  {args.shift}")
    print(f"{'='*60}\n")
    
    # Step 0: Load known clients
    print("[0/4] Loading known clients from DB...")
    known, known_list = load_clients()
    print(f"  → {len(known)} known clients\n")
    
    # Step 1: Extract text
    print("[1/4] Extracting text from PDF...")
    pdf_text = extract_pdf_text(args.pdf)
    has_text = bool(pdf_text.strip())
    
    if has_text:
        print(f"  ✅ PDF has extractable text ({len(pdf_text)} chars)")
        names = parse_names(pdf_text)
        print(f"  → Extracted {len(names)} candidate names")
    else:
        print(f"  ⚠ PDF is scanned image — need MinerU OCR (first-run downloads models)")
        print(f"  ℹ Run: mineru -p \"{args.pdf}\" -o /tmp/mineru_reconstruct")
        names = []
    
    # Step 2: Also try MinerU markdown if available
    md_path = None
    for p in Path("/tmp/mineru_reconstruct").rglob("*.md"):
        md_path = p
        break
    
    if md_path:
        print(f"\n  Using existing MinerU output: {md_path}")
        mineru_names = parse_mineru_markdown(str(md_path))
        print(f"  → MinerU found {len(mineru_names)} names")
        # Merge with direct text extraction
        all_names = list(dict.fromkeys(names + mineru_names))
    else:
        all_names = names
    
    if not all_names:
        print("\n  ❌ No names extracted. Options:")
        print("    1. Run MinerU: cd ~/Desktop/REX && mineru-venv/bin/mineru -p \"<pdf>\" -o /tmp/mineru_reconstruct")
        print("    2. Use a PDF with extractable text")
        print("    3. Manually enter client PINs for today's shift")
        sys.exit(1)
    
    print(f"\n  Total unique candidates: {len(all_names)}")
    
    # Step 3: Fuzzy match against known clients
    print("\n[2/4] Matching against known clients...")
    matched = []
    unmatched = []
    for name in all_names:
        result = fuzzy_match(name, known, known_list)
        if result:
            matched.append({"name": result, "codes": []})
            print(f"  ✅ {name:35s} → {result}")
        else:
            unmatched.append(name)
            print(f"  ❌ {name:35s} → NO MATCH")
    
    print(f"\n  Matched: {len(matched)} / {len(all_names)}")
    if unmatched:
        print(f"  Unmatched ({len(unmatched)}):")
        for u in unmatched:
            print(f"    - {u}")
        print("\n  ℹ These will need manual review.")
    
    # Step 3b: Show cluster info
    print(f"\n  ⚠ Shift {args.shift} has {len(matched)} matched clients")
    print(f"  (Total GOJ: {len(known)} clients)")
    
    # Step 4: Generate clean PDF
    print("\n[3/4] Generating clean PDF...")
    output_pdf = generate_clean_pdf(matched, date_str, args.shift)
    print(f"  ✅ Clean PDF: {output_pdf}")
    
    print("\n[4/4] Copying to output_docs...")
    import shutil
    final_path = OUTPUT_DIR / f"GOJ_MENU_{date_str}_S{args.shift}.pdf"
    shutil.copy(output_pdf, str(final_path))
    print(f"  ✅ Delivered: {final_path}")
    
    print(f"\n{'='*60}")
    print(f"✅ DONE — {len(matched)} clients in menu PDF")
    print(f"📄 {final_path}")
    if unmatched:
        print(f"\n⚠ {len(unmatched)} unmatched names need review")
    print(f"{'='*60}")
