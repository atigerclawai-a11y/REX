"""
backend/rex_command_center_status.py — Shared Command Center Data Layer
═══════════════════════════════════════════════════════════════════════
Rexonasence v4 · Phase 11 · Garden of Joy · Gold Health Systems

PURPOSE:
  Single data-collection module shared by BOTH command center UI modes:
    Mode A — Claude UI  (terminal, clean, fast)
    Mode B — Executive  (HTML dashboard, leadership view)

  Both modes call get_status() and receive the same data object.
  ONLY the presentation layer differs.

ARCHITECTURE:
  This module reads directly from the filesystem + SQLite.
  It does NOT depend on the FastAPI backend being up.
  If Rex backend is running, additional live data is fetched.
  If Rex backend is down, filesystem data is used as fallback.

  FastAPI mounts this as: GET /api/chairman/command-center-status
  Terminal mode calls get_status() directly.
"""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

# ── Paths ──────────────────────────────────────────────────────────────────────
HOME     = Path.home()
REX_DIR  = HOME / "Desktop" / "REX"
AUTH_DB  = HOME / "Documents" / "goj files" / "dashboard" / "auth_tracker.db"
MANIFEST = REX_DIR / "ACTIVE_SYSTEM_MANIFEST.json"
FLAG_Q   = REX_DIR / "goj_menu_flags_queue.json"
QUAR_DIR = REX_DIR / "QUARANTINE_CONTRADICTORY_LEGACY_2026_04_14"
INTAKE   = REX_DIR / "LEDGER_REVIEW_INBOX"
ALERTS_DIR = REX_DIR / "alerts"
LOG_DIR  = REX_DIR / "logs"


# ── Main collector ─────────────────────────────────────────────────────────────
def get_status() -> Dict[str, Any]:
    """
    Collect the full command center status snapshot.
    Always returns a dict — never raises.
    """
    now = datetime.now(timezone.utc).isoformat()
    return {
        "timestamp":        now,
        "generated_by":     "rex_command_center_status v1.0",
        "system_health":    _system_health(),
        "database":         _database_status(),
        "services":         _service_status(),
        "ocr":              _ocr_status(),
        "dashboard":        _dashboard_status(),
        "quarantine":       _quarantine_status(),
        "ledger":           _ledger_status(),
        "security_alerts":  _security_alerts(),
        "recent_changes":   _recent_changes(),
        "manual_review":    _manual_review_items(),
        "backup":           _backup_status(),
    }


# ── Individual collectors ──────────────────────────────────────────────────────
def _database_status() -> Dict:
    result = {
        "path":            str(AUTH_DB),
        "accessible":      False,
        "client_count":    0,
        "active_clients":  0,
        "staff_count":     0,
        "auth_count":      0,
        "attendance_count":0,
        "menu_count":      0,
        "rexxie_ideas":    0,
        "staff_medical":   0,
        "error":           None,
    }
    if not AUTH_DB.exists():
        result["error"] = "auth_tracker.db not found"
        return result
    try:
        conn = sqlite3.connect(str(AUTH_DB))
        conn.row_factory = sqlite3.Row
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        result["accessible"] = True
        result["tables"] = sorted(tables)

        if "clients" in tables:
            result["client_count"]   = conn.execute("SELECT COUNT(*) FROM clients").fetchone()[0]
            result["active_clients"] = conn.execute("SELECT COUNT(*) FROM clients WHERE active=1").fetchone()[0]

        if "users" in tables:
            result["staff_count"] = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]

        if "auth_documents" in tables:
            result["auth_count"] = conn.execute("SELECT COUNT(*) FROM auth_documents").fetchone()[0]

        if "attendance_log" in tables:
            result["attendance_count"] = conn.execute("SELECT COUNT(*) FROM attendance_log").fetchone()[0]

        if "client_menus" in tables:
            result["menu_count"] = conn.execute("SELECT COUNT(DISTINCT client_name) FROM client_menus").fetchone()[0]

        if "rexxie_ideas" in tables:
            result["rexxie_ideas"] = conn.execute("SELECT COUNT(*) FROM rexxie_ideas WHERE status='open'").fetchone()[0]

        if "staff_medical_log" in tables:
            result["staff_medical"] = conn.execute("SELECT COUNT(*) FROM staff_medical_log").fetchone()[0]

        conn.close()
    except Exception as e:
        result["error"] = str(e)
    return result


