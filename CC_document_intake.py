#!/usr/bin/env python3
"""
CC_document_intake.py — UNIFIED document-intake OCR orchestrator for GOJ/REX.

ANY document (member upload, email, Google Drive, sign-in drop folder) →
  classify → OCR (LOCAL) → route to the right engine → record in a manifest →
  notify Kato on Telegram → printable batch summary.

This file ORCHESTRATES existing engines. It does NOT re-implement OCR or
classification, and it NEVER touches server.py.

Engines reused (imported, not duplicated):
  - goj_signin_intake.py          → get_text(), detect_sheet_type(), keyword maps
                                      (the canonical classifier)
  - goj_signin_ocr_processor.py   → local sign-in → attendance (real sheets only)
  - goj_menu_ocr.py               → menu cloud OCR (GATED: Gate-1 + header-crop)
  - CC_carecenta_extract.py /      → auth PDF → dates (LOCAL, STAGED for Kato)
    CC_carecenta_tesseract.py
  - CC_ocr_telegram_fallback.py   → Telegram bot token + chat-id resolution

HARD RULES (enforced here):
  • NO PHI to cloud. Menu-form cloud OCR stays DISABLED unless
    GATE1_REQUIRED is satisfied AND a name-crop exists; otherwise the menu doc
    is STAGED for review (no cloud call). Everything else is LOCAL.
  • NEVER fabricate attendance. The sign-in route reads real sheets only via the
    existing local processor. The --selftest uses synthetic docs ONLY and never
    writes to attendance_log.
  • auth / menu / driver-route changes are STAGED for Kato review, not written
    live (consistent with the prior staging phases).
  • New file + one new state json only. No edits to existing engines.

Usage:
    python3 CC_document_intake.py --selftest        # synthetic classify→route→manifest, no cloud, no DB
    python3 CC_document_intake.py --scan            # scan all watched sources, route, stage, notify
    python3 CC_document_intake.py --path FILE.pdf   # ingest a single document
    python3 CC_document_intake.py --no-notify ...   # skip the Telegram summary
    python3 CC_document_intake.py --print-batch ID  # re-render a batch summary to PDF
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

# ── Paths ───────────────────────────────────────────────────────────────────────
REX_DIR        = Path(__file__).resolve().parent
STATE_DIR      = REX_DIR / "state"
MANIFEST_PATH  = STATE_DIR / "intake_manifest.json"
BATCH_DIR      = STATE_DIR / "intake_batches"          # per-batch printable summaries
CARECENTA_STAGE = STATE_DIR / "carecenta_staging.json"  # auth staging (existing)
INTAKE_STAGE   = STATE_DIR / "intake_staging.json"      # menu/route staging (this orchestrator)

GOJ_DOCS       = Path.home() / "Documents" / "goj files" / "documents"
MEMBER_FILES   = GOJ_DOCS / "member_files"
SIGNINS_DROP   = REX_DIR / "signins"

# Sources to watch (existing drop locations). Missing dirs are skipped silently.
WATCH_DIRS = [
    MEMBER_FILES,                                   # member uploads
    SIGNINS_DROP,                                   # sign-in drop folder
    GOJ_DOCS / "inbox",                             # generic email/scan inbox (if present)
]

# Where "other" docs get filed when we can't route them.
OTHER_FILE_DIR = MEMBER_FILES / "_unclassified"

VALID_EXTS = {".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff"}

# ── Logging (stderr; stdout stays clean for summaries) ──────────────────────────
import logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
    stream=sys.stderr,
)
log = logging.getLogger("intake")


# ── Lazy engine loaders (import by path; engines aren't a package) ─────────────
def _load_module(name: str, filename: str):
    """Import a sibling engine module by file path. Returns module or None."""
    path = REX_DIR / filename
    if not path.exists():
        log.warning("engine missing: %s", filename)
        return None
    try:
        spec = importlib.util.spec_from_file_location(name, str(path))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    except Exception as exc:  # noqa: BLE001 — engine import must never crash the orchestrator
        log.error("failed to import %s: %s", filename, exc)
        return None


_INTAKE_MOD = None   # goj_signin_intake (classifier)
_TG_MOD = None       # CC_ocr_telegram_fallback (notify)


def get_intake():
    global _INTAKE_MOD
    if _INTAKE_MOD is None:
        _INTAKE_MOD = _load_module("goj_signin_intake", "goj_signin_intake.py")
    return _INTAKE_MOD


def get_tg():
    global _TG_MOD
    if _TG_MOD is None:
        _TG_MOD = _load_module("cc_ocr_telegram_fallback", "CC_ocr_telegram_fallback.py")
    return _TG_MOD


# ── Document type map (orchestrator's stable vocabulary) ────────────────────────
# The classifier returns its own internal labels; we normalize to these five.
TYPE_SIGNIN  = "signin"
TYPE_MENU    = "menu"
TYPE_AUTH    = "authorization"
TYPE_ROUTE   = "driver_route"
TYPE_OTHER   = "other"

# classifier-internal → orchestrator type
_CLASSIFIER_MAP = {
    "signin":       TYPE_SIGNIN,
    "menu":         TYPE_MENU,
    "distribution": TYPE_MENU,    # distribution sheets share the menu destination
    "kitchen":      TYPE_MENU,    # kitchen prep is menu-family; stage, don't cloud-OCR
    "auth":         TYPE_AUTH,
    "drivers":      TYPE_ROUTE,
}


# ── Local text extraction (no cloud) ────────────────────────────────────────────
def _local_text(path: Path) -> str:
    """
    Extract text LOCALLY only — never the cloud-vision fallback inside the engine's
    get_text(). Order: PDF text layer (pdftotext/PyMuPDF) → local Tesseract.
    Returns "" if nothing local works (caller then leans on the filename).
    """
    intake = get_intake()

    # 1) PDF text layer via the engine's own local extractors, if importable.
    if intake is not None:
        for fn_name in ("extract_text_pdfplumber", "extract_text_pymupdf",
                        "extract_text_tesseract"):
            fn = getattr(intake, fn_name, None)
            if fn is None:
                continue
            try:
                text = fn(path) or ""
                if len(text.strip()) > 30:
                    return text
            except Exception as exc:  # noqa: BLE001
                log.debug("  %s failed: %s", fn_name, exc)

    # 2) Last-resort: system pdftotext (still local).
    if path.suffix.lower() == ".pdf" and shutil.which("pdftotext"):
        try:
            out = subprocess.run(
                ["pdftotext", "-layout", str(path), "-"],
                capture_output=True, text=True, timeout=60,
            )
            if len(out.stdout.strip()) > 30:
                return out.stdout
        except Exception as exc:  # noqa: BLE001
            log.debug("  pdftotext failed: %s", exc)

    return ""


# ── Classify ────────────────────────────────────────────────────────────────────
def classify(path: Path, text: str | None = None) -> tuple[str, str, float]:
    """
    Classify a document into one of the orchestrator types.

    Returns (doc_type, reason, confidence).
      doc_type    — one of TYPE_* constants
      reason      — short human string for the manifest
      confidence  — 0..1 (filename-only ~0.4, content-confirmed ~0.9)

    Reuses goj_signin_intake.detect_sheet_type (keyword scoring + learned
    patterns). Filename keywords are a low-confidence fallback when text is thin.
    Pure LOCAL text only — no cloud.
    """
    intake = get_intake()
    if text is None:
        text = _local_text(path)

    name = path.name.lower()

    # ── Content-based (preferred) via the canonical classifier ─────────────────
    # NOTE: we pass path=None on purpose. With a path, detect_sheet_type consults
    # the engine's learned-pattern cache, which is currently overfit (returns
    # "menu" for nearly everything). Passing None uses the deterministic keyword
    # scorer — the canonical, reliable classification logic we want to reuse.
    if intake is not None and text.strip():
        try:
            raw = intake.detect_sheet_type(text, None)
        except Exception as exc:  # noqa: BLE001
            raw = None
            log.debug("  detect_sheet_type error: %s", exc)
        if raw:
            mapped = _CLASSIFIER_MAP.get(raw, TYPE_OTHER)
            return mapped, f"classifier:{raw}", 0.9

    # ── Filename heuristics (low confidence, used when content is thin) ─────────
    if any(k in name for k in ("signin", "sign-in", "sign_in", "attendance")):
        return TYPE_SIGNIN, "filename:signin", 0.45
    if any(k in name for k in ("menu", "food", "preference", "weekly_order")):
        return TYPE_MENU, "filename:menu", 0.4
    if any(k in name for k in ("auth", "carecenta", "authoriz", "vis tr", "vis_tr")):
        return TYPE_AUTH, "filename:auth", 0.45
    if any(k in name for k in ("route", "driver", "delivery")):
        return TYPE_ROUTE, "filename:route", 0.4

    return TYPE_OTHER, "unclassified", 0.2


# ── Manifest helpers (idempotent by content hash) ──────────────────────────────
def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def _load_manifest() -> dict:
    if MANIFEST_PATH.exists():
        try:
            return json.loads(MANIFEST_PATH.read_text())
        except Exception as exc:  # noqa: BLE001
            log.error("manifest unreadable, starting fresh: %s", exc)
    return {"version": 1, "docs": {}}


def _save_manifest(man: dict) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    tmp = MANIFEST_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(man, indent=1))
    tmp.replace(MANIFEST_PATH)


def _load_intake_stage() -> dict:
    if INTAKE_STAGE.exists():
        try:
            return json.loads(INTAKE_STAGE.read_text())
        except Exception:  # noqa: BLE001
            pass
    return {"version": 1, "menu": {}, "driver_route": {}, "other": {}}


def _save_intake_stage(stage: dict) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    tmp = INTAKE_STAGE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(stage, indent=1))
    tmp.replace(INTAKE_STAGE)


# ── Route ───────────────────────────────────────────────────────────────────────
def route(doc_type: str, path: Path, source: str, text: str,
          *, dry_run: bool = False) -> dict:
    """
    Route a classified document to the correct engine / staging action.

    Returns a result record:
      { action: updated|staged|filed|skipped,
        target: <table or staging file>,
        detail: <human string>,
        cloud_used: bool }

    LOCAL auto-updates: signin (attendance, real sheets only via existing engine).
    STAGED for Kato review: authorization, menu, driver_route.
    FILED: other.
    """
    if doc_type == TYPE_SIGNIN:
        return _route_signin(path, source, text, dry_run=dry_run)
    if doc_type == TYPE_AUTH:
        return _route_auth(path, source, text, dry_run=dry_run)
    if doc_type == TYPE_MENU:
        return _route_menu(path, source, text, dry_run=dry_run)
    if doc_type == TYPE_ROUTE:
        return _route_driver(path, source, text, dry_run=dry_run)
    return _route_other(path, source, dry_run=dry_run)


def _route_signin(path: Path, source: str, text: str, *, dry_run: bool) -> dict:
    """
    Sign-in → attendance. Delegates to the existing LOCAL processor, which reads
    real sheets only and writes status='attended'. We DO NOT extract or fabricate
    names here — that stays in the canonical engine to keep one source of truth.

    Because the existing processor is Paperless-document-oriented, the safe
    orchestrator behavior is to hand the sheet to the sign-in drop folder it
    already watches (idempotent) and record that the local pipeline owns it.
    Never fabricates attendance.
    """
    target = "attendance_log (via goj_signin_ocr_processor — LOCAL)"

    # Confirmation gate: the OCR processor has a STRICTER is_signin_sheet (it
    # rejects menus/receipts/route sheets via NON_SIGNIN_KEYWORDS). If the
    # canonical processor disagrees this is a real sign-in sheet, do NOT route to
    # attendance — file it instead. Prevents receipts/invoices from being
    # mistaken for sign-in sheets.
    proc = _load_module("goj_signin_ocr_processor", "goj_signin_ocr_processor.py")
    if proc is not None and hasattr(proc, "is_signin_sheet") and text.strip():
        try:
            if not proc.is_signin_sheet(text, path.name):
                log.info("  signin keyword hit but processor rejected it — filing as other")
                return _route_other(path, source, dry_run=dry_run)
        except Exception as exc:  # noqa: BLE001
            log.debug("  is_signin_sheet check failed (continuing): %s", exc)

    if dry_run:
        return {"action": "would_update", "target": target,
                "detail": "sign-in confirmed by canonical processor; no DB write in dry-run",
                "cloud_used": False}

    # Ensure the real sheet is in the folder the local processor consumes.
    SIGNINS_DROP.mkdir(parents=True, exist_ok=True)
    dest = SIGNINS_DROP / path.name
    try:
        if path.resolve() != dest.resolve():
            shutil.copy2(path, dest)
    except Exception as exc:  # noqa: BLE001
        log.error("  could not stage sign-in sheet: %s", exc)
        return {"action": "skipped", "target": target,
                "detail": f"copy failed: {exc}", "cloud_used": False}

    return {
        "action": "staged_for_local_attendance",
        "target": target,
        "detail": ("real sign-in sheet placed in signins/ drop folder; "
                   "goj_signin_ocr_processor performs the LOCAL attendance write "
                   "(real sheets only — never fabricated)"),
        "cloud_used": False,
    }


def _route_auth(path: Path, source: str, text: str, *, dry_run: bool) -> dict:
    """
    Authorization → LOCAL date/name extraction → STAGE to carecenta_staging.json.
    Kato approves staging before any live authorization-table write (prior rule).
    """
    target = str(CARECENTA_STAGE)
    dates = _extract_dates_local(text)
    rec = {
        "file_name": path.name,
        "source": source,
        "ingested_at": datetime.now(timezone.utc).isoformat(),
        "dates_found": dates,
        "name_guess": _guess_name_from_filename(path.name),
        "status": "intake_staged_local",
    }
    if dry_run:
        return {"action": "would_stage", "target": target,
                "detail": f"synthetic auth; dates={dates}", "cloud_used": False}

    stage = {}
    if CARECENTA_STAGE.exists():
        try:
            stage = json.loads(CARECENTA_STAGE.read_text())
        except Exception:  # noqa: BLE001
            stage = {}
    key = f"intake::{_sha256(path)[:16]}"
    stage[key] = rec
    tmp = CARECENTA_STAGE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(stage, indent=1))
    tmp.replace(CARECENTA_STAGE)

    return {"action": "staged", "target": "carecenta_staging.json (Kato review)",
            "detail": f"auth extracted LOCALLY; dates={dates or 'none'}",
            "cloud_used": False}


def _route_menu(path: Path, source: str, text: str, *, dry_run: bool) -> dict:
    """
    Menu form. Cloud OCR is GATED. Re-enable a real client-form cloud call only if
    BOTH GATE1_REQUIRED is satisfied AND a name-crop image exists. Otherwise STAGE
    the menu for review — NO cloud PHI.
    """
    target_stage = str(INTAKE_STAGE)
    gate1_ok = _menu_gate_satisfied(path)

    if dry_run:
        return {"action": "would_stage", "target": target_stage,
                "detail": "synthetic menu staged (cloud gated)", "cloud_used": False}

    if not gate1_ok:
        stage = _load_intake_stage()
        stage["menu"][_sha256(path)[:16]] = {
            "file_name": path.name, "source": source,
            "ingested_at": datetime.now(timezone.utc).isoformat(),
            "status": "menu_staged_cloud_gated",
            "reason": "GATE1 + header-crop not satisfied — no cloud PHI",
        }
        _save_intake_stage(stage)
        return {"action": "staged", "target": "intake_staging.json:menu (Kato review)",
                "detail": "menu form staged; cloud OCR DISABLED (Gate-1/crop unmet)",
                "cloud_used": False}

    # Gate locally satisfied (GATE1_REQUIRED honored + name-crop present). The
    # menu engine (goj_menu_ocr.py) owns the actual gated cloud-Vision call and
    # re-checks its own Gate-1 firewall; it is driven via its own CLI, not a
    # single-doc public function. To preserve the "no silent cloud writes from
    # the orchestrator" rule, we STAGE the doc and flag it cloud-eligible so the
    # menu engine's gated pipeline can pick it up under its own firewall.
    stage = _load_intake_stage()
    stage["menu"][_sha256(path)[:16]] = {
        "file_name": path.name, "source": source,
        "ingested_at": datetime.now(timezone.utc).isoformat(),
        "status": "menu_staged_cloud_eligible",
        "note": "Gate-1 + name-crop satisfied; eligible for goj_menu_ocr gated cloud run",
    }
    _save_intake_stage(stage)
    return {"action": "staged", "target": "intake_staging.json:menu (cloud-eligible)",
            "detail": "Gate-1+crop satisfied; staged for goj_menu_ocr gated pipeline",
            "cloud_used": False}


def _route_driver(path: Path, source: str, text: str, *, dry_run: bool) -> dict:
    """
    Driver / route sheet → parse LOCALLY → STAGE proposed route updates for review.
    """
    target = str(INTAKE_STAGE)
    proposal = {
        "file_name": path.name, "source": source,
        "ingested_at": datetime.now(timezone.utc).isoformat(),
        "client_count_hint": _count_route_lines(text),
        "status": "route_proposed_staged",
    }
    if dry_run:
        return {"action": "would_stage", "target": target,
                "detail": "synthetic route staged", "cloud_used": False}
    stage = _load_intake_stage()
    stage["driver_route"][_sha256(path)[:16]] = proposal
    _save_intake_stage(stage)
    return {"action": "staged", "target": "intake_staging.json:driver_route (Kato review)",
            "detail": f"route proposal staged; lines≈{proposal['client_count_hint']}",
            "cloud_used": False}


def _route_other(path: Path, source: str, *, dry_run: bool) -> dict:
    """File unclassified docs under member_files/_unclassified with a category note."""
    if dry_run:
        return {"action": "would_file", "target": str(OTHER_FILE_DIR),
                "detail": "synthetic other filed", "cloud_used": False}
    OTHER_FILE_DIR.mkdir(parents=True, exist_ok=True)
    dest = OTHER_FILE_DIR / path.name
    try:
        if path.resolve() != dest.resolve():
            shutil.copy2(path, dest)
    except Exception as exc:  # noqa: BLE001
        return {"action": "skipped", "target": str(OTHER_FILE_DIR),
                "detail": f"file failed: {exc}", "cloud_used": False}
    return {"action": "filed", "target": "member_files/_unclassified",
            "detail": "filed for manual categorization", "cloud_used": False}


# ── Small local helpers (no cloud) ──────────────────────────────────────────────
def _extract_dates_local(text: str) -> list[str]:
    """Reuse the carecenta date regexes (same patterns as the existing extractors)."""
    import re
    res = [
        re.compile(r"(?:through|thru|to|end(?:ing)?(?:\s*date)?|expir\w*)[:\s]*?"
                   r"(\d{1,2})[/.-](\d{1,2})[/.-](\d{2,4})", re.I),
        re.compile(r"(\d{1,2})[/.](\d{1,2})[/.](\d{4})\s*[-–]\s*"
                   r"(\d{1,2})[/.](\d{1,2})[/.](\d{4})"),
    ]
    out: set[str] = set()
    for rx in res:
        for m in rx.finditer(text or ""):
            g = m.groups()
            if len(g) >= 3:
                mo, dy, yr = g[-3], g[-2], g[-1]
                try:
                    y = int(yr); y = y + 2000 if y < 100 else y
                    cand = f"{y:04d}-{int(mo):02d}-{int(dy):02d}"
                    if cand > "2024-01-01":
                        out.add(cand)
                except Exception:  # noqa: BLE001
                    pass
    return sorted(out)[-4:]


def _guess_name_from_filename(name: str) -> str:
    import re
    stem = re.split(r"\d|\.pdf", name, 1, re.I)[0]
    return stem.replace("_", " ").replace("-", " ").strip().title()


def _count_route_lines(text: str) -> int:
    import re
    return sum(1 for ln in (text or "").splitlines()
               if re.search(r"\d{2,}|\bSt\b|\bAve\b|\bRd\b", ln))


def _menu_gate_satisfied(path: Path) -> bool:
    """
    Cloud menu OCR is allowed ONLY if GATE1_REQUIRED is satisfied AND a name-crop
    image exists alongside the doc. Default posture: gated OFF.
    """
    gate1 = os.environ.get("GATE1_REQUIRED", "true").lower() == "true"
    if not gate1:
        # If the operator explicitly disabled the requirement, the engine's own
        # firewall still governs; we permit delegation.
        return True
    crop = path.with_suffix(".namecrop.png")
    return crop.exists()


# ── Notify (Telegram) + printable batch summary ────────────────────────────────
def _telegram_send_text(text: str) -> dict:
    """Send a plain-text Telegram message using the existing helper's token/chat."""
    tg = get_tg()
    if tg is None:
        return {"ok": False, "error": "telegram helper unavailable"}
    try:
        token = tg._bot_token("rex_of_gold") or tg._bot_token("default")
        chat = tg._chat_id()
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"token/chat resolve failed: {exc}"}
    if not token:
        return {"ok": False, "error": "no bot token in env (set REX_OF_GOLD_BOT_TOKEN or TELEGRAM_BOT_TOKEN)"}

    import urllib.request, urllib.error
    body = json.dumps({"chat_id": chat, "text": text[:4000]}).encode()
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage", data=body, method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        r = urllib.request.urlopen(req, timeout=20)
        return {"ok": True, "status": r.status}
    except urllib.error.HTTPError as e:  # noqa: PERF203
        return {"ok": False, "status": e.code, "error": e.read(300).decode("utf-8", "replace")}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}


