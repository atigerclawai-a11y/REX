#!/usr/bin/env python3
"""Garbled-name review package builder.

For a given menu doc (already MinerU-OCR'd), find each unmatched client name,
locate it in the MinerU content_list JSON (page_idx), render that PDF page's
top region (where Имя: lives) to a PNG, and emit a review manifest.

Usage: python3 CC_garbled_review.py <doc_stem> [--src-pdf PATH]
Output: ~/Desktop/REX/garbled_review/<doc>/<idx>_<slug>.png + manifest.json
"""
import sys, json, re, argparse
from pathlib import Path

sys.path.insert(0, "/Users/mainsobhelper/Desktop/REX")
import fitz  # PyMuPDF
from goj_menu_form_parser import parse_menu_md, load_roster, norm_text

REX = Path.home() / "Desktop/REX"
OUT = REX / "garbled_review"
STABLE = REX / "menu_intake_stable"
SCANS = Path.home() / "Documents/goj files/scans/ocr_processed"

def find_md(doc_stem: str):
    cands = list(REX.glob(f"menu_ocr_full/{doc_stem}/ocr/*.md"))
    if cands:
        return cands[0]
    return None

def find_src_pdf(doc_stem: str):
    for d in (STABLE, SCANS, Path("/tmp/email_intake")):
        for pat in (f"{doc_stem}.pdf", f"*{doc_stem}*.pdf"):
            hits = sorted(d.glob(pat))
            if hits:
                return hits[0]
    return None

def name_slug(s: str) -> str:
    s = re.sub(r"[^A-Za-zА-Яа-я0-9]+", "_", s).strip("_")
    return s[:40] or "noname"

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("doc")
    ap.add_argument("--src-pdf", default=None)
    ap.add_argument("--dpi", type=int, default=150)
    args = ap.parse_args()

    doc = args.doc
    md = find_md(doc)
    if not md:
        print(f"NO_MD {doc}"); sys.exit(1)
    pdf_path = Path(args.src_pdf) if args.src_pdf else find_src_pdf(doc)
    if not pdf_path or not pdf_path.exists():
        print(f"NO_PDF {doc}"); sys.exit(1)

    # Parse the doc, collect unmatched names
    roster, norm = load_roster()
    parsed = parse_menu_md(str(md), roster, norm)
    unmatched = [raw for raw, info in parsed["clients"].items()
                 if not info.get("matched")]
    if not unmatched:
        print(f"ALL_MATCHED {doc}")
        sys.exit(0)

    # content_list_v2.json = list of pages; each page = list of blocks with
    # nested content + bbox. Extract per-page text, score token overlap.
    cl_files = sorted(md.parent.glob("*content_list_v2.json")) or \
                 sorted(md.parent.glob("*content_list.json"))
    page_hits = {}
    if cl_files:
        cl = json.loads(cl_files[0].read_text())
        def texts(o):
            if isinstance(o, dict):
                for k, v in o.items():
                    if k in ("text", "content") and isinstance(v, str):
                        yield v
                    else:
                        yield from texts(v)
            elif isinstance(o, list):
                for v in o:
                    yield from texts(v)
        page_texts = []
        if isinstance(cl, list):
            for pg in cl:
                page_texts.append(" ".join(texts(pg)).lower())
        for name in unmatched:
            toks = [t.lower() for t in re.split(r"\s+", name) if len(t) >= 4]
            best = None
            for pi, ptxt in enumerate(page_texts):
                if not ptxt:
                    continue
                score = sum(1 for t in toks if t in ptxt)
                if score and (best is None or score > best[0]):
                    best = (score, pi)
            if best:
                page_hits[name] = best[1]

    # Render: name lives at top of the client's first form page
    outdir = OUT / doc
    outdir.mkdir(parents=True, exist_ok=True)
    pdf = fitz.open(str(pdf_path))
    manifest = []
    for i, name in enumerate(unmatched, 1):
        pg = page_hits.get(name)
        if pg is None:
            # fallback heuristic: form i starts at page (i-1)*2
            pg = min((i - 1) * 2, pdf.page_count - 1)
        pg = max(0, min(int(pg), pdf.page_count - 1))
        page = pdf.load_page(pg)
        r = page.rect
        clip = fitz.Rect(r.x0, r.y0, r.x1, r.y0 + r.height * 0.22)  # top 22%
        pix = page.get_pixmap(dpi=args.dpi, clip=clip)
        fn = outdir / f"{i:02d}_{name_slug(name)}_p{pg+1}.png"
        pix.save(str(fn))
        manifest.append({"idx": i, "ocr_name": name, "pdf_page": pg + 1,
                         "image": str(fn)})
    (outdir / "manifest.json").write_text(json.dumps(
        {"doc": doc, "src_pdf": str(pdf_path), "count": len(manifest),
         "items": manifest}, ensure_ascii=False, indent=2))
    print(f"REVIEW_READY {doc} unmatched={len(manifest)} dir={outdir}")
    for m in manifest:
        print(f"  [{m['idx']:02d}] {m['ocr_name']!r} → p{m['pdf_page']} {Path(m['image']).name}")

if __name__ == "__main__":
    main()
