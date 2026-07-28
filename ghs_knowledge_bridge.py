#!/usr/bin/env python3
"""
GHS Knowledge Bridge — MCP Server
═══════════════════════════════════
Bridges Obsidian vault, NotebookLM handoffs, and business memory
into a single MCP toolset for Hermes Agent.

Exposes:
  - obsidian_read      — Read a note from the vault
  - obsidian_search    — Full-text search across vault  
  - obsidian_list      — List notes in vault
  - obsidian_write     — Create/update a note
  - notebooklm_status  — Check latest handoff freshness
  - knowledge_integrity — Run integrity check
  - business_memory    — Read/write business memory JSON
"""

import json, os, sys, re
from datetime import datetime
from pathlib import Path

# ── Paths ────────────────────────────────────────────────────────────────────
VAULT_PATH = Path.home() / "Documents" / "GHS-Vault"
NOTEBOOKLM_PATH = Path.home() / ".hermes-cloud" / "mcp"
BUSINESS_MEMORY = Path.home() / "Desktop" / "REX" / "higgsfield_business_memory.json"
KEY_FILES = [
    "Masha Voice Agent.md",
    "BBG Social.md",
    "Hermes Perpetual Memory.md",
    "Hermes Session Brief.md",
]

# ── Scope + redaction ─────────────────────────────────────────────────────────
# The vault (Perpetual Memory, notes) and NotebookLM handoffs are shared memory.
# LOCAL build reads/writes them in FULL. CLOUD build reads/writes REDACTED — private
# info stripped — so the cloud never sees or persists raw secrets/PHI. Same pattern
# as the organizer's ORG_SCOPE. Default = local (full).
KNOWLEDGE_SCOPE = os.environ.get("KNOWLEDGE_SCOPE", "local").strip().lower()
CLOUD_BACKUP_PREFIX = "Cloud Backups/"  # cloud writes land here, never clobbering canonical private notes