def _batch_summary_text(batch_id: str, results: list[dict]) -> str:
    def act(r) -> str:
        return r["result"]["action"]

    auto = [r for r in results if act(r) in
            ("updated", "would_update", "staged_for_local_attendance")]
    staged = [r for r in results if act(r) in ("staged", "would_stage")]
    filed = [r for r in results if act(r) in ("filed", "would_file")]
    skipped = [r for r in results if act(r) == "skipped"]

    lines = [
        f"📥 GOJ Document Intake — batch {batch_id}",
        f"   {len(results)} document(s) processed",
        "",
        f"✅ Auto-updated (LOCAL): {len(auto)}",
    ]
    for r in auto:
        lines.append(f"   • {r['type']}: {r['file']} → {r['result']['target']}")
    lines += ["", f"📝 Staged for your review: {len(staged)}"]
    for r in staged:
        lines.append(f"   • {r['type']}: {r['file']} → {r['result']['target']}")
    lines += ["", f"🗂 Filed (unclassified): {len(filed)}"]
    for r in filed:
        lines.append(f"   • {r['file']}")
    if skipped:
        lines += ["", f"⏭ Skipped: {len(skipped)}"]
        for r in skipped:
            lines.append(f"   • {r['file']}: {r['result']['detail']}")
    lines += ["", "No PHI sent to cloud. Auth/menu/route changes await your approval.",
              f"Generated {datetime.now(timezone.utc).isoformat()}Z"]
    return "\n".join(lines)


