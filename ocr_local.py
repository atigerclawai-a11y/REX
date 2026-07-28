#!/usr/bin/env python3
"""Local OCR Pipeline — processes documents using tesseract + pdftotext only.
Zero cloud, zero Docker, zero OAuth. IMAP is the only outbound path.
Usage: python3 ocr_local.py /path/to/document.pdf
       python3 ocr_local.py --watch ~/Documents/goj\ files/scans/
"""

import sys, os, subprocess, json
from pathlib import Path
from datetime import datetime

OUTPUT_DIR = os.path.expanduser("~/.hermes/rexxie_vault/ocr-output")
os.makedirs(OUTPUT_DIR, exist_ok=True)

def ocr_image(image_path):
    """OCR an image using tesseract."""
    result = subprocess.run(
        ["tesseract", image_path, "stdout", "-l", "eng+rus", "--psm", "6"],
        capture_output=True, text=True, timeout=30
    )
    return result.stdout.strip()

def ocr_pdf(pdf_path):
    """Extract text from PDF. Use pdftotext first, fall back to PyMuPDF for images."""
    # Fast path: pdftotext
    result = subprocess.run(
        ["pdftotext", "-layout", pdf_path, "-"],
        capture_output=True, text=True, timeout=30
    )
    text = result.stdout.strip()
    
    if len(text) > 50:
        return text
    
    # Slow path: PyMuPDF for scanned PDFs
    try:
        import fitz
        doc = fitz.open(pdf_path)
        pages = []
        for page in doc:
            page_text = page.get_text()
            if len(page_text.strip()) > 10:
                pages.append(page_text)
            else:
                # Page is likely an image — render and OCR
                pix = page.get_pixmap(dpi=300)
                tmp = f"/tmp/ocr_page_{page.number}.png"
                pix.save(tmp)
                ocr_text = ocr_image(tmp)
                pages.append(ocr_text)
                os.remove(tmp)
        doc.close()
        return "\n\n".join(pages)
    except Exception as e:
        return f"[PyMuPDF error: {e}]"

def process_file(filepath):
    """Process a single file and save result."""
    path = Path(filepath)
    if not path.exists():
        return {"error": "not found"}
    
    ext = path.suffix.lower()
    
    if ext == ".pdf":
        text = ocr_pdf(str(path))
    elif ext in (".png", ".jpg", ".jpeg", ".tiff", ".tif", ".bmp"):
        text = ocr_image(str(path))
    else:
        return {"error": f"unsupported format: {ext}"}
    
    # Save result
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = os.path.join(OUTPUT_DIR, f"{path.stem}_{timestamp}.txt")
    with open(output_path, 'w') as f:
        f.write(f"# OCR: {path.name}\n# Processed: {datetime.now().isoformat()}\n# Source: {filepath}\n\n{text}")
    
    return {
        "status": "ok",
        "source": str(path),
        "output": output_path,
        "chars": len(text),
        "lines": text.count('\n')
    }

def watch_directory(directory):
    """Watch a directory for new files and process them."""
    import time
    processed = set()
    print(f"Watching {directory}...")
    
    while True:
        for f in Path(directory).iterdir():
            if f.is_file() and f.name not in processed:
                print(f"\n📄 Processing: {f.name}")
                result = process_file(str(f))
                if result.get("status") == "ok":
                    print(f"   ✅ {result['chars']} chars → {result['output']}")
                    processed.add(f.name)
                    # Optionally archive via IMAP
                    archive_via_imap(result['output'], f.name)
        time.sleep(5)

def archive_via_imap(filepath, original_name):
    """Send OCR result via IMAP as email."""
    try:
        import json
        with open(os.path.expanduser("~/.rex_gmail_imap.json"), 'r') as f:
            creds = json.load(f)
        
        with open(filepath, 'r') as f:
            body = f.read()[:5000]
        
        msg = f"""From: {creds['user']}
To: {creds['user']}
Subject: [OCR] {original_name}

{body}
"""
        import smtplib
        with smtplib.SMTP_SSL(creds['host'], 465) as server:
            server.login(creds['user'], creds['password'])
            server.sendmail(creds['user'], creds['user'], msg)
        return True
    except Exception as e:
        print(f"   ⚠️ IMAP archive skipped: {e}")
        return False

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    
    arg = sys.argv[1]
    
    if arg == "--watch":
        watch_path = sys.argv[2] if len(sys.argv) > 2 else os.path.expanduser("~/Documents/goj files/scans")
        watch_directory(watch_path)
    else:
        result = process_file(arg)
        if result.get("status") == "ok":
            print(f"✅ {result['chars']} chars → {result['output']}")
        else:
            print(f"❌ {result.get('error', 'unknown')}", file=sys.stderr)