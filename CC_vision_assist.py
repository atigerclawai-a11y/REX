"""
CC_vision_assist.py — AI Vision fallback for unmatched OCR rows
================================================================
Phase 5 self-improving learning loop component.

When Tesseract + fuzzy matching can't identify a client (confidence < threshold),
this module passes the name-crop image to Claude Vision for a second opinion.

If Claude Vision succeeds:
  1. The correct client name is recorded in goj_menu_learning.json
  2. Future OCR runs will match that OCR string without calling Vision again
  3. The existing DB record is updated with the resolved client_id

Usage (standalone):
    python CC_vision_assist.py --pdf signin_samples/808_doc...pdf
    python CC_vision_assist.py --reprocess  # fix unmatched DB rows from last N days

Called from CC_signin_ocr.py:
    from CC_vision_assist import vision_match_client
    client_id, name = vision_match_client(name_crop_img, all_clients, learning_path)
"""

import base64
import io
import json
import logging
import sqlite3
from pathlib import Path
from typing import Optional

logger = logging.getLogger("rex.vision_assist")

REX_DIR       = Path(__file__).resolve().parent
DB_PATH       = Path.home() / "Documents" / "goj files" / "dashboard" / "auth_tracker.db"
LEARNING_PATH = REX_DIR / "goj_menu_learning.json"


def _img_to_b64(pil_img) -> str:
    """Convert PIL image to base64 PNG string for Claude Vision API."""
    buf = io.BytesIO()
    pil_img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


def vision_match_client(
    name_crop_img,          # PIL Image of the name column crop
    all_clients: list,      # [(client_id, name), ...] from clients table
    learning_path: Path = LEARNING_PATH,
    api_key: Optional[str] = None,
) -> tuple:
    """
    Use Claude Vision to identify a client name from a sign-in sheet crop.

    Returns:
        (client_id, matched_name) on success
        (None, None) on failure or if API unavailable
    """
    try:
        import anthropic
    except ImportError:
        logger.warning("anthropic package not available — skipping Vision assist")
        return None, None

    # Load API key
    if not api_key:
        api_key = _load_api_key()
    if not api_key:
        logger.warning("No Anthropic API key found — skipping Vision assist")
        return None, None

    # Build client name list for the prompt (no PHI leaves local — names only)
    client_names = [name for _, name in all_clients]
    names_block = "\n".join(sorted(client_names))

    img_b64 = _img_to_b64(name_crop_img)

    client = anthropic.Anthropic(api_key=api_key)

    try:
        resp = client.messages.create(
            model="claude-haiku-4-5-20251001",   # cheapest Vision model, fast
            max_tokens=100,
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/png",
                            "data": img_b64,
                        }
                    },
                    {
                        "type": "text",
                        "text": (
                            "This is a cropped name cell from an adult day care attendance sheet. "
                            "The text may be handwritten or printed in English or Russian. "
                            "Read the name in this image and find the CLOSEST MATCH from the list below. "
                            "Reply with ONLY the exact matching name from the list, or UNKNOWN if you can't tell.\n\n"
                            f"NAME LIST:\n{names_block}"
                        )
                    }
                ]
            }]
        )

        answer = resp.content[0].text.strip()
        if answer == "UNKNOWN" or not answer:
            return None, None

        # Find exact match in client list
        answer_lower = answer.lower()
        for cid, cname in all_clients:
            if cname.lower() == answer_lower:
                return cid, cname

        # Fuzzy fallback on Vision's answer
        from difflib import SequenceMatcher
        best_cid, best_score, best_name = None, 0.0, ""
        for cid, cname in all_clients:
            s = SequenceMatcher(None, answer_lower, cname.lower()).ratio()
            if s > best_score:
                best_score = s
                best_cid = cid
                best_name = cname

        if best_score >= 0.75:
            return best_cid, best_name

        return None, None

    except Exception as e:
        logger.warning("Vision API call failed: %s", e)
        return None, None


