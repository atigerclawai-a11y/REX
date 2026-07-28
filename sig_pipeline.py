"""
Signature extraction → attendance_evidence_rows (the signature database).

For each sign-in sheet: locate the signature column (rightmost of the table),
crop each client row's signature cell, detect ink presence, save the crop, and
write one evidence row per client into attendance_evidence_rows with:
  client_name_ocr, row_number, page_number, source_pdf_path, signature_crop_path,
  signature_present ('yes'/'no'), name/row confidence, attendance_status.

v1 geometry heuristic (verify crops in the review UI): signature column = rightmost
1/ncols of the table bbox; rows = table body divided evenly by rows-on-page. Refine
once cell-level bboxes are available. Comparison vs signature_sample_registry is the
NEXT step (needs reference enrollment).
"""
import fitz, sqlite3, json, os
from datetime import datetime
from pathlib import Path

DB = Path.home() / "Documents" / "goj files" / "dashboard" / "auth_tracker.db"
SIG_DIR = Path.home() / "Documents" / "goj files" / "signatures"
INK_THRESHOLD = 0.012   # fraction of dark pixels above which a cell counts as "signed"


def _ink_ratio(pix) -> float:
    """Fraction of non-white (ink) pixels in a pixmap."""
    n = pix.width * pix.height
    if n == 0:
        return 0.0
    dark = 0
    samples = pix.samples
    stride = pix.n  # bytes per pixel
    for i in range(0, len(samples), stride):
        # treat a pixel as ink if noticeably darker than white
        if samples[i] < 200:
            dark += 1
    return dark / n


def extract_sheet_signatures(pdf_path, registry_id, clients, ncols=7):
    """Crop per-row signatures for one sheet, write evidence rows. Returns summary."""
    SIG_DIR.mkdir(parents=True, exist_ok=True)
    doc = fitz.open(pdf_path)
    conn = sqlite3.connect(str(DB)); cur = conn.cursor(); now = datetime.now().isoformat()
    stem = Path(pdf_path).stem
    npages = len(doc)
    # distribute clients across pages in order
    per_page = max(1, (len(clients) + npages - 1) // npages) if npages else len(clients)
    written = signed = 0
    for idx, c in enumerate(clients):
        name = (c.get("name") or "").strip()
        if not name:
            continue
        page_idx = min(idx // per_page, npages - 1)
        page = doc[page_idx]
        pr = page.rect
        # signature column = rightmost 1/ncols of the page width (below a header margin)
        col_w = pr.width / ncols
        sig_x0, sig_x1 = pr.x1 - col_w, pr.x1
        body_top = pr.y0 + pr.height * 0.10   # skip title/header band
        rows_here = min(per_page, len(clients) - page_idx * per_page)
        row_in_page = idx - page_idx * per_page
        band_h = (pr.y1 - body_top) / max(rows_here, 1)
        y0 = body_top + row_in_page * band_h
        # inset to the cell center so table grid-lines/borders don't read as "ink"
        mx, my = (sig_x1 - sig_x0) * 0.14, band_h * 0.22
        rect = fitz.Rect(sig_x0 + mx, y0 + my, sig_x1 - mx, y0 + band_h - my)
        present = "unknown"; crop_path = ""
        try:
            pix = page.get_pixmap(clip=rect, dpi=150)
            ratio = _ink_ratio(pix)
            present = "yes" if ratio >= INK_THRESHOLD else "no"
            crop_path = str(SIG_DIR / f"{stem}_p{page_idx}_r{row_in_page}_{name.split()[0][:12]}.png")
            pix.save(crop_path)
            if present == "yes":
                signed += 1
        except Exception:
            pass
        cur.execute(
            "INSERT INTO attendance_evidence_rows (registry_id, client_name_ocr, matched_client_name, "
            "attendance_status, source_pdf_path, page_number, row_number, signature_crop_path, "
            "signature_present, created_at, active) VALUES (?,?,?,?,?,?,?,?,?,?,1)",
            (registry_id, name, name, "present", pdf_path, page_idx, row_in_page + 1,
             crop_path, present, now))
        written += 1
    conn.commit(); conn.close(); doc.close()
    return {"evidence_rows": written, "signed": signed, "pdf": Path(pdf_path).name}