def _service_status() -> Dict:
    def _check_proc(pattern: str) -> Dict:
        try:
            r = subprocess.run(["pgrep", "-f", pattern], capture_output=True, text=True, timeout=3)
            pids = r.stdout.strip().split()
            return {"status": "running" if pids else "stopped", "pids": pids}
        except Exception:
            return {"status": "unknown", "pids": []}

    def _check_port(port: int) -> bool:
        try:
            import socket
            s = socket.socket()
            s.settimeout(0.5)
            s.connect(("localhost", port))
            s.close()
            return True
        except Exception:
            return False

    rex_back   = _check_proc("uvicorn.*backend.main")
    rexxie_bot = _check_proc("rex_rexxie_telegram_bot")
    scheduler  = _check_proc("goj_daily_scheduler")
    gold_bot   = _check_proc("private_confidant_gold")

    return {
        "rex_backend": {
            **rex_back,
            "url":         "http://localhost:8000",
            "port_open":   _check_port(8000),
        },
        "rexxie_bot": {
            **rexxie_bot,
            "file":        "rex_rexxie_telegram_bot.py",
        },
        "rexxie_growth_loop": {
            **gold_bot,
            "file":        "private_confidant_gold.py",
            "note":        "In Gold_Health_Systems/ — separate start",
        },
        "scheduler": {
            **scheduler,
            "file":        "goj_daily_scheduler.py",
        },
        "flask_dashboard": {
            "port_open":   _check_port(8080),
            "url":         "http://localhost:8080",
            "status":      "running" if _check_port(8080) else "stopped",
        },
    }


def _ocr_status() -> Dict:
    result = {
        "flag_queue_total":      0,
        "flag_queue_unresolved": 0,
        "flag_queue_stale_path": 0,
        "last_ocr_log":          None,
        "snapshot_exists":       False,
        "core_schema_ok":        False,
        "drop_zone":             str(REX_DIR / "Scanned docs"),
        "drop_zone_pending":     0,
    }
    # Flag queue
    if FLAG_Q.exists():
        try:
            flags = json.loads(FLAG_Q.read_text())
            result["flag_queue_total"]      = len(flags)
            result["flag_queue_unresolved"] = len([f for f in flags if not f.get("resolved")])
            result["flag_queue_stale_path"] = len([f for f in flags
                                                   if not f.get("resolved") and
                                                   "/sessions/" in str(f.get("pdf_path",""))])
        except Exception:
            pass

    # Last OCR log
    ocr_logs = sorted(LOG_DIR.glob("vision_ocr_*.log"), reverse=True) if LOG_DIR.exists() else []
    if ocr_logs:
        result["last_ocr_log"] = {
            "file": ocr_logs[0].name,
            "modified": datetime.fromtimestamp(ocr_logs[0].stat().st_mtime).isoformat(),
        }

    # Snapshot
    result["snapshot_exists"] = any(REX_DIR.glob("OCR_WORKING_SNAPSHOT_*"))

    # Schema
    result["core_schema_ok"] = (REX_DIR / "core" / "ocr_schema.py").exists()

    # Drop zone
    drop = REX_DIR / "Scanned docs"
    if drop.exists():
        result["drop_zone_pending"] = len(list(drop.glob("*.pdf")))

    return result


def _dashboard_status() -> Dict:
    return {
        "local_flask":  {
            "url":    "http://localhost:8080",
            "note":   "Flask app — reads local auth_tracker.db",
        },
        "railway_goj":  {
            "url":    "https://respectful-intuition-production-0acf.up.railway.app",
            "status": "DISCONNECTED",
            "note":   "Uses Railway's own DB — NOT synced with local auth_tracker.db",
        },
        "ghs_marketing":{
            "url":    "https://goldhealthsys.com",
            "note":   "Marketing site only. No client data.",
        },
        "recommended":  {
            "path":   "FastAPI (localhost:8000) → auth_tracker.db via Tailscale",
            "command":"START_API_SERVER.command",
            "status": "NOT_YET_CONFIGURED",
        },
    }


def _quarantine_status() -> Dict:
    result = {"path": str(QUAR_DIR), "exists": False, "item_count": 0, "items": []}
    if QUAR_DIR.exists():
        result["exists"] = True
        items = [p.name for p in QUAR_DIR.iterdir() if not p.name.startswith('.')]
        result["item_count"] = len(items)
        result["items"] = items[:10]
    return result


def _ledger_status() -> Dict:
    files = {
        "MASTER_BUILD_LEDGER.md":    REX_DIR / "MASTER_BUILD_LEDGER.md",
        "MASTER_SYSTEM_FILE_LOG.md": REX_DIR / "MASTER_SYSTEM_FILE_LOG.md",
        "BUILD_DECISION_HISTORY.md": REX_DIR / "BUILD_DECISION_HISTORY.md",
        "LEDGER_INTAKE_LOG.md":      REX_DIR / "LEDGER_INTAKE_LOG.md",
    }
    result = {"files": {}, "intake_pending": 0, "all_present": True}
    for name, path in files.items():
        if path.exists():
            result["files"][name] = {
                "lines": sum(1 for _ in path.open()),
                "modified": datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d"),
            }
        else:
            result["files"][name] = {"lines": 0, "modified": None}
            result["all_present"] = False

    if INTAKE.exists():
        result["intake_pending"] = len([f for f in INTAKE.iterdir()
                                        if not f.name.startswith('.') and f.name != 'README.md'])
    return result


