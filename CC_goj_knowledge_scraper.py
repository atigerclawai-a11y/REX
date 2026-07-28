#!/usr/bin/env python3
"""GOJ knowledge scraper — deep-scrape EVERY file into one searchable corpus (Mac-side).

Runs locally so there is NO context-window limit and it can reach your backup drive.
Walks folders recursively and, per file:
  - text (md/txt/py/csv/json/sh/html/sql/yaml/xml/ini/cfg/log) -> extracted inline
  - .xlsx / .docx                                              -> text pulled from zip XML
  - .pdf                                                       -> pdftotext (poppler); if
                                                                  empty it's a SCAN -> OCR queue
  - images (jpg/jpeg/png/tif/tiff/heic/bmp/gif) + empty pdfs   -> knowledge/ocr_queue.txt
  - everything else                                            -> inventoried in index.md

Outputs:
  knowledge/corpus.jsonl   one record per readable file {path, ext, bytes, chars, text}
  knowledge/index.md       full inventory + first 60 lines of each readable doc
  knowledge/ocr_queue.txt  every scan/image to feed the OCR track (Track A/B)

FIRST extract any archive so its files are walkable, e.g.
    mkdir -p ~/goj_corpus && tar xzf /Volumes/BACKUP/goj-files-*.tar.gz -C ~/goj_corpus

Build :  python scrape_knowledge.py build ~/goj_corpus /Volumes/BACKUP/GOJ
Search:  python scrape_knowledge.py search "APC_FAIL denial CPHL"
"""
import sys, json, subprocess, zipfile, re, html
from pathlib import Path

TEXT_EXT = {".md", ".txt", ".py", ".csv", ".json", ".sh", ".html", ".htm",
            ".sql", ".yaml", ".yml", ".xml", ".ini", ".cfg", ".log"}
IMG_EXT = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".heic", ".bmp", ".gif"}
OUT = Path("knowledge")
_ocr = []


def _xml_text(zpath: Path, member_ok) -> str:
    out = []
    try:
        with zipfile.ZipFile(zpath) as z:
            for name in z.namelist():
                if member_ok(name):
                    out.append(html.unescape(re.sub(r"<[^>]+>", " ",
                               z.read(name).decode("utf-8", "ignore"))))
    except Exception as e:
        return f"[{zpath.suffix}: {e}]"
    return " ".join(out)


def read_text(p: Path) -> str:
    ext = p.suffix.lower()
    try:
        if ext in TEXT_EXT:
            return p.read_text(errors="ignore")
        if ext == ".docx":
            return _xml_text(p, lambda n: n == "word/document.xml")
        if ext == ".xlsx":
            return _xml_text(p, lambda n: n.startswith("xl/sharedStrings") or
                             (n.startswith("xl/worksheets/") and n.endswith(".xml")))
        if ext == ".pdf":
            try:
                t = subprocess.run(["pdftotext", "-layout", str(p), "-"],
                                   capture_output=True, text=True, timeout=180).stdout
            except Exception:
                return "[pdf: install poppler -> brew install poppler]"
            if len(t.strip()) < 40:            # no embedded text -> it's a scan
                _ocr.append(str(p)); return "[pdf: no text layer -> queued for OCR]"
            return t
        if ext in IMG_EXT:
            _ocr.append(str(p)); return "[image -> queued for OCR]"
    except Exception as e:
        return f"[error: {e}]"
    return ""


def build(roots):
    OUT.mkdir(exist_ok=True)
    corpus, index, ocrq = OUT / "corpus.jsonl", OUT / "index.md", OUT / "ocr_queue.txt"
    n = other = 0
    readable = TEXT_EXT | {".pdf", ".docx", ".xlsx"} | IMG_EXT
    with corpus.open("w", encoding="utf-8") as cf, index.open("w", encoding="utf-8") as ixf:
        ixf.write(f"# GOJ deep-scrape index — {', '.join(roots)}\n\n")
        for root in roots:
            for p in sorted(Path(root).rglob("*")):
                if not p.is_file():
                    continue
                if p.suffix.lower() not in readable:
                    other += 1
                    ixf.write(f"- (not scraped) `{p}`  ({p.stat().st_size:,} B)\n")
                    continue
                text = read_text(p)
                cf.write(json.dumps({"path": str(p), "ext": p.suffix.lower(),
                                     "bytes": p.stat().st_size, "chars": len(text),
                                     "text": text}, ensure_ascii=False) + "\n")
                head = "\n".join(text.splitlines()[:60])
                ixf.write(f"\n## {p.name}  ({p.stat().st_size:,} B · {len(text):,} chars)\n"
                          f"`{p}`\n\n```\n{head}\n```\n")
                n += 1
    ocrq.write_text("\n".join(_ocr), encoding="utf-8")
    print(f"Scraped {n} readable files, {other} other (inventoried).")
    print(f"  {corpus}\n  {index}\n  {ocrq}  ({len(_ocr)} scans/images to OCR)")


def search(term):
    corpus = OUT / "corpus.jsonl"
    if not corpus.exists():
        print("Run `build <folder> [<folder> ...]` first."); return
    t, hits = term.lower(), 0
    for line in corpus.open(encoding="utf-8"):
        rec = json.loads(line)
        low = rec["text"].lower()
        if t in low:
            hits += 1
            i = low.find(t)
            print(f"\n### {rec['path']}\n…{rec['text'][max(0,i-120):i+220].strip()}…")
    print(f"\n{hits} files matched '{term}'")


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "build":
        build(sys.argv[2:])
    elif len(sys.argv) >= 3 and sys.argv[1] == "search":
        search(" ".join(sys.argv[2:]))
    else:
        print(__doc__)
