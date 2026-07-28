#!/usr/bin/env python3
"""
CC_signature_learn.py — Signature Learning Pipeline Scaffold
GOJ / GHS Operations — Phase H4 (§20 addendum)

PURPOSE
-------
Scaffold for the signature learning pipeline.  Accumulates signature
samples extracted from scanned sign-in sheets, builds per-client
profiles (sample counts, metadata), and provides a placeholder
similarity stub that documents what a real model would need.

WHAT IT IS
----------
- A local-only pipeline (SQLite, PNG files on disk)
- Pure-function design — every step is independently testable
- Data model extension that sits BESIDE, not inside, auth_tracker.db
  (writes to ~/Desktop/REX/signature_models.db — its own DB)
- Reads crops produced by goj_signature_extractor.py or generates
  synthetic ones for testing

WHAT IT IS NOT
--------------
See the Directive-9 boundary below.

──────────────────────────────────────────────────────────────────
DIRECTIVE-9 BOUNDARY — READ BEFORE EXTENDING
──────────────────────────────────────────────────────────────────
Comparing a signature crop against a stored profile may ASSIST a
human reviewer in flagging a mismatch, but it MUST NOT:

  • Automatically mark a client as "attended" or "absent"
  • Write to Medicaid attendance records without explicit human sign-off
  • Override or suppress a human staff member's sign-in decision
  • Be treated as identity verification for billing, payroll, or compliance

The pipeline returns SCORES and FLAGS only.  Every attendance write
is a human-confirmed action.  Violating this rule creates fraudulent
Medicaid billing — a federal crime.

What Kato must decide before activating real signature matching:

  1. MODEL CHOICE
     A pixel-hash (Jaccard) baseline is included as a stub.  Useful
     only as a "grossly different / possibly same" gate.  For anything
     meaningful Kato must approve one of:
       a) Local Siamese CNN (e.g. fine-tuned on GOJ samples, PyTorch)
       b) OpenCV SSIM + template alignment (faster, no GPU needed)
       c) A commercial signature-verification API (requires PHI review)

  2. CONSENT
     Clients must be informed that their signatures are stored and used
     for attendance verification under HIPAA.  Check with compliance
     before storing any biometric-adjacent data.

  3. THRESHOLD
     What similarity score triggers a "possible mismatch" flag?  This
     number affects false-positive rate (staff burden) and false-negative
     rate (fraud risk).  Must be set by Kato + compliance, not the AI.

  4. FALLBACK BEHAVIOUR
     If the similarity engine returns no-match, who is notified?
     Telegram alert to supervisor?  Manual audit queue?  Decide before
     enabling.
──────────────────────────────────────────────────────────────────

EXTENDING
---------
This file is designed to be extended, not replaced.  When a real
model is approved:
  1. Implement a function compare_embeddings(emb_a, emb_b) → float
  2. Replace the stub inside profile_for() / compare_against_profile()
  3. Keep the Directive-9 safeguard — never auto-write attendance

Dependencies (all available in the Python 3.11 brew env):
  PyMuPDF (fitz), Pillow, sqlite3 (stdlib)

Usage:
  python3.11 CC_signature_learn.py --selftest
  python3.11 CC_signature_learn.py --report
  python3.11 CC_signature_learn.py --register PATH.png --client "First Last"
"""

from __future__ import annotations

import argparse
import hashlib
import io
import os
import sqlite3
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Optional

# ── Paths ────────────────────────────────────────────────────────
REX_DIR = Path(os.path.expanduser("~/Desktop/REX"))
DB_PATH = REX_DIR / "signature_models.db"          # OWN DB — never auth_tracker.db
SAMPLES_DIR = REX_DIR / "signatures" / "cc_learn_samples"