def _security_alerts() -> List[Dict]:
    alerts = []
    # Check if old token pattern exists (don't expose actual token)
    env_file = REX_DIR / ".env"
    if env_file.exists():
        content = env_file.read_text()
        if "ANTHROPIC_API_KEY" in content and "sk-ant" in content:
            alerts.append({
                "level":   "CRITICAL",
                "message": "Anthropic API key in plaintext .env — rotate and move to Keychain",
                "file":    ".env",
            })

    # Check telegram config
    tg_config = REX_DIR / "rex_rexxie_telegram_config.json"
    if tg_config.exists():
        try:
            d = json.loads(tg_config.read_text())
            token = d.get("bot_token", "")
            if token and ":" in token:
                alerts.append({
                    "level":   "CRITICAL",
                    "message": "Telegram bot token in plaintext JSON — revoke via BotFather and move to Keychain",
                    "file":    "rex_rexxie_telegram_config.json",
                })
        except Exception:
            pass

    # Check vaults
    vault_recovery = REX_DIR / "rexxie.db"
    if vault_recovery.exists():
        try:
            conn = sqlite3.connect(str(vault_recovery))
            row = conn.execute("SELECT backup_enc FROM rexxie_vault_recovery LIMIT 1").fetchone()
            if row and row[0] is None:
                alerts.append({
                    "level":   "HIGH",
                    "message": "Vault recovery shares not generated — if .rexxie_key is lost, vault is unrecoverable",
                    "file":    "rexxie.db",
                })
            conn.close()
        except Exception:
            pass

    return alerts


def _recent_changes() -> List[Dict]:
    changes = []
    try:
        # Find recently modified files
        cutoff = datetime.now().timestamp() - (24 * 3600)  # last 24h
        skip = {".venv", "node_modules", "__pycache__", "REX_Backups", "_archive", "logs"}

        for f in REX_DIR.rglob("*"):
            if any(s in f.parts for s in skip):
                continue
            if not f.is_file():
                continue
            try:
                mtime = f.stat().st_mtime
                if mtime > cutoff:
                    changes.append({
                        "file": str(f.relative_to(REX_DIR)),
                        "modified": datetime.fromtimestamp(mtime).strftime("%H:%M"),
                    })
            except Exception:
                continue

        changes.sort(key=lambda x: x["modified"], reverse=True)
    except Exception:
        pass
    return changes[:15]


def _manual_review_items() -> List[Dict]:
    items = []
    if INTAKE.exists():
        for f in INTAKE.iterdir():
            if f.name.startswith('.') or f.name == 'README.md':
                continue
            items.append({
                "file":    f.name,
                "path":    str(f),
                "size":    f.stat().st_size if f.exists() else 0,
            })
    return items


def _backup_status() -> Dict:
    # REX snapshots live EXCLUSIVELY on the external Cartoons drive.
    # If the drive isn't mounted we report zero backups and say so —
    # we do NOT fall back to the in-tree REX_Backups folder, which is
    # being retired (and may be stale / mid-migration).
    cartoons_root = None
    for candidate in (Path("/Volumes/Cartoons/REX_Backups"),
                      Path("/Volumes/cartoons/REX_Backups")):
        if candidate.exists():
            cartoons_root = candidate
            break

    if cartoons_root is None:
        return {
            "last_backup": None,
            "backup_count": 0,
            "cartoons_accessible": False,
            "backup_dir": None,
            "note": "Cartoons drive not mounted — plug in to see or take snapshots.",
        }

    try:
        backups = sorted(cartoons_root.glob("REX_*"), reverse=True)
    except Exception:
        backups = []
    return {
        "last_backup": backups[0].name if backups else None,
        "backup_count": len(backups),
        "cartoons_accessible": True,
        "backup_dir": str(cartoons_root),
        "note": "REX snapshots live on Cartoons. Nothing in REX reads from here as a source.",
    }


def _system_health() -> str:
    """Overall health: ok / warning / critical."""
    alerts = _security_alerts()
    if any(a["level"] == "CRITICAL" for a in alerts):
        return "critical"
    db = _database_status()
    if not db["accessible"] or db["active_clients"] == 0:
        return "critical"
    svcs = _service_status()
    if svcs["rex_backend"]["status"] == "stopped":
        return "warning"
    if any(a["level"] == "HIGH" for a in alerts):
        return "warning"
    return "ok"