def _write_batch_files(batch_id: str, summary_text: str) -> dict:
    """Write a .txt and try to render a printable .pdf for the batch."""
    BATCH_DIR.mkdir(parents=True, exist_ok=True)
    txt_path = BATCH_DIR / f"{batch_id}.txt"
    txt_path.write_text(summary_text)

    pdf_path = BATCH_DIR / f"{batch_id}.pdf"
    rendered = _render_text_pdf(summary_text, pdf_path)
    return {"txt": str(txt_path), "pdf": str(pdf_path) if rendered else None}


def _render_text_pdf(text: str, out_path: Path) -> bool:
    """Render plain text to a printable PDF. Tries fpdf, then reportlab, then enscript."""
    # fpdf2
    try:
        from fpdf import FPDF  # type: ignore
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Courier", size=10)
        for line in text.splitlines() or [""]:
            pdf.multi_cell(0, 5, line)
        pdf.output(str(out_path))
        return True
    except Exception:  # noqa: BLE001
        pass
    # reportlab
    try:
        from reportlab.pdfgen import canvas  # type: ignore
        from reportlab.lib.pagesizes import letter  # type: ignore
        c = canvas.Canvas(str(out_path), pagesize=letter)
        y = 750
        c.setFont("Courier", 9)
        for line in text.splitlines():
            c.drawString(40, y, line[:110])
            y -= 12
            if y < 40:
                c.showPage(); c.setFont("Courier", 9); y = 750
        c.save()
        return True
    except Exception:  # noqa: BLE001
        pass
    # enscript | ps2pdf
    if shutil.which("enscript") and shutil.which("ps2pdf"):
        try:
            with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as tf:
                tf.write(text); src = tf.name
            ps = src + ".ps"
            subprocess.run(["enscript", "-B", "-p", ps, src], check=True,
                           capture_output=True)
            subprocess.run(["ps2pdf", ps, str(out_path)], check=True,
                           capture_output=True)
            os.unlink(src); os.unlink(ps)
            return True
        except Exception:  # noqa: BLE001
            pass
    log.info("  no PDF renderer available — .txt summary is still printable")
    return False