_REDACT_PATTERNS = [
    (re.compile(r'sk-[A-Za-z0-9._-]{10,}'), '[REDACTED_KEY]'),
    (re.compile(r'key_[A-Za-z0-9]{10,}'), '[REDACTED_KEY]'),
    (re.compile(r'AIza[A-Za-z0-9_-]{20,}'), '[REDACTED_KEY]'),
    (re.compile(r'xai-[A-Za-z0-9]{10,}'), '[REDACTED_KEY]'),
    (re.compile(r'\b\d{6,}:[A-Za-z0-9_-]{20,}\b'), '[REDACTED_TOKEN]'),      # telegram bot tokens
    (re.compile(r'[Bb]earer\s+[A-Za-z0-9._-]{10,}'), 'Bearer [REDACTED]'),
    (re.compile(r'\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b'), '[REDACTED_PHONE]'),
    (re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b'), '[REDACTED_EMAIL]'),
    (re.compile(r'\bclient_id[:\s=]+\d+', re.I), 'client_id [REDACTED]'),
    (re.compile(r'\b\d{3}-\d{2}-\d{4}\b'), '[REDACTED_SSN]'),
]
# Lines mentioning clinical/PHI markers get withheld entirely in cloud scope, because
# arbitrary patient NAMES can't be caught by regex — so a PHI line is dropped, not half-masked.
_PHI_LINE = re.compile(r'\b(patient|PHI|medicaid|medicare|DOB|date of birth|diagnosis|'
                       r'\bSSN\b|insurance id|member id|prescription|clinical)\b', re.I)


def _redact(text: str) -> str:
    if not isinstance(text, str):
        return text
    out = []
    for line in text.split('\n'):
        red = line
        for pat, repl in _REDACT_PATTERNS:
            red = pat.sub(repl, red)
        if _PHI_LINE.search(red):
            red = '[REDACTED — PHI line withheld from cloud scope]'
        out.append(red)
    return '\n'.join(out)


def _maybe(text):
    """Redact in cloud scope; return full content in local scope."""
    return _redact(text) if KNOWLEDGE_SCOPE == "cloud" else text


def _maybe_obj(obj):
    if KNOWLEDGE_SCOPE != "cloud":
        return obj
    if isinstance(obj, str):
        return _redact(obj)
    if isinstance(obj, list):
        return [_maybe_obj(x) for x in obj]
    if isinstance(obj, dict):
        return {k: _maybe_obj(v) for k, v in obj.items()}
    return obj

# ── Tool Handlers ────────────────────────────────────────────────────────────

def obsidian_read(path: str) -> dict:
    """Read a markdown note from the Obsidian vault."""
    full_path = VAULT_PATH / path
    if not full_path.exists():
        # Try fuzzy match
        matches = list(VAULT_PATH.rglob(f"*{path}*"))
        if len(matches) == 1:
            full_path = matches[0]
        elif matches:
            matched = [str(m.relative_to(VAULT_PATH)) for m in matches[:5]]
            return {"error": f"Multiple matches: {matched}"}
        else:
            return {"error": f"Note not found: {path}"}
    
    content = full_path.read_text(encoding='utf-8')
    return {
        "path": str(full_path.relative_to(VAULT_PATH)),
        "size": len(content),
        "lines": content.count('\n') + 1,
        "scope": KNOWLEDGE_SCOPE,
        "content": _maybe(content)
    }


def obsidian_search(query: str, limit: int = 10) -> dict:
    """Full-text search across all markdown notes in the vault."""
    results = []
    for md_file in VAULT_PATH.rglob("*.md"):
        try:
            content = md_file.read_text(encoding='utf-8')
            if query.lower() in content.lower():
                # Find the matching lines
                lines = content.split('\n')
                matches = []
                for i, line in enumerate(lines):
                    if query.lower() in line.lower():
                        ctx_start = max(0, i-1)
                        ctx_end = min(len(lines), i+2)
                        matches.append({
                            "line": i+1,
                            "context": _maybe('\n'.join(lines[ctx_start:ctx_end]))
                        })
                
                results.append({
                    "file": str(md_file.relative_to(VAULT_PATH)),
                    "matches": len(matches),
                    "snippets": matches[:3]
                })
                if len(results) >= limit:
                    break
        except Exception:
            continue
    
    return {"query": query, "found": len(results), "results": results}


def obsidian_list(folder: str = "") -> dict:
    """List markdown notes in the vault or a subfolder."""
    search_path = VAULT_PATH / folder if folder else VAULT_PATH
    if not search_path.exists():
        return {"error": f"Folder not found: {folder}"}
    
    notes = []
    for md_file in sorted(search_path.rglob("*.md")):
        stat = md_file.stat()
        notes.append({
            "path": str(md_file.relative_to(VAULT_PATH)),
            "size": stat.st_size,
            "modified": datetime.fromtimestamp(stat.st_mtime).isoformat()
        })
    
    return {"folder": folder or "/", "count": len(notes), "notes": notes[:50]}


def obsidian_write(path: str, content: str) -> dict:
    """Create or overwrite a note in the vault.
    CLOUD scope: content is redacted AND redirected under 'Cloud Backups/' so a cloud
    write can never overwrite the canonical private notes the local build maintains."""
    if KNOWLEDGE_SCOPE == "cloud":
        content = _redact(content)
        if not path.startswith(CLOUD_BACKUP_PREFIX):
            path = CLOUD_BACKUP_PREFIX + path
    full_path = VAULT_PATH / path
    full_path.parent.mkdir(parents=True, exist_ok=True)
    full_path.write_text(content, encoding='utf-8')
    return {
        "path": str(full_path.relative_to(VAULT_PATH)),
        "size": len(content),
        "scope": KNOWLEDGE_SCOPE,
        "written": True
    }


def notebooklm_status() -> dict:
    """Check NotebookLM handoff status."""
    NOTEBOOKLM_PATH.mkdir(parents=True, exist_ok=True)
    
    handoffs = sorted(NOTEBOOKLM_PATH.glob("handoff_*.md"), reverse=True)
    latest = handoffs[0] if handoffs else None
    
    return {
        "handoff_dir": str(NOTEBOOKLM_PATH),
        "total_handoffs": len(handoffs),
        "latest": {
            "file": latest.name if latest else None,
            "size": latest.stat().st_size if latest else 0,
            "modified": datetime.fromtimestamp(latest.stat().st_mtime).isoformat() if latest else None,
            "age_hours": round((datetime.now().timestamp() - latest.stat().st_mtime) / 3600, 1) if latest else None
        } if latest else None,
        "all_handoffs": [h.name for h in handoffs[:10]]
    }


def knowledge_integrity() -> dict:
    """Run a knowledge integrity check across all sources."""
    results = {
        "timestamp": datetime.now().isoformat(),
        "obsidian": {},
        "notebooklm": {},
        "business_memory": {},
    }
    
    # Obsidian
    vault_exists = VAULT_PATH.exists()
    results["obsidian"]["vault_exists"] = vault_exists
    if vault_exists:
        key_status = {}
        for kf in KEY_FILES:
            match = list(VAULT_PATH.rglob(kf))
            if match:
                f = match[0]
                age_days = (datetime.now().timestamp() - f.stat().st_mtime) / 86400
                key_status[kf] = {
                    "found": True,
                    "path": str(f.relative_to(VAULT_PATH)),
                    "age_days": round(age_days, 1),
                    "stale": age_days > 7
                }
            else:
                key_status[kf] = {"found": False}
        results["obsidian"]["key_files"] = key_status
        results["obsidian"]["total_notes"] = len(list(VAULT_PATH.rglob("*.md")))
    
    # NotebookLM
    nb = notebooklm_status()
    results["notebooklm"] = nb
    
    # Business memory
    if BUSINESS_MEMORY.exists():
        try:
            bm = json.loads(BUSINESS_MEMORY.read_text())
            results["business_memory"] = {
                "exists": True,
                "version": bm.get("version"),
                "last_updated": bm.get("last_updated"),
                "size_bytes": BUSINESS_MEMORY.stat().st_size,
                "foh_categories": len(bm.get("foh", {}).get("menu", {}).get("categories", [])),
                "faq_count": len(bm.get("foh", {}).get("faq", [])),
            }
        except Exception as e:
            results["business_memory"] = {"exists": True, "error": str(e)}
    else:
        results["business_memory"] = {"exists": False}
    
    # Overall health
    issues = []
    if vault_exists:
        for kf, status in results["obsidian"]["key_files"].items():
            if not status["found"]:
                issues.append(f"MISSING: {kf}")
            elif status.get("stale"):
                issues.append(f"STALE: {kf} ({status['age_days']} days old)")
    
    if not results["business_memory"]["exists"]:
        issues.append("MISSING: business_memory.json")
    
    results["health"] = "OK" if not issues else f"{len(issues)} issues"
    results["issues"] = issues
    
    return results


def business_memory_read(section: str = "") -> dict:
    """Read business memory JSON, optionally filtered by section."""
    if not BUSINESS_MEMORY.exists():
        return {"error": "Business memory not found"}
    
    bm = json.loads(BUSINESS_MEMORY.read_text())
    
    if section:
        data = bm.get(section, {})
        return {"section": section, "scope": KNOWLEDGE_SCOPE, "data": _maybe_obj(data)}
    
    return {
        "version": bm.get("version"),
        "last_updated": bm.get("last_updated"),
        "sections": list(bm.keys()),
    }


def business_memory_write(section: str, data: dict) -> dict:
    """Update a section of the business memory JSON."""
    if not BUSINESS_MEMORY.exists():
        return {"error": "Business memory not found"}
    
    bm = json.loads(BUSINESS_MEMORY.read_text())
    bm[section] = data
    bm["last_updated"] = datetime.now().strftime("%Y-%m-%d")
    
    BUSINESS_MEMORY.write_text(json.dumps(bm, indent=2, ensure_ascii=False))
    return {"section": section, "updated": True, "version": bm.get("version")}


# ── MCP Server ───────────────────────────────────────────────────────────────

HANDLERS = {
    "obsidian_read": obsidian_read,
    "obsidian_search": obsidian_search,
    "obsidian_list": obsidian_list,
    "obsidian_write": obsidian_write,
    "notebooklm_status": notebooklm_status,
    "knowledge_integrity": knowledge_integrity,
    "business_memory_read": business_memory_read,
    "business_memory_write": business_memory_write,
}

TOOL_SCHEMAS = {
    "obsidian_read": {
        "description": "Read a markdown note from the Obsidian vault (~/Documents/GHS-Vault/)",
        "parameters": {
            "path": {"type": "string", "description": "Relative path to the note (e.g. 'Masha KB.md')"}
        }
    },
    "obsidian_search": {
        "description": "Full-text search across all markdown notes in the Obsidian vault",
        "parameters": {
            "query": {"type": "string", "description": "Search query"},
            "limit": {"type": "integer", "description": "Max results (default 10)"}
        }
    },
    "obsidian_list": {
        "description": "List markdown notes in the vault or a subfolder",
        "parameters": {
            "folder": {"type": "string", "description": "Subfolder path (empty for root)"}
        }
    },
    "obsidian_write": {
        "description": "Create or overwrite a markdown note in the Obsidian vault",
        "parameters": {
            "path": {"type": "string", "description": "Relative path for the note"},
            "content": {"type": "string", "description": "Markdown content"}
        }
    },
    "notebooklm_status": {
        "description": "Check NotebookLM handoff freshness and count",
        "parameters": {}
    },
    "knowledge_integrity": {
        "description": "Run full knowledge integrity check across Obsidian, NotebookLM, and business memory",
        "parameters": {}
    },
    "business_memory_read": {
        "description": "Read business memory JSON (~/Desktop/REX/higgsfield_business_memory.json)",
        "parameters": {
            "section": {"type": "string", "description": "Section to read (foh, business, hashtag_bank, etc.) — empty for summary"}
        }
    },
    "business_memory_write": {
        "description": "Update a section of the business memory JSON",
        "parameters": {
            "section": {"type": "string", "description": "Section name to update"},
            "data": {"type": "object", "description": "Data to write to the section"}
        }
    },
}


def main():
    """MCP JSON-RPC bridge with auto-shutdown on stdin close."""
    import signal, select
    
    def _check_stdin_ready(timeout=60):
        """Return True if data available on stdin within timeout."""
        r, _, _ = select.select([sys.stdin], [], [], timeout)
        return bool(r)
    
    while True:
        if not _check_stdin_ready(60):
            # No request for 60s — exit cleanly, no zombie
            break
        line_raw = sys.stdin.readline()
        if not line_raw:
            # stdin closed (EOF) — exit cleanly
            break
        line = line_raw.strip()
        if not line:
            continue

if __name__ == "__main__":
    main()
