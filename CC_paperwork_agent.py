#!/usr/bin/env python3
"""
CC_paperwork_agent.py — GHS Insurance & Business Paperwork Agent
Port 8003 · Works with CC_doc_overseer.py (CC_ naming, whitelist, scan trigger)

Capabilities:
  - Business profile store (EIN, addresses, policy numbers, contacts)
  - Insurance form assistant (disability, liability, workers comp, E&O, umbrella)
  - Document intake: classify scanned PDFs → CC_ rename → file → registry → OCD scan
  - Q&A: answer insurance/business questions using stored context
  - Telegram alerts on every filing action

Usage:
  python CC_paperwork_agent.py             # start API on port 8003
  python CC_paperwork_agent.py --profile   # print current business profile
  python CC_paperwork_agent.py --registry  # print filing registry
  python CC_paperwork_agent.py --scan      # trigger OCD overseer scan
"""

import argparse, base64, json, os, shutil, subprocess, sys, urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# ── Deps ──────────────────────────────────────────────────────────────────────
try:
    import anthropic
except ImportError:
    anthropic = None

try:
    from fastapi import FastAPI, HTTPException, UploadFile, File
    from fastapi.responses import JSONResponse
    from pydantic import BaseModel
    import uvicorn
    HAS_FASTAPI = True
except ImportError:
    HAS_FASTAPI = False

# ── Paths ─────────────────────────────────────────────────────────────────────
REX           = Path.home() / "Desktop" / "REX"
PAPERWORK_DIR = REX / "paperwork"
PROFILE_FILE  = REX / "CC_paperwork_profile.json"
REGISTRY_FILE = REX / "CC_paperwork_registry.json"
OCD_SCRIPT    = REX / "CC_doc_overseer.py"
LOG_DIR       = REX / "logs"
TELEGRAM_API  = "https://api.telegram.org/bot{}/sendMessage"
CHAT_ID       = "5587703834"

FOLDERS = {
    "disability_insurance": PAPERWORK_DIR / "insurance" / "disability",
    "liability_insurance":  PAPERWORK_DIR / "insurance" / "liability",
    "workers_comp":         PAPERWORK_DIR / "insurance" / "workers_comp",
    "general_insurance":    PAPERWORK_DIR / "insurance" / "general",
    "contracts":            PAPERWORK_DIR / "contracts",
    "licenses":             PAPERWORK_DIR / "licenses",
    "forms":                PAPERWORK_DIR / "forms",
    "correspondence":       PAPERWORK_DIR / "correspondence",
    "uncategorized":        PAPERWORK_DIR / "uncategorized",
}

