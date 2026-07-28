"""
rex_documents.py — Document Management for REX

Handles:
  • Downloading email attachments from Gmail and routing to correct folders
  • Staff medical portfolio (per-employee documents)
  • Compliance vault (audit files, chairman/Vlad only)
  • Member document portfolios
  • GOJ member data from Google Sheets (via goj_live_data.json)

Document folder structure:
  REX/documents/
    staff/
      medical/          ← staff medical PDFs
      inservice/        ← in-service logs
      compliance/       ← per-employee compliance docs
    compliance/
      audit/            ← fire drill, P&P (restricted)
      site_visits/      ← SWH, MJHS, etc.
    signins/            ← GOJ scanner sign-in sheet scans
    menu/               ← menu scans
    members/            ← member authorization docs (per member name)
"""

import os
import json
import base64
import logging
import re
import hashlib
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict, Any

logger = logging.getLogger("rex.documents")

REX_DIR = Path(__file__).resolve().parent.parent
DOCS_DIR = REX_DIR / "documents"
GOJ_DATA_PATH = REX_DIR / "data" / "goj_live_data.json"

# ── Document routing rules ──────────────────────────────────────────────────

# Email messages to process and where to route their attachments
EMAIL_ROUTING = [
    {
        "message_id":   "19d67a0b629b3296",
        "description":  "Staff Medical PDFs",
        "category":     "staff_medical",
        "dest_folder":  DOCS_DIR / "staff" / "medical",
        "access":       ["chairman", "admin", "director"],
        "file_types":   [".pdf"],
        "watermark":    False,
    },
    {
        "message_id":   "19d67a070114bc35",
        "description":  "Employee Medical + Inservice Due Dates",
        "category":     "staff_inservice",
        "dest_folder":  DOCS_DIR / "staff" / "inservice",
        "access":       ["chairman", "admin", "director"],
        "file_types":   [".docx", ".pdf"],
        "watermark":    False,
    },
    {
        "message_id":   "19d3d8cd43414708",
        "description":  "Audit Files (Policies & Procedures, Fire Drill)",
        "category":     "compliance_audit",
        "dest_folder":  DOCS_DIR / "compliance" / "audit",
        "access":       ["chairman"],  # chairman + Vlad only per Allen's note
        "file_types":   [".pdf"],
        "watermark":    True,  # Allen requested watermarks
    },
    {
        "message_id":   "19d4ea0c94462588",
        "description":  "SWH Annual Site Visit Package",
        "category":     "site_visit",
        "dest_folder":  DOCS_DIR / "compliance" / "site_visits" / "SWH_Apr2026",
        "access":       ["chairman", "admin", "director"],
        "file_types":   [".pdf", ".docx", ".jpg", ".jpeg", ".png"],
        "watermark":    False,
    },
    # ── SWH Site Visit Package Parts 2 & 3 ────────────────────────────────────
    {
        "message_id":   "19d4ea02e321b2e5",
        "description":  "SWH Site Visit – Part 2 (HCBS, Licenses, Menu, PCSP forms)",
        "category":     "site_visit",
        "dest_folder":  DOCS_DIR / "compliance" / "site_visits" / "SWH_Apr2026",
        "access":       ["chairman", "admin", "director"],
        "file_types":   [".pdf", ".docx", ".jpg", ".jpeg", ".png"],
        "watermark":    False,
        "extract_pcsp": True,   # pcsp form.pdf → also copy to members/pcsp/
    },
    {
        "message_id":   "19d4e9fbb106b557",
        "description":  "SWH Site Visit – Part 3 (Insurance, Workers Comp, W9, Driver List)",
        "category":     "site_visit",
        "dest_folder":  DOCS_DIR / "compliance" / "site_visits" / "SWH_Apr2026",
        "access":       ["chairman", "admin", "director"],
        "file_types":   [".pdf", ".docx", ".jpg", ".jpeg", ".png"],
        "watermark":    False,
    },
    # ── HCBS Policies & Training ───────────────────────────────────────────────
    {
        "message_id":   "19cfbff518f09545",
        "description":  "HCBS P&P and Training (VillageCare VNS Compliance)",
        "category":     "compliance_audit",
        "dest_folder":  DOCS_DIR / "compliance" / "audit",
        "access":       ["chairman", "admin", "director"],
        "file_types":   [".pdf", ".docx"],
        "watermark":    False,
    },
    # ── Sign-in and Menu Scans ─────────────────────────────────────────────────
    {
        "message_id":   "19d5604f33622807",
        "description":  "Sign-in Sheet Scan Apr 3 (Sheet 1)",
        "category":     "signin_scan",
        "dest_folder":  DOCS_DIR / "signins" / "2026-04-03",
        "access":       ["chairman", "admin", "director", "staff"],
        "file_types":   [".pdf"],
        "watermark":    False,
    },
    {
        "message_id":   "19d560489c99e9e9",
        "description":  "Sign-in Sheet Scan Apr 3 (Sheet 2)",
        "category":     "signin_scan",
        "dest_folder":  DOCS_DIR / "signins" / "2026-04-03",
        "access":       ["chairman", "admin", "director", "staff"],
        "file_types":   [".pdf"],
        "watermark":    False,
    },
    {
        "message_id":   "19d5720c403b2736",
        "description":  "Menu Scan Mar 30",
        "category":     "menu_scan",
        "dest_folder":  DOCS_DIR / "menu" / "2026-03-30",
        "access":       ["chairman", "admin", "director", "staff"],
        "file_types":   [".pdf"],
        "watermark":    False,
    },
    {
        "message_id":   "19d56572c638493f",
        "description":  "Document Scan Mar 30 (Part 1)",
        "category":     "general_scan",
        "dest_folder":  DOCS_DIR / "signins" / "2026-03-30",
        "access":       ["chairman", "admin", "director"],
        "file_types":   [".pdf"],
        "watermark":    False,
    },
]