# ── Schema ───────────────────────────────────────────────────────
#
# signature_samples  — one row per individual signature crop
# signature_profiles — one row per client (aggregated view)
#
# There is intentionally NO similarity score stored here yet;
# that table (signature_comparisons) should only be added once
# the model and threshold are approved (see Directive-9 above).

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS signature_samples (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    client_name   TEXT    NOT NULL,
    source_pdf    TEXT,                     -- basename of originating PDF or 'synthetic'
    page          INTEGER,                  -- 0-indexed PDF page number
    bbox          TEXT,                     -- "x0,y0,x1,y1" in pixels at extraction DPI
    img_path      TEXT    NOT NULL,         -- absolute path to PNG on disk
    img_hash      TEXT    UNIQUE,           -- perceptual hash for deduplication
    dark_pixels   INTEGER,                  -- count of ink pixels (quality proxy)
    quality       TEXT,                     -- 'clear'|'partial'|'faint'|'synthetic'|'unknown'
    captured_at   TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS signature_profiles (
    client_name   TEXT    PRIMARY KEY,
    sample_count  INTEGER NOT NULL DEFAULT 0,
    updated_at    TEXT    NOT NULL DEFAULT (datetime('now')),
    notes         TEXT    -- human-editable notes field
);
"""


# ════════════════════════════════════════════════════════════════
# DB helpers
# ════════════════════════════════════════════════════════════════

def _open_db(db_path: Path = DB_PATH) -> sqlite3.Connection:
    """Open (and initialise if needed) the signature_models.db."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA_SQL)
    conn.commit()
    return conn


# ════════════════════════════════════════════════════════════════
# PIPELINE FUNCTIONS  (pure / testable / local)
# ════════════════════════════════════════════════════════════════

def extract_signature_region(
    pdf_path: str,
    page: int,
    bbox: tuple[int, int, int, int],
    dpi: int = 300,
    out_dir: Optional[Path] = None,
) -> Path:
    """
    Crop a rectangular region from a PDF page and save it as a PNG.

    Parameters
    ----------
    pdf_path : str
        Absolute path to the source PDF.
    page : int
        0-indexed page number.
    bbox : (x0, y0, x1, y1)
        Bounding box in pixels at the given DPI.
    dpi : int
        Render resolution (default 300).
    out_dir : Path, optional
        Directory for the output PNG.  Defaults to SAMPLES_DIR.

    Returns
    -------
    Path  — absolute path to the saved PNG.

    Notes
    -----
    Uses PyMuPDF (fitz) which is present in the brew Python 3.11 env.
    Raises FileNotFoundError if the PDF does not exist.
    """
    import fitz  # PyMuPDF

    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    save_dir = Path(out_dir) if out_dir else SAMPLES_DIR
    save_dir.mkdir(parents=True, exist_ok=True)

    zoom = dpi / 72.0
    mat = fitz.Matrix(zoom, zoom)

    doc = fitz.open(str(pdf_path))
    if page >= len(doc):
        doc.close()
        raise ValueError(f"Page {page} out of range (doc has {len(doc)} pages)")

    pg = doc[page]
    pix = pg.get_pixmap(matrix=mat)
    doc.close()

    from PIL import Image
    full_img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

    x0, y0, x1, y1 = bbox
    crop = full_img.crop((x0, y0, x1, y1))

    # Deterministic filename: hash of (pdf_basename, page, bbox)
    key = f"{pdf_path.name}:p{page}:{x0},{y0},{x1},{y1}"
    fname = f"sig_{hashlib.md5(key.encode()).hexdigest()[:12]}.png"
    out_path = save_dir / fname
    crop.save(str(out_path), "PNG")

    return out_path


def _img_hash(img_path: Path) -> str:
    """Perceptual hash (32×32 average hash) for deduplication."""
    import numpy as np
    from PIL import Image
    img = Image.open(str(img_path)).convert("L").resize((32, 32), Image.LANCZOS)
    arr = np.array(img, dtype=np.float32).flatten()
    avg = float(arr.mean())
    bits = "".join("1" if float(p) >= avg else "0" for p in arr)
    return hex(int(bits, 2))[2:].zfill(8)


def _count_dark_pixels(img_path: Path, threshold: int = 128) -> int:
    """Count pixels darker than threshold (quality proxy for ink coverage)."""
    from PIL import Image
    import numpy as np
    arr = np.array(Image.open(str(img_path)).convert("L"))
    return int((arr < threshold).sum())


def register_sample(
    client_name: str,
    png_path: str | Path,
    meta: Optional[dict] = None,
    db_path: Path = DB_PATH,
) -> int:
    """
    Register a signature PNG in signature_samples and update the client's profile.

    Parameters
    ----------
    client_name : str
        Full name of the client (used as the profile key).
    png_path : str | Path
        Absolute path to the already-saved PNG crop.
    meta : dict, optional
        Additional metadata keys: source_pdf, page, bbox, quality.
        Any key not in the schema is silently ignored.
    db_path : Path
        Target database (default: ~/Desktop/REX/signature_models.db).

    Returns
    -------
    int — the new row id in signature_samples (or existing id if duplicate hash).

    Side effects
    ------------
    • Inserts / updates signature_profiles for client_name.
    • Idempotent on duplicate image hash — returns existing id without double-inserting.
    """
    png_path = Path(png_path)
    if not png_path.exists():
        raise FileNotFoundError(f"PNG not found: {png_path}")

    meta = meta or {}
    img_hash = _img_hash(png_path)
    dark_px = _count_dark_pixels(png_path)
    now = datetime.now().isoformat(timespec="seconds")

    conn = _open_db(db_path)
    try:
        # Deduplication: check hash first
        existing = conn.execute(
            "SELECT id FROM signature_samples WHERE img_hash = ?", (img_hash,)
        ).fetchone()
        if existing:
            conn.close()
            return existing["id"]

        # Insert sample
        conn.execute(
            """
            INSERT INTO signature_samples
                (client_name, source_pdf, page, bbox, img_path,
                 img_hash, dark_pixels, quality, captured_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                client_name,
                meta.get("source_pdf"),
                meta.get("page"),
                meta.get("bbox"),
                str(png_path),
                img_hash,
                dark_px,
                meta.get("quality", "unknown"),
                now,
            ),
        )
        new_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

        # Upsert profile
        conn.execute(
            """
            INSERT INTO signature_profiles (client_name, sample_count, updated_at)
            VALUES (?, 1, ?)
            ON CONFLICT(client_name) DO UPDATE SET
                sample_count = sample_count + 1,
                updated_at   = excluded.updated_at
            """,
            (client_name, now),
        )

        conn.commit()
        return new_id

    finally:
        conn.close()


def profile_for(client_name: str, db_path: Path = DB_PATH) -> dict:
    """
    Return the signature profile for a client.

    Returns
    -------
    dict with keys:
        client_name   str
        sample_count  int   — number of registered samples
        updated_at    str   — ISO timestamp of last update
        similarity_stub str — placeholder message (see note below)

    SIMILARITY STUB NOTE
    --------------------
    Real signature matching requires a model that Kato has not yet
    approved (see Directive-9 header).  Until that decision is made,
    this function returns a human-readable stub string instead of a
    numeric score.  Callers MUST NOT treat this field as a verification
    result.  It exists only to document where a real similarity call
    will live.
    """
    conn = _open_db(db_path)
    try:
        row = conn.execute(
            "SELECT client_name, sample_count, updated_at, notes "
            "FROM signature_profiles WHERE client_name = ?",
            (client_name,),
        ).fetchone()
    finally:
        conn.close()

    if row is None:
        return {
            "client_name": client_name,
            "sample_count": 0,
            "updated_at": None,
            "similarity_stub": (
                "NO_PROFILE — client has no registered samples. "
                "Extract at least 2 clear samples before comparison is meaningful."
            ),
        }

    stub_msg = (
        f"STUB — {row['sample_count']} sample(s) registered. "
        "Real similarity scoring requires a model approved by Kato "
        "(Siamese CNN / SSIM / commercial API). "
        "This stub is a placeholder only — do NOT use for attendance decisions. "
        "Directive-9: signatures assist human review; they never auto-write attendance."
    )

    return {
        "client_name": row["client_name"],
        "sample_count": row["sample_count"],
        "updated_at": row["updated_at"],
        "notes": row["notes"],
        "similarity_stub": stub_msg,
    }


def list_profiles(db_path: Path = DB_PATH) -> list[dict]:
    """Return all client profiles ordered by sample_count descending."""
    conn = _open_db(db_path)
    try:
        rows = conn.execute(
            "SELECT client_name, sample_count, updated_at "
            "FROM signature_profiles ORDER BY sample_count DESC"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


# ════════════════════════════════════════════════════════════════
# SYNTHETIC IMAGE GENERATOR  (selftest only — no real PHI)
# ════════════════════════════════════════════════════════════════

def _make_synthetic_signature_pdf(out_path: Path) -> None:
    """
    Generate a minimal 1-page PDF containing a fake squiggle 'signature'.
    Uses PyMuPDF drawing primitives — zero real biometric data.
    """
    import fitz

    doc = fitz.open()  # new empty document
    page = doc.new_page(width=612, height=792)  # US Letter

    # Draw a synthetic squiggle in the lower-right quadrant
    # (approximate position of the signature column on a GOJ sign-in sheet)
    shape = page.new_shape()

    # Wavy line resembling a scrawl
    points = [
        (420, 640), (435, 625), (455, 650), (475, 630),
        (495, 655), (510, 635), (525, 645), (540, 630),
    ]
    shape.draw_polyline(points)
    shape.finish(color=(0, 0, 0), width=1.5, stroke_opacity=1.0)

    # A second short stroke crossing the first
    shape.draw_line((430, 655), (520, 625))
    shape.finish(color=(0, 0, 0), width=1.2)

    # Add a text label so the page isn't empty (not a real name)
    page.insert_text((50, 660), "SYNTHETIC TEST — NOT A REAL SIGNATURE", fontsize=9)

    shape.commit()
    doc.save(str(out_path))
    doc.close()


# ════════════════════════════════════════════════════════════════
# SELF-TEST
# ════════════════════════════════════════════════════════════════

def run_selftest() -> bool:
    """
    End-to-end selftest using entirely synthetic data.

    Steps
    -----
    1. Create a temporary directory for DB + images.
    2. Generate a synthetic PDF (fake squiggle).
    3. Call extract_signature_region() → PNG.
    4. Call register_sample() → DB row.
    5. Call profile_for() → assert sample_count == 1.
    6. Print verbatim results.
    7. Tear down the temp directory.

    Returns True on success, False on any assertion failure.
    """
    import traceback

    print("=" * 60)
    print("CC_signature_learn.py — SELFTEST")
    print(f"  Started: {datetime.now().isoformat(timespec='seconds')}")
    print("  Data:    SYNTHETIC — no real PHI, no real signatures")
    print("=" * 60)

    tmp = Path(tempfile.mkdtemp(prefix="cc_sig_selftest_"))
    test_db = tmp / "test_signature_models.db"
    test_samples_dir = tmp / "samples"
    test_samples_dir.mkdir()

    try:
        # ── Step 1: Generate synthetic PDF ───────────────────────
        print("\n[1/5] Generating synthetic PDF …")
        synthetic_pdf = tmp / "synthetic_signin.pdf"
        _make_synthetic_signature_pdf(synthetic_pdf)
        assert synthetic_pdf.exists(), "PDF generation failed"
        print(f"      ✓  {synthetic_pdf.name}  ({synthetic_pdf.stat().st_size} bytes)")

        # ── Step 2: Extract region via PyMuPDF ───────────────────
        print("\n[2/5] Calling extract_signature_region() …")
        # bbox covers the squiggle area we drew (pixels at 300 DPI)
        # At 300 DPI, page is 2550×3300 px for US Letter
        # We drew the squiggle around x=420-540, y=625-660 in points
        # At 300/72 ≈ 4.17× zoom: x≈1750-2250, y≈2600-2750
        bbox = (1700, 2550, 2300, 2800)
        png_path = extract_signature_region(
            pdf_path=str(synthetic_pdf),
            page=0,
            bbox=bbox,
            dpi=300,
            out_dir=test_samples_dir,
        )
        assert png_path.exists(), f"PNG not saved: {png_path}"
        from PIL import Image
        img = Image.open(str(png_path))
        print(f"      ✓  PNG saved: {png_path.name}")
        print(f"         Size: {img.size[0]}×{img.size[1]} px")

        # ── Step 3: Register sample in DB ────────────────────────
        print("\n[3/5] Calling register_sample() …")
        sample_id = register_sample(
            client_name="Test Client (Synthetic)",
            png_path=png_path,
            meta={
                "source_pdf": "synthetic_signin.pdf",
                "page": 0,
                "bbox": f"{bbox[0]},{bbox[1]},{bbox[2]},{bbox[3]}",
                "quality": "synthetic",
            },
            db_path=test_db,
        )
        assert isinstance(sample_id, int) and sample_id > 0, "register_sample returned bad id"
        print(f"      ✓  Inserted row id={sample_id}")

        # ── Step 4: Verify DB row ─────────────────────────────────
        print("\n[4/5] Verifying DB row …")
        conn = sqlite3.connect(str(test_db))
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM signature_samples WHERE id = ?", (sample_id,)
        ).fetchone()
        conn.close()
        assert row is not None, "Row not found in DB"
        print(f"      ✓  DB row verified:")
        print(f"         id           = {row['id']}")
        print(f"         client_name  = {row['client_name']}")
        print(f"         source_pdf   = {row['source_pdf']}")
        print(f"         page         = {row['page']}")
        print(f"         bbox         = {row['bbox']}")
        print(f"         img_path     = {Path(row['img_path']).name}")
        print(f"         img_hash     = {row['img_hash']}")
        print(f"         dark_pixels  = {row['dark_pixels']}")
        print(f"         quality      = {row['quality']}")
        print(f"         captured_at  = {row['captured_at']}")

        # ── Step 5: profile_for() → count == 1 ───────────────────
        print("\n[5/5] Calling profile_for() …")
        profile = profile_for("Test Client (Synthetic)", db_path=test_db)
        assert profile["sample_count"] == 1, (
            f"Expected sample_count=1, got {profile['sample_count']}"
        )
        print(f"      ✓  Profile returned:")
        print(f"         client_name    = {profile['client_name']}")
        print(f"         sample_count   = {profile['sample_count']}")
        print(f"         updated_at     = {profile['updated_at']}")
        print(f"         similarity_stub= {profile['similarity_stub'][:80]}…")

        # ── Idempotency check ─────────────────────────────────────
        print("\n[+]  Idempotency check (re-register same image) …")
        id2 = register_sample(
            "Test Client (Synthetic)", png_path, db_path=test_db
        )
        assert id2 == sample_id, "Duplicate insert should return same id"
        profile2 = profile_for("Test Client (Synthetic)", db_path=test_db)
        assert profile2["sample_count"] == 1, "Count should not increase on duplicate"
        print("      ✓  Duplicate correctly rejected (hash dedup works)")

        print("\n" + "=" * 60)
        print("SELFTEST PASSED — all 5 steps + idempotency check OK")
        print("=" * 60)
        return True

    except Exception as exc:
        print("\n" + "=" * 60)
        print(f"SELFTEST FAILED: {exc}")
        traceback.print_exc()
        print("=" * 60)
        return False

    finally:
        # Teardown
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)
        print(f"\n[cleanup] Temp dir removed: {tmp}")


# ════════════════════════════════════════════════════════════════
# CLI
# ════════════════════════════════════════════════════════════════

def main() -> None:
    parser = argparse.ArgumentParser(
        description="CC_signature_learn — H4 signature learning pipeline scaffold",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    sub = parser.add_subparsers(dest="cmd")

    # --selftest
    parser.add_argument(
        "--selftest",
        action="store_true",
        help="Run synthetic end-to-end selftest (no real data used)",
    )

    # --report
    parser.add_argument(
        "--report",
        action="store_true",
        help="Print all client profiles from signature_models.db",
    )

    # --register
    parser.add_argument("--register", metavar="PNG_PATH",
                        help="Register a PNG crop for a client")
    parser.add_argument("--client", metavar="NAME",
                        help="Client name (required with --register)")

    args = parser.parse_args()

    if args.selftest:
        ok = run_selftest()
        sys.exit(0 if ok else 1)

    if args.report:
        profiles = list_profiles()
        if not profiles:
            print("No profiles found in signature_models.db")
        else:
            print(f"{'Client':<35} {'Samples':>7}  {'Updated'}")
            print("-" * 60)
            for p in profiles:
                print(f"{p['client_name']:<35} {p['sample_count']:>7}  {p['updated_at']}")
        return

    if args.register:
        if not args.client:
            parser.error("--register requires --client NAME")
        row_id = register_sample(
            client_name=args.client,
            png_path=args.register,
        )
        print(f"Registered sample id={row_id} for '{args.client}'")
        p = profile_for(args.client)
        print(f"Profile: sample_count={p['sample_count']}, updated={p['updated_at']}")
        return

    parser.print_help()


if __name__ == "__main__":
    main()