# ── Form templates ────────────────────────────────────────────────────────────
FORM_TEMPLATES = {
    "disability_insurance": {
        "name": "Disability Insurance Application",
        "description": "Short-term and long-term disability coverage for GHS/GOJ",
        "fields": [
            ("business_name",        "Business legal name"),
            ("ein",                  "Employer Identification Number (EIN)"),
            ("business_address",     "Business address"),
            ("business_phone",       "Business phone"),
            ("business_type",        "Type of business / industry"),
            ("num_employees",        "Number of full-time employees"),
            ("annual_payroll",       "Annual payroll"),
            ("owner_name",           "Owner / applicant name"),
            ("owner_dob",            "Owner date of birth"),
            ("owner_ssn_last4",      "Last 4 digits of owner SSN (stored locally only)"),
            ("existing_coverage",    "Existing disability coverage (if any)"),
            ("coverage_amount",      "Desired monthly benefit amount"),
            ("elimination_period",   "Elimination period (days before benefits begin)"),
            ("benefit_period",       "Benefit period (months/years)"),
            ("effective_date",       "Requested effective date"),
        ]
    },
    "general_liability": {
        "name": "General Liability Insurance Application",
        "description": "Commercial general liability coverage",
        "fields": [
            ("business_name",        "Business legal name"),
            ("dba",                  "DBA name (if any)"),
            ("ein",                  "EIN"),
            ("business_address",     "Business address"),
            ("business_phone",       "Business phone"),
            ("business_email",       "Business email"),
            ("years_in_business",    "Years in operation"),
            ("business_type",        "Business description / operations"),
            ("num_employees",        "Number of employees"),
            ("annual_revenue",       "Annual gross revenue"),
            ("premises_owned",       "Own or lease premises?"),
            ("premises_sqft",        "Square footage of premises"),
            ("prior_claims",         "Any claims in the last 5 years?"),
            ("coverage_limit",       "Desired coverage limit"),
            ("effective_date",       "Requested effective date"),
        ]
    },
    "workers_comp": {
        "name": "Workers Compensation Insurance Application",
        "description": "Workers comp coverage for GHS / GOJ employees",
        "fields": [
            ("business_name",        "Business legal name"),
            ("ein",                  "EIN"),
            ("business_address",     "Business address"),
            ("business_phone",       "Business phone"),
            ("business_type",        "Business description"),
            ("num_employees",        "Number of employees"),
            ("employee_classifications", "Job classifications and payroll by class"),
            ("annual_payroll",       "Total annual payroll"),
            ("prior_carrier",        "Prior carrier (if any)"),
            ("prior_claims",         "Claims in the last 5 years"),
            ("effective_date",       "Requested effective date"),
        ]
    },
    "umbrella": {
        "name": "Umbrella / Excess Liability Application",
        "description": "Umbrella coverage layered over primary policies",
        "fields": [
            ("business_name",        "Business legal name"),
            ("ein",                  "EIN"),
            ("business_address",     "Business address"),
            ("underlying_policies",  "List of underlying policies (GL, auto, WC)"),
            ("underlying_limits",    "Limits on each underlying policy"),
            ("desired_umbrella_limit","Desired umbrella limit"),
            ("annual_revenue",       "Annual gross revenue"),
            ("prior_claims",         "Any claims in the last 5 years?"),
            ("effective_date",       "Requested effective date"),
        ]
    },
    "e_and_o": {
        "name": "Errors & Omissions (Professional Liability)",
        "description": "E&O coverage for professional services",
        "fields": [
            ("business_name",        "Business legal name"),
            ("ein",                  "EIN"),
            ("business_address",     "Business address"),
            ("services_description", "Detailed description of professional services"),
            ("num_professionals",    "Number of licensed professionals"),
            ("annual_revenue",       "Annual gross revenue from professional services"),
            ("prior_claims",         "Any claims or complaints in the last 5 years?"),
            ("retroactive_date",     "Desired retroactive date"),
            ("coverage_limit",       "Desired coverage limit"),
            ("effective_date",       "Requested effective date"),
        ]
    },
}

# ── Defaults ──────────────────────────────────────────────────────────────────
DEFAULT_PROFILE = {
    "ghs": {
        "name":           "Gold Health Systems",
        "dba":            "",
        "ein":            "",
        "address":        "",
        "phone":          "",
        "email":          "atigerclawai@gmail.com",
        "owner_name":     "Alejandro",
        "years_in_business": "",
        "business_type":  "Healthcare / Adult Day Care Services",
    },
    "goj": {
        "name":           "Garden of Joy",
        "address":        "Brooklyn, NY",
        "num_employees":  "",
        "annual_payroll": "",
        "annual_revenue": "",
        "num_clients":    425,
        "license_number": "",
    },
    "insurance_policies": [],
    "notes": [],
}

# ── Helpers ───────────────────────────────────────────────────────────────────
def _ensure_dirs():
    for d in FOLDERS.values():
        d.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)

def _load_profile() -> dict:
    if PROFILE_FILE.exists():
        return json.loads(PROFILE_FILE.read_text())
    return DEFAULT_PROFILE.copy()

def _save_profile(p: dict):
    PROFILE_FILE.write_text(json.dumps(p, indent=2))

def _load_registry() -> list:
    if REGISTRY_FILE.exists():
        return json.loads(REGISTRY_FILE.read_text())
    return []

def _save_registry(r: list):
    REGISTRY_FILE.write_text(json.dumps(r, indent=2))