# ── Member portfolio folder names (per plan) ────────────────────────────────
MEMBER_DOC_PLANS = ["SWH", "VNS", "Anthem", "VCM", "Eld_Serve", "Aetna", "MetroPlus"]

# Known member authorization document filenames (from SWH site visit emails)
# These get copied to members/pcsp/ after routing
MEMBER_AUTH_FILENAMES = {
    "pcsp form.pdf":        "members/pcsp/SWH_PCSP_Forms_2026.pdf",
    "member rights.JPG":    "members/pcsp/SWH_Member_Rights_2026.jpg",
    "coo 2026 new.pdf":     "members/pcsp/COO_Authorization_2026.pdf",
}

# Staff name → normalized filename map (for medical PDFs)
STAFF_PDF_MAP = {
    "alisher.pdf":               "Alisher",
    "allen khiger.pdf":          "Allen_Khiger",
    "andriy sheremet.pdf":       "Andriy_Sheremet",
    "gennadi gugilov.pdf":       "Gennadi_Gugilov",
    "klimova inna.pdf":          "Klimova_Inna",
    "liudmila zhuk.pdf":         "Liudmila_Zhuk",
    "natalie altman.pdf":        "Natalie_Altman",
    "oleg tikhonov.pdf":         "Oleg_Tikhonov",
    "ravil aleev.pdf":           "Ravil_Aleev",
    "svitlana rozmetanyuk.pdf":  "Svitlana_Rozmetanyuk",
    "vadim kononenko.pdf":       "Vadim_Kononenko",
    "valerian.pdf":              "Valerian",
    "vladimir khiger.pdf":       "Vladimir_Khiger",
}


def _get_gmail_service():
    """Get authenticated Gmail API service from rex_gmail."""
    try:
        from .rex_gmail import _get_service
        return _get_service()
    except Exception as e:
        logger.error(f"Failed to get Gmail service: {e}")
        return None


