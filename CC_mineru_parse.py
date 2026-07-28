#!/usr/bin/env python3
"""
CC_mineru_parse.py — MinerU PDF parser wrapper for GOJ document pipeline.

Replaces the 5-tier OCR cascade with a single MinerU call.
Outputs structured content_list.json that feeds into goj_signin_intake.py.

Usage:
    python3 CC_mineru_parse.py input.pdf                    # parse, print JSON result
    python3 CC_mineru_parse.py input.pdf --output-dir /tmp  # custom output dir
    python3 CC_mineru_parse.py input.pdf --json-only        # only print JSON, no temp files

Environment:
    Requires MinerU installed at ~/Desktop/REX/mineru-venv/
    Uses pipeline backend (CPU-only, no GPU required).
"""

import json
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

MINERU_BIN = str(Path.home() / "Desktop/REX/mineru-venv/bin/mineru")

# Fallback: if production venv doesn't exist, try workspace test venv
if not Path(MINERU_BIN).exists():
    _fallback = Path.home() / "workspace/.mineru-test/bin/mineru"
    if _fallback.exists():
        MINERU_BIN = str(_fallback)


def parse_pdf(pdf_path: str, output_dir: str = None) -> dict:
    """
    Parse a PDF with MinerU pipeline backend.
    
    Returns:
        dict with keys: pdf, md_path, json_path, output_dir, elements, pages, 
                        elapsed_s, error (if failed)
    """
    pdf = Path(pdf_path).resolve()
    if not pdf.exists():
        return {"error": f"File not found: {pdf_path}"}
    
    if not Path(MINERU_BIN).exists():
        return {"error": f"MinerU not found at {MINERU_BIN}. Run: cd ~/Desktop/REX && uv venv mineru-venv && source mineru-venv/bin/activate && uv pip install 'mineru[core]'"}

    parent_dir = Path(output_dir).resolve() if output_dir else Path(tempfile.mkdtemp(prefix="mineru_"))
    parent_dir.mkdir(parents=True, exist_ok=True)

    start = time.time()
    result = subprocess.run(
        [MINERU_BIN, "-p", str(pdf), "-o", str(parent_dir), "-b", "pipeline"],
        capture_output=True, text=True, timeout=300
    )
    elapsed = round(time.time() - start, 1)

    auto_dir = parent_dir / pdf.stem / "auto"
    md_file = auto_dir / f"{pdf.stem}.md"
    cl_file = auto_dir / f"{pdf.stem}_content_list.json"

    if not cl_file.exists():
        return {
            "error": "MinerU produced no output",
            "stderr": result.stderr[-1000:] if result.stderr else "",
            "stdout": result.stdout[-1000:] if result.stdout else "",
            "exit_code": result.returncode,
            "elapsed_s": elapsed
        }

    with open(cl_file) as f:
        content = json.load(f)

    # Extract table rows from content_list for direct ingestion
    tables = []
    for elem in content:
        if elem.get("type") == "table" and elem.get("table_body"):
            tables.append({
                "page": elem.get("page_idx", 0),
                "bbox": elem.get("bbox", []),
                "html": elem["table_body"],
                "rows": _parse_html_table(elem["table_body"])
            })

    return {
        "pdf": str(pdf),
        "md_path": str(md_file) if md_file.exists() else None,
        "json_path": str(cl_file),
        "output_dir": str(auto_dir),
        "elements": len(content),
        "pages": len(set(e.get("page_idx", 0) for e in content)),
        "tables": len(tables),
        "table_data": tables,
        "elapsed_s": elapsed
    }


def _parse_html_table(html: str) -> list[list[str]]:
    """Parse MinerU's HTML table output into list of rows."""
    rows = []
    for tr in re.findall(r"<tr>(.*?)</tr>", html, re.DOTALL):
        cells = re.findall(r"<td[^>]*>(.*?)</td>", tr, re.DOTALL)
        rows.append([c.strip() for c in cells])
    return rows


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 CC_mineru_parse.py <input.pdf> [--output-dir DIR] [--json-only]")
        sys.exit(1)

    pdf_path = sys.argv[1]
    output_dir = None
    json_only = "--json-only" in sys.argv

    for i, arg in enumerate(sys.argv):
        if arg == "--output-dir" and i + 1 < len(sys.argv):
            output_dir = sys.argv[i + 1]

    result = parse_pdf(pdf_path, output_dir=output_dir)

    if json_only:
        # Strip table_data for compact output
        compact = {k: v for k, v in result.items() if k != "table_data"}
        print(json.dumps(compact, indent=2, ensure_ascii=False))
    else:
        print(json.dumps(result, indent=2, ensure_ascii=False))