def _telegram(msg: str):
    token = os.environ.get("HERMES_BOT_TOKEN", "")
    if not token:
        return
    try:
        data = json.dumps({"chat_id": CHAT_ID, "text": msg,
                           "parse_mode": "HTML"}).encode()
        req = urllib.request.Request(
            TELEGRAM_API.format(token), data=data,
            headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=10)
    except Exception as e:
        print(f"[paperwork] telegram error: {e}")

def _cc_filename(doc_type: str, description: str, ext: str = ".pdf") -> str:
    """Generate a CC_-prefixed filename compliant with OCD naming rules."""
    date = datetime.now().strftime("%Y-%m-%d")
    safe = description.lower().replace(" ", "_").replace("/", "-")[:40]
    return f"CC_{date}_{doc_type}_{safe}{ext}"

def _trigger_ocd_scan():
    """Run OCD overseer in report mode so it validates new files."""
    if OCD_SCRIPT.exists():
        try:
            subprocess.run(
                [sys.executable, str(OCD_SCRIPT), "--report"],
                capture_output=True, text=True, timeout=30)
        except Exception:
            pass

def _file_document(src_path: Path, doc_type: str, description: str) -> dict:
    """Move a document to the correct folder with CC_ naming. Log to registry."""
    _ensure_dirs()
    folder = FOLDERS.get(doc_type, FOLDERS["uncategorized"])
    ext    = src_path.suffix or ".pdf"
    fname  = _cc_filename(doc_type, description, ext)
    dest   = folder / fname

    # Avoid overwrite
    counter = 1
    while dest.exists():
        fname = _cc_filename(doc_type, f"{description}_{counter}", ext)
        dest  = folder / fname
        counter += 1

    shutil.copy2(src_path, dest)

    entry = {
        "filed_at":    datetime.now(timezone.utc).isoformat(),
        "original":    str(src_path),
        "filed_as":    str(dest),
        "doc_type":    doc_type,
        "description": description,
    }
    reg = _load_registry()
    reg.append(entry)
    _save_registry(reg)

    _telegram(
        f"📄 <b>Paperwork Agent</b> — Document filed\n"
        f"Type: {doc_type}\n"
        f"File: {fname}\n"
        f"Folder: paperwork/{doc_type}")

    _trigger_ocd_scan()
    return entry

def _classify_document(file_path: Path) -> dict:
    """Use Claude Vision to classify a scanned document."""
    if anthropic is None:
        return {"doc_type": "uncategorized", "description": "unclassified_document",
                "confidence": 0.0, "summary": "anthropic package not installed"}
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        return {"doc_type": "uncategorized", "description": "unclassified_document",
                "confidence": 0.0, "summary": "ANTHROPIC_API_KEY not set"}

    try:
        with open(file_path, "rb") as f:
            b64 = base64.standard_b64encode(f.read()).decode()
        ext = file_path.suffix.lower()
        media_type = {"pdf": "application/pdf", ".pdf": "application/pdf",
                      ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
                      ".png": "image/png"}.get(ext, "application/pdf")

        client = anthropic.Anthropic(api_key=api_key)
        resp = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=512,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image",
                     "source": {"type": "base64", "media_type": media_type, "data": b64}},
                    {"type": "text", "text": (
                        "You are classifying a business document for Gold Health Systems (GHS), "
                        "an adult day care operator in Brooklyn, NY. "
                        "Classify this document into exactly one of: "
                        "disability_insurance, liability_insurance, workers_comp, general_insurance, "
                        "contracts, licenses, forms, correspondence, uncategorized. "
                        "Also provide a brief description (5 words max, snake_case) for the filename "
                        "and a one-sentence summary. "
                        "Respond with JSON only: "
                        "{\"doc_type\": \"...\", \"description\": \"...\", "
                        "\"confidence\": 0.0-1.0, \"summary\": \"...\"}"
                    )}
                ]
            }]
        )
        return json.loads(resp.content[0].text.strip())
    except Exception as e:
        return {"doc_type": "uncategorized", "description": "unclassified_document",
                "confidence": 0.0, "summary": str(e)}