def download_attachment(service, message_id: str, attachment_filename: str, dest_folder: Path) -> Optional[Path]:
    """
    Download a specific attachment from a Gmail message.
    Returns the saved file path, or None on failure.
    """
    try:
        msg = service.users().messages().get(userId='me', id=message_id, format='full').execute()
        parts = msg.get('payload', {}).get('parts', [])

        # Flatten nested parts
        def flatten_parts(parts):
            flat = []
            for p in parts:
                if p.get('parts'):
                    flat.extend(flatten_parts(p['parts']))
                else:
                    flat.append(p)
            return flat

        all_parts = flatten_parts(parts)

        for part in all_parts:
            fn = part.get('filename', '')
            if not fn:
                continue
            if fn.lower() != attachment_filename.lower():
                continue

            att_id = part.get('body', {}).get('attachmentId')
            if not att_id:
                # Inline data
                data = part.get('body', {}).get('data', '')
            else:
                att = service.users().messages().attachments().get(
                    userId='me', messageId=message_id, id=att_id
                ).execute()
                data = att.get('data', '')

            if not data:
                continue

            # Decode base64url
            file_data = base64.urlsafe_b64decode(data + '==')
            dest_folder.mkdir(parents=True, exist_ok=True)
            out_path = dest_folder / fn
            out_path.write_bytes(file_data)
            logger.info(f"Downloaded: {fn} → {out_path}")
            return out_path

    except Exception as e:
        logger.error(f"download_attachment({message_id}, {attachment_filename}): {e}")
    return None


def download_all_message_attachments(service, message_id: str, dest_folder: Path, file_types: list = None) -> List[Path]:
    """Download all attachments from a message to dest_folder."""
    try:
        msg = service.users().messages().get(userId='me', id=message_id, format='full').execute()

        def flatten_parts(parts):
            flat = []
            for p in parts:
                if p.get('parts'):
                    flat.extend(flatten_parts(p['parts']))
                else:
                    flat.append(p)
            return flat

        all_parts = flatten_parts(msg.get('payload', {}).get('parts', []))
        saved = []

        for part in all_parts:
            fn = part.get('filename', '')
            if not fn:
                continue
            ext = Path(fn).suffix.lower()
            if file_types and ext not in file_types:
                continue
            if ext in ('.svg',):  # skip Outlook icons
                continue

            att_id = part.get('body', {}).get('attachmentId')
            if att_id:
                att = service.users().messages().attachments().get(
                    userId='me', messageId=message_id, id=att_id
                ).execute()
                data = att.get('data', '')
            else:
                data = part.get('body', {}).get('data', '')

            if not data:
                continue

            file_data = base64.urlsafe_b64decode(data + '==')
            dest_folder.mkdir(parents=True, exist_ok=True)
            out_path = dest_folder / fn
            out_path.write_bytes(file_data)
            saved.append(out_path)
            logger.info(f"Saved: {fn} ({len(file_data):,} bytes)")

        return saved

    except Exception as e:
        logger.error(f"download_all_message_attachments({message_id}): {e}")
        return []


def run_document_routing() -> Dict[str, Any]:
    """
    Download and route all known email attachments to their correct folders.
    Also copies member auth docs (PCSP forms, COO, member rights) to members/pcsp/.
    Returns a summary of what was processed.
    """
    svc = _get_gmail_service()
    if not svc:
        return {"error": "Gmail service not available", "processed": []}

    results = []
    for rule in EMAIL_ROUTING:
        msg_id = rule["message_id"]
        dest = rule["dest_folder"]
        file_types = rule.get("file_types", [])
        logger.info(f"Processing: {rule['description']}")

        saved = download_all_message_attachments(svc, msg_id, dest, file_types)

        # If this rule flags PCSP extraction, copy member auth docs to members/pcsp/
        if rule.get("extract_pcsp"):
            pcsp_dir = DOCS_DIR / "members" / "pcsp"
            pcsp_dir.mkdir(parents=True, exist_ok=True)
            for f in saved:
                canonical = MEMBER_AUTH_FILENAMES.get(f.name.lower())
                if not canonical:
                    canonical = MEMBER_AUTH_FILENAMES.get(f.name)
                if canonical:
                    import shutil
                    dest_path = DOCS_DIR / canonical
                    dest_path.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(f, dest_path)
                    logger.info(f"PCSP copy: {f.name} → {dest_path}")

        results.append({
            "message_id":  msg_id,
            "description": rule["description"],
            "category":    rule["category"],
            "dest":        str(dest),
            "files_saved": [f.name for f in saved],
            "count":       len(saved),
        })

    # Ensure member plan subfolders exist
    members_dir = DOCS_DIR / "members"
    for plan in MEMBER_DOC_PLANS:
        (members_dir / plan).mkdir(parents=True, exist_ok=True)
    (members_dir / "pcsp").mkdir(parents=True, exist_ok=True)

    # Save manifest
    manifest_path = DOCS_DIR / "manifest.json"
    manifest = {
        "generated": datetime.now().isoformat(),
        "routes": results,
        "total_files": sum(r["count"] for r in results),
    }
    manifest_path.write_text(json.dumps(manifest, indent=2))

    return manifest