def learn_correction(ocr_text: str, correct_name: str, learning_path: Path = LEARNING_PATH):
    """
    Persist an OCR→correct_name mapping to the learning store.
    Thread-unsafe (OK for single-process use).
    """
    if not ocr_text or not correct_name:
        return

    data = {}
    if learning_path.exists():
        try:
            data = json.loads(learning_path.read_text())
        except Exception:
            data = {}

    if "client_name_map" not in data:
        data["client_name_map"] = {}

    key = ocr_text.strip().upper()
    if data["client_name_map"].get(key) != correct_name:
        data["client_name_map"][key] = correct_name
        learning_path.write_text(json.dumps(data, ensure_ascii=False, indent=2))
        logger.info("Learning store updated: %r -> %r", key, correct_name)


def reprocess_unmatched(
    days: int = 7,
    max_rows: int = 200,
    db_path: Path = DB_PATH,
    learning_path: Path = LEARNING_PATH,
    api_key: Optional[str] = None,
):
    """
    Find unmatched rows from the past N days, re-OCR their source PDFs
    using Vision assist, and update the DB + learning store.

    This is the offline batch learning loop — run manually or nightly.
    """
    from CC_signin_ocr import (
        pdf_to_images, detect_rows, extract_name_and_sig_regions,
        ocr_name, _is_header_row, match_client_id,
    )

    conn = sqlite3.connect(str(db_path))
    all_clients = conn.execute(
        "SELECT client_id, name FROM clients WHERE active=1"
    ).fetchall()

    # Fetch unmatched rows from recent runs
    rows = conn.execute("""
        SELECT DISTINCT source_pdf FROM client_signatures
        WHERE client_id IS NULL
          AND confidence BETWEEN 0.25 AND 0.44
          AND created_at >= datetime('now', ?)
        LIMIT ?
    """, (f"-{days} days", max_rows)).fetchall()
    conn.close()

    source_pdfs = [r[0] for r in rows if r[0] and Path(r[0]).exists()]
    logger.info("Reprocessing %d PDFs with Vision assist...", len(source_pdfs))

    fixed_total = 0

    for pdf_path_str in source_pdfs:
        pdf_path = Path(pdf_path_str)
        try:
            imgs = pdf_to_images(pdf_path, dpi=150)
        except Exception as e:
            logger.warning("Could not load %s: %s", pdf_path.name, e)
            continue

        for img in imgs:
            rows_detected = detect_rows(img)
            for row in rows_detected:
                name_crop, _ = extract_name_and_sig_regions(row["row_img"], img.width)
                raw = ocr_name(name_crop)
                if not raw.strip() or _is_header_row(raw):
                    continue

                cid, score = match_client_id(raw, db_path)
                if cid:
                    continue  # now matches — threshold may have changed

                if score < 0.25 or score > 0.44:
                    continue  # out of near-miss zone

                # Try Vision
                vision_cid, vision_name = vision_match_client(
                    name_crop, all_clients, learning_path, api_key=api_key
                )

                if vision_cid:
                    learn_correction(raw, vision_name, learning_path)
                    fixed_total += 1
                    logger.info("Vision fixed: %r -> %r (cid=%s)", raw, vision_name, vision_cid)

    logger.info("Vision reprocess complete — fixed %d rows", fixed_total)
    return fixed_total


def _load_api_key() -> Optional[str]:
    """Load Anthropic API key from Hermes config (local only, never logged)."""
    config_path = Path.home() / ".hermes" / "profiles" / "cloud" / "config.yaml"
    if config_path.exists():
        try:
            import yaml
            cfg = yaml.safe_load(config_path.read_text())
            # Traverse nested config for anthropic api_key
            providers = cfg.get("providers", {})
            for p in providers.values():
                if isinstance(p, dict):
                    key = p.get("api_key", "")
                    if key.startswith("sk-ant-"):
                        return key
        except Exception:
            pass

    # Fallback: environment variable
    import os
    return os.environ.get("ANTHROPIC_API_KEY")


# ── CLI entry point ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    import sys

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    parser = argparse.ArgumentParser(description="Vision-assist learning loop for sign-in OCR")
    parser.add_argument("--reprocess", action="store_true",
                        help="Reprocess unmatched rows from past 7 days using Vision")
    parser.add_argument("--days", type=int, default=7,
                        help="How many days back to look (default: 7)")
    parser.add_argument("--max", type=int, default=200,
                        help="Max source PDFs to reprocess (default: 200)")
    args = parser.parse_args()

    if args.reprocess:
        n = reprocess_unmatched(days=args.days, max_rows=args.max)
        print(f"Done. {n} rows fixed and added to learning store.")
    else:
        parser.print_help()