def _fill_form(form_type: str) -> dict:
    """Return a form pre-filled from the business profile."""
    template = FORM_TEMPLATES.get(form_type)
    if not template:
        return {"error": f"Unknown form type: {form_type}. "
                         f"Available: {list(FORM_TEMPLATES.keys())}"}
    profile = _load_profile()
    ghs = profile.get("ghs", {})
    goj = profile.get("goj", {})

    # Auto-fill from stored profile
    prefill = {
        "business_name":  ghs.get("name", ""),
        "dba":            ghs.get("dba", ""),
        "ein":            ghs.get("ein", ""),
        "business_address": ghs.get("address", "") or goj.get("address", ""),
        "business_phone": ghs.get("phone", ""),
        "business_email": ghs.get("email", ""),
        "business_type":  ghs.get("business_type", ""),
        "years_in_business": ghs.get("years_in_business", ""),
        "num_employees":  goj.get("num_employees", ""),
        "annual_payroll": goj.get("annual_payroll", ""),
        "annual_revenue": goj.get("annual_revenue", ""),
        "owner_name":     ghs.get("owner_name", ""),
    }

    fields_out = []
    missing    = []
    for field_id, field_label in template["fields"]:
        value = prefill.get(field_id, "")
        fields_out.append({"id": field_id, "label": field_label, "value": value})
        if not value:
            missing.append({"id": field_id, "label": field_label})

    return {
        "form_type":  form_type,
        "form_name":  template["name"],
        "description":template["description"],
        "fields":     fields_out,
        "missing":    missing,
        "prefilled":  len(fields_out) - len(missing),
        "total":      len(fields_out),
        "note":       (f"{len(missing)} field(s) need input. "
                       "PUT /profile to update stored values and avoid re-entering next time.")
                      if missing else "All fields pre-filled from profile.",
    }