def list_documents(category: str = None, access_role: str = "staff") -> List[Dict]:
    """
    List available documents, filtered by access role.
    """
    docs = []
    if not DOCS_DIR.exists():
        return docs

    ROLE_ACCESS = {
        "chairman": {"staff_medical", "staff_inservice", "compliance_audit", "site_visit",
                     "signin_scan", "menu_scan", "general_scan"},
        "admin":    {"staff_medical", "staff_inservice", "site_visit", "signin_scan", "menu_scan"},
        "director": {"staff_medical", "staff_inservice", "site_visit", "signin_scan", "menu_scan"},
        "staff":    {"signin_scan", "menu_scan"},
    }
    allowed = ROLE_ACCESS.get(access_role, set())

    for rule in EMAIL_ROUTING:
        cat = rule["category"]
        if category and cat != category:
            continue
        if cat not in allowed:
            continue
        dest = rule["dest_folder"]
        if not dest.exists():
            continue
        for f in sorted(dest.iterdir()):
            if f.is_file() and not f.name.startswith('.'):
                docs.append({
                    "filename":    f.name,
                    "category":    cat,
                    "description": rule["description"],
                    "path":        str(f.relative_to(REX_DIR)),
                    "size":        f.stat().st_size,
                    "modified":    datetime.fromtimestamp(f.stat().st_mtime).isoformat(),
                })
    return docs


def get_staff_medical_docs() -> Dict[str, List[Dict]]:
    """Return dict of staff_name → list of their medical documents."""
    medical_dir = DOCS_DIR / "staff" / "medical"
    inservice_dir = DOCS_DIR / "staff" / "inservice"
    portfolio = {}

    for d, doc_type in [(medical_dir, "Medical"), (inservice_dir, "Inservice")]:
        if not d.exists():
            continue
        for f in sorted(d.iterdir()):
            if not f.is_file():
                continue
            # Normalize name from filename
            stem = f.stem.lower().replace('_', ' ').strip()
            matched_staff = STAFF_PDF_MAP.get(f.name.lower(), f.stem.replace('_', ' '))
            if matched_staff not in portfolio:
                portfolio[matched_staff] = []
            portfolio[matched_staff].append({
                "filename": f.name,
                "type":     doc_type,
                "size":     f.stat().st_size,
                "path":     str(f.relative_to(REX_DIR)),
                "modified": datetime.fromtimestamp(f.stat().st_mtime).isoformat(),
            })

    return portfolio


# ── GOJ Member Data ─────────────────────────────────────────────────────────

def load_goj_data() -> Optional[Dict]:
    """Load the live GOJ member data from JSON (written by goj_import.py)."""
    if not GOJ_DATA_PATH.exists():
        return None
    try:
        with open(GOJ_DATA_PATH) as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Failed to load GOJ data: {e}")
        return None


def get_goj_stats() -> Dict[str, Any]:
    """Return GOJ statistics for the dashboard. Falls back to known stats if JSON not loaded."""
    data = load_goj_data()
    if data and "stats" in data:
        return {
            **data["stats"],
            "meta": data.get("meta", {}),
            "source": "live"
        }

    # Fallback: hardcoded from our Google Sheets analysis (April 12, 2026)
    return {
        "source": "cached",
        "meta": {
            "generated": "2026-04-12",
            "totalMembers": 425,
            "note": "Run tools/goj_import.py to refresh from Google Sheets"
        },
        "plans": {
            "Anthem":     253,
            "Eld Serve":  88,
            "VCM":        30,
            "SWH":        24,
            "VNS":        20,
            "Aetna":       4,
            "Pr.Pay":      3,
            "MetroPlus":   2,
            "Empire":      1,
        },
        "transport": {"van": 357, "self": 68},
        "cdpap": 216,
        "byDay": {"M": 150, "T": 146, "W": 166, "TH": 159, "F": 206, "Su": 64},
        "dailyRosters": {
            "M1": 77, "M2": 73,
            "T1": 86, "T2": 60,
            "W1": 78, "W2": 88,
            "TH1": 94, "TH2": 65,
            "F1": 98, "F2": 108,
            "Su": 64
        },
        "aprilByDay": {
            "1": 154, "2": 139, "3": 193,
            "5": 59,  "6": 140, "7": 132,
            "8": 164, "9": 145
        }
    }