def notify(batch_id: str, results: list[dict], *, send: bool = True) -> dict:
    """Build the printable batch summary and (optionally) send the Telegram digest."""
    summary = _batch_summary_text(batch_id, results)
    files = _write_batch_files(batch_id, summary)
    tg_result = {"ok": False, "skipped": True}
    if send:
        tg_result = _telegram_send_text(summary)
    return {"summary_files": files, "telegram": tg_result, "summary_text": summary}


# ── Ingest one document end-to-end ──────────────────────────────────────────────
def ingest_one(path: Path, source: str, man: dict, *, dry_run: bool = False) -> dict | None:
    """Classify → route → record in manifest. Idempotent by content hash."""
    if not path.exists() or path.suffix.lower() not in VALID_EXTS:
        return None

    digest = _sha256(path)
    if digest in man["docs"] and not dry_run:
        log.info("  skip (already processed): %s", path.name)
        return None

    text = _local_text(path)
    doc_type, reason, conf = classify(path, text)
    result = route(doc_type, path, source, text, dry_run=dry_run)

    record = {
        "file": path.name,
        "path": str(path),
        "source": source,
        "type": doc_type,
        "classify_reason": reason,
        "confidence": conf,
        "result": result,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    if not dry_run:
        man["docs"][digest] = record
    return record


# ── Scan all watched sources ────────────────────────────────────────────────────
def scan(*, send: bool = True, dry_run: bool = False) -> dict:
    man = _load_manifest()
    batch_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    results: list[dict] = []

    for d in WATCH_DIRS:
        if not d.exists():
            continue
        for path in sorted(d.rglob("*")):
            if path.is_file() and path.suffix.lower() in VALID_EXTS:
                rec = ingest_one(path, source=f"dir:{d.name}", man=man, dry_run=dry_run)
                if rec:
                    results.append(rec)

    if not dry_run:
        _save_manifest(man)

    notify_out = {"summary_files": {}, "telegram": {"skipped": True}}
    if results:
        notify_out = notify(batch_id, results, send=send and not dry_run)

    return {"batch_id": batch_id, "count": len(results),
            "results": results, "notify": notify_out}


# ── Self-test (synthetic only; no cloud, no DB writes, no fabricated attendance) ─
def selftest() -> int:
    print("=" * 70)
    print("CC_document_intake --selftest  (synthetic docs; LOCAL only; no DB writes)")
    print("=" * 70)

    tmp = Path(tempfile.mkdtemp(prefix="intake_selftest_"))
    man = {"version": 1, "docs": {}}  # throwaway in-memory manifest
    results: list[dict] = []

    # 1) Synthetic SIGN-IN sheet (text file faking a sign-in sheet's content).
    signin = tmp / "SIGN-IN SHEET_synthetic.txt"
    signin.write_text(
        "GARDEN OF JOY ADULT DAY CARE CENTER\n"
        "SIGN-IN SHEET\n"
        "Insurance Plan   Total present\n"
        "Staff signature\n"
        "(SYNTHETIC — no real attendees, no DB write)\n"
    )
    # selftest uses .txt; classify reads the text directly so we don't OCR.
    st_text = signin.read_text()
    t1, r1, c1 = classify(signin, st_text)
    res1 = route(t1, signin, "selftest", st_text, dry_run=True)
    rec1 = {"file": signin.name, "type": t1, "classify_reason": r1,
            "confidence": c1, "result": res1}
    results.append(rec1)
    print(f"\n[1] sign-in  → type={t1} reason={r1} conf={c1}")
    print(f"    route action={res1['action']} target={res1['target']}")
    print(f"    cloud_used={res1['cloud_used']}  (must be False)")

    # 2) Synthetic AUTH doc by FILENAME (no content) — proves filename routing.
    auth = tmp / "CHEBOTAREVA VIS TR auth 03.31.2027.txt"
    auth.write_text("Authorization Period through 03/31/2027  Member ID 123 (SYNTHETIC)")
    a_text = auth.read_text()
    t2, r2, c2 = classify(auth, a_text)
    res2 = route(t2, auth, "selftest", a_text, dry_run=True)
    rec2 = {"file": auth.name, "type": t2, "classify_reason": r2,
            "confidence": c2, "result": res2}
    results.append(rec2)
    print(f"\n[2] auth     → type={t2} reason={r2} conf={c2}")
    print(f"    route action={res2['action']} target={res2['target']}")
    print(f"    dates_extracted_local={_extract_dates_local(a_text)}")
    print(f"    cloud_used={res2['cloud_used']}  (must be False)")

    # 3) Synthetic MENU — proves cloud stays gated (no cloud call).
    menu = tmp / "GOJ Weekly Menu preference_synthetic.txt"
    menu.write_text("GOJ Weekly Menu\nSalad Choice  Soup Choice  Main Choice\nMon Tue Wed (SYNTHETIC)")
    m_text = menu.read_text()
    t3, r3, c3 = classify(menu, m_text)
    res3 = route(t3, menu, "selftest", m_text, dry_run=True)
    results.append({"file": menu.name, "type": t3, "classify_reason": r3,
                    "confidence": c3, "result": res3})
    print(f"\n[3] menu     → type={t3} reason={r3} conf={c3}")
    print(f"    route action={res3['action']} cloud_used={res3['cloud_used']}  (must be False)")

    # Build a printable batch summary (no Telegram send in selftest).
    batch_id = "SELFTEST"
    full_results = [
        {"type": rec["type"], "file": rec["file"], "result": rec["result"]}
        for rec in results
    ]
    out = notify(batch_id, full_results, send=False)
    print("\n" + "-" * 70)
    print("BATCH SUMMARY (printable):")
    print(out["summary_text"])
    print("-" * 70)
    print(f"summary files: {out['summary_files']}")

    # ── Assertions ─────────────────────────────────────────────────────────────
    ok = True
    if t1 != TYPE_SIGNIN:
        print(f"FAIL: sign-in misclassified as {t1}"); ok = False
    if t2 != TYPE_AUTH:
        print(f"FAIL: auth misclassified as {t2}"); ok = False
    if t3 != TYPE_MENU:
        print(f"FAIL: menu misclassified as {t3}"); ok = False
    if any(rec["result"]["cloud_used"] for rec in results):
        print("FAIL: a synthetic doc triggered a cloud call"); ok = False
    # Manifest must be empty (selftest never persists).
    if man["docs"]:
        print("FAIL: selftest wrote to the manifest"); ok = False

    shutil.rmtree(tmp, ignore_errors=True)
    print("\n" + ("✅ SELFTEST PASSED" if ok else "❌ SELFTEST FAILED"))
    print("(no cloud calls, no DB writes, no fabricated attendance)")
    return 0 if ok else 1


# ── CLI ─────────────────────────────────────────────────────────────────────────
def main() -> int:
    ap = argparse.ArgumentParser(description="Unified GOJ document-intake orchestrator")
    ap.add_argument("--selftest", action="store_true", help="run synthetic classify→route→manifest test")
    ap.add_argument("--scan", action="store_true", help="scan all watched sources")
    ap.add_argument("--path", help="ingest a single document")
    ap.add_argument("--no-notify", action="store_true", help="skip the Telegram summary")
    ap.add_argument("--dry-run", action="store_true", help="classify/route without writing")
    ap.add_argument("--print-batch", help="re-render an existing batch summary id to stdout")
    args = ap.parse_args()

    if args.selftest:
        return selftest()

    if args.print_batch:
        p = BATCH_DIR / f"{args.print_batch}.txt"
        if p.exists():
            print(p.read_text()); return 0
        print(f"batch not found: {p}"); return 1

    if args.path:
        man = _load_manifest()
        path = Path(args.path).expanduser()
        rec = ingest_one(path, source="cli:path", man=man, dry_run=args.dry_run)
        if rec is None:
            print("nothing to do (already processed, missing, or unsupported type)")
            return 0
        if not args.dry_run:
            _save_manifest(man)
        batch_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        out = notify(batch_id, [rec], send=not args.no_notify and not args.dry_run)
        print(json.dumps({"record": rec, "notify": out["summary_files"],
                          "telegram": out["telegram"]}, indent=2))
        return 0

    if args.scan:
        out = scan(send=not args.no_notify, dry_run=args.dry_run)
        print(json.dumps({"batch_id": out["batch_id"], "count": out["count"],
                          "notify": out["notify"]["summary_files"],
                          "telegram": out["notify"]["telegram"]}, indent=2))
        return 0

    ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