# ── FastAPI ───────────────────────────────────────────────────────────────────
if HAS_FASTAPI:
    app = FastAPI(title="CC Paperwork Agent", version="1.0.0")

    class ProfileUpdate(BaseModel):
        section: str          # "ghs" or "goj"
        updates: dict

    class FormSubmit(BaseModel):
        form_type:   str
        field_values: dict    # {field_id: value}

    class QueryRequest(BaseModel):
        question: str

    @app.get("/health")
    def health():
        return {"service": "paperwork_agent", "status": "ok",
                "port": 8003, "forms": list(FORM_TEMPLATES.keys())}

    @app.get("/api/forms")
    def list_forms():
        return [{"id": k, "name": v["name"], "description": v["description"]}
                for k, v in FORM_TEMPLATES.items()]

    @app.get("/api/form/{form_type}")
    def get_form(form_type: str):
        result = _fill_form(form_type)
        if "error" in result:
            raise HTTPException(400, result["error"])
        return result

    @app.post("/api/form/submit")
    def submit_form(req: FormSubmit):
        """Save a completed form to the forms folder."""
        template = FORM_TEMPLATES.get(req.form_type)
        if not template:
            raise HTTPException(400, f"Unknown form type: {req.form_type}")
        date   = datetime.now().strftime("%Y-%m-%d")
        fname  = f"CC_{date}_{req.form_type}_completed.json"
        dest   = FOLDERS["forms"] / fname
        FOLDERS["forms"].mkdir(parents=True, exist_ok=True)
        payload = {
            "form_type":    req.form_type,
            "form_name":    template["name"],
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "fields":       req.field_values,
        }
        dest.write_text(json.dumps(payload, indent=2))
        reg = _load_registry()
        reg.append({"filed_at": datetime.now(timezone.utc).isoformat(),
                    "original": None, "filed_as": str(dest),
                    "doc_type": "forms", "description": req.form_type})
        _save_registry(reg)
        _telegram(f"📋 <b>Paperwork Agent</b> — Form saved\n"
                  f"Form: {template['name']}\nFile: {fname}")
        _trigger_ocd_scan()
        return {"status": "saved", "file": str(dest)}

    @app.get("/api/profile")
    def get_profile():
        return _load_profile()

    @app.put("/api/profile")
    def update_profile(req: ProfileUpdate):
        """Update a section of the business profile."""
        profile = _load_profile()
        if req.section not in profile:
            profile[req.section] = {}
        profile[req.section].update(req.updates)
        _save_profile(profile)
        return {"status": "updated", "section": req.section}

    @app.post("/api/intake")
    async def intake_document(file: UploadFile = File(...),
                              doc_type: Optional[str] = None,
                              description: Optional[str] = None):
        """Receive a scanned document. Classify it and file it."""
        _ensure_dirs()
        tmp = REX / "logs" / f"_intake_tmp_{file.filename}"
        try:
            tmp.write_bytes(await file.read())
            if not doc_type:
                classified = _classify_document(tmp)
                doc_type   = classified.get("doc_type", "uncategorized")
                description = description or classified.get("description", "uploaded_doc")
                summary     = classified.get("summary", "")
            else:
                summary = ""
            entry = _file_document(tmp, doc_type, description or "uploaded_doc")
            return {"status": "filed", **entry, "ai_summary": summary}
        finally:
            if tmp.exists():
                tmp.unlink()

    @app.get("/api/registry")
    def get_registry():
        return _load_registry()

    @app.post("/api/query")
    def answer_query(req: QueryRequest):
        """Answer an insurance or business question using stored profile context."""
        if anthropic is None:
            raise HTTPException(500, "anthropic package not installed")
        api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        if not api_key:
            raise HTTPException(500, "ANTHROPIC_API_KEY not set")
        profile = _load_profile()
        client  = anthropic.Anthropic(api_key=api_key)
        resp = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1024,
            system=(
                "You are an insurance and business operations expert for Gold Health Systems (GHS), "
                "an adult day care operator in Brooklyn, NY with 425 clients. "
                "You have access to the company's business profile. "
                "Answer questions concisely and practically. "
                "Always flag if a question requires a licensed professional (attorney, insurance broker). "
                f"\n\nBusiness profile:\n{json.dumps(profile, indent=2)}"
            ),
            messages=[{"role": "user", "content": req.question}]
        )
        return {"question": req.question, "answer": resp.content[0].text}

    @app.post("/api/ocd-scan")
    def run_ocd_scan():
        """Manually trigger the OCD doc overseer scan."""
        if not OCD_SCRIPT.exists():
            raise HTTPException(404, "CC_doc_overseer.py not found")
        result = subprocess.run(
            [sys.executable, str(OCD_SCRIPT), "--report"],
            capture_output=True, text=True, timeout=30)
        return {"output": result.stdout, "stderr": result.stderr}

# ── CLI ───────────────────────────────────────────────────────────────────────
def _cli():
    ap = argparse.ArgumentParser(description="GHS Paperwork Agent")
    ap.add_argument("--profile",  action="store_true", help="Print business profile")
    ap.add_argument("--registry", action="store_true", help="Print filing registry")
    ap.add_argument("--scan",     action="store_true", help="Run OCD overseer scan")
    ap.add_argument("--forms",    action="store_true", help="List available form types")
    ap.add_argument("--port",     type=int, default=8003)
    args = ap.parse_args()

    if args.profile:
        print(json.dumps(_load_profile(), indent=2))
        return
    if args.registry:
        reg = _load_registry()
        print(f"{len(reg)} filed document(s):")
        for e in reg[-20:]:
            print(f"  [{e['doc_type']}] {Path(e['filed_as']).name}  —  {e['filed_at'][:10]}")
        return
    if args.scan:
        _trigger_ocd_scan()
        print("OCD scan triggered.")
        return
    if args.forms:
        for k, v in FORM_TEMPLATES.items():
            print(f"  {k:25s} — {v['name']}")
        return

    if not HAS_FASTAPI:
        print("fastapi/uvicorn not installed. Run: pip install fastapi uvicorn")
        sys.exit(1)

    _ensure_dirs()
    print(f"CC Paperwork Agent starting on port {args.port}")
    print(f"Profile:  {PROFILE_FILE}")
    print(f"Registry: {REGISTRY_FILE}")
    print(f"Docs:     {PAPERWORK_DIR}")
    uvicorn.run(app, host="0.0.0.0", port=args.port)

if __name__ == "__main__":
    _cli()