def get_goj_members(plan: str = None, day: str = None, search: str = None) -> List[Dict]:
    """Return GOJ member list with optional filtering."""
    data = load_goj_data()
    if not data:
        return []
    members = data.get("members", [])
    if plan:
        members = [m for m in members if m.get("plan", "").lower() == plan.lower()]
    if day:
        members = [m for m in members if m.get("days", {}).get(day.upper())]
    if search:
        s = search.lower()
        members = [m for m in members if s in m.get("name", "").lower()]
    return members


# ── Member Portfolio (per-member document management) ────────────────────────

def _member_folder_name(name: str) -> str:
    """Normalize a member name to a safe folder name."""
    return re.sub(r'[^a-zA-Z0-9_\-]', '_', name.strip()).strip('_')


def get_member_portfolios(search: str = None) -> Dict[str, Any]:
    """
    Return member document portfolios.
    Combines:
      - Per-member folders under documents/members/<name>/
      - Shared PCSP docs in documents/members/pcsp/
      - COO and authorization docs in documents/members/pcsp/
    """
    members_dir = DOCS_DIR / "members"
    pcsp_dir = members_dir / "pcsp"
    portfolios = {}

    # Shared compliance docs (PCSP forms, COO, member rights — apply to all SWH members)
    shared_docs = []
    if pcsp_dir.exists():
        for f in sorted(pcsp_dir.iterdir()):
            if f.is_file() and not f.name.startswith('.'):
                shared_docs.append({
                    "filename": f.name,
                    "type":     "PCSP/Authorization",
                    "shared":   True,
                    "size":     f.stat().st_size,
                    "path":     str(f.relative_to(REX_DIR)),
                    "modified": datetime.fromtimestamp(f.stat().st_mtime).isoformat(),
                })

    # Per-member folders
    if members_dir.exists():
        for d in sorted(members_dir.iterdir()):
            if not d.is_dir() or d.name in ('pcsp',) + tuple(MEMBER_DOC_PLANS):
                continue
            member_name = d.name.replace('_', ' ')
            if search and search.lower() not in member_name.lower():
                continue
            files = []
            for f in sorted(d.iterdir()):
                if f.is_file() and not f.name.startswith('.'):
                    files.append({
                        "filename": f.name,
                        "type":     "Authorization",
                        "shared":   False,
                        "size":     f.stat().st_size,
                        "path":     str(f.relative_to(REX_DIR)),
                        "modified": datetime.fromtimestamp(f.stat().st_mtime).isoformat(),
                    })
            if files:
                portfolios[member_name] = files

    # Cross-reference with GOJ member list
    goj_members = get_goj_members(search=search)
    member_names_from_goj = {m["name"] for m in goj_members}

    return {
        "shared_docs": shared_docs,
        "per_member": portfolios,
        "total_members_with_docs": len(portfolios),
        "shared_doc_count": len(shared_docs),
        "goj_member_count": len(goj_members),
        "note": "Shared docs (PCSP forms, COO, member rights) apply to all SWH members. "
                "Per-member folders shown for members with individual uploaded documents.",
    }


def upload_member_document(member_name: str, filename: str, file_data: bytes) -> Dict[str, Any]:
    """
    Save a document to a member's individual portfolio folder.
    Creates the folder if it doesn't exist.
    """
    folder_name = _member_folder_name(member_name)
    member_dir = DOCS_DIR / "members" / folder_name
    member_dir.mkdir(parents=True, exist_ok=True)

    # Sanitize filename
    safe_fn = re.sub(r'[^a-zA-Z0-9_\-.]', '_', filename.strip())
    dest = member_dir / safe_fn
    dest.write_bytes(file_data)
    logger.info(f"Member doc uploaded: {member_name}/{safe_fn} ({len(file_data):,} bytes)")
    return {
        "member":   member_name,
        "filename": safe_fn,
        "path":     str(dest.relative_to(REX_DIR)),
        "size":     len(file_data),
    }
