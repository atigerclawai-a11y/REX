#!/usr/bin/env python3
"""
REX — Nightly Briefing Generator (rex_nightly_brief.py)
Phase 9 | CLS v3 Build
Built: 2026-04-15

══════════════════════════════════════════════════════════════════════════════
REQUIRED METADATA — every briefing MUST include:
  1. Covered time window (start → end in local time)
  2. Generation timestamp (UTC ISO-8601)
  3. Source/event counts used

MOBILE SAFETY:
  • Role boundaries are enforced before any section is included
  • Chairman-only sections are never rendered for staff-tier callers
  • Mobile access does NOT weaken governance — same role checks apply

ROLE RULES:
  • role="chairman"  → full briefing (all sections)
  • role="staff"     → operational summary only (no memory, no CLS, no flags)
  • role="guest"     → not permitted; returns error block

DELIVERY:
  • Returns a structured dict for API/Telegram rendering
  • Caller is responsible for actual delivery (Telegram, web, email)
  • Use NightlyBrief.send_telegram() for Rexxie bot delivery

Usage:
    from backend.rex_nightly_brief import NightlyBrief
    brief = NightlyBrief(role="chairman")
    result = brief.generate()
    brief.send_telegram(result)

    # CLI:
    python -m backend.rex_nightly_brief [--role chairman] [--dry-run]
══════════════════════════════════════════════════════════════════════════════
"""

from __future__ import annotations

import argparse
import json
import logging
import sqlite3
import urllib.request
from datetime import datetime, timedelta, timezone, date
from pathlib import Path
from typing import Any, Dict, List, Optional

log = logging.getLogger("rex_nightly_brief")

# ── Paths ─────────────────────────────────────────────────────────────────────
_BASE       = Path(__file__).parent.parent
_DATA_DIR   = _BASE / "data"
_VAULT_DIR  = _DATA_DIR / "vaults"

EVENTS_DB       = _DATA_DIR / "rex_events.db"
UNRESOLVED_DB   = _DATA_DIR / "rex_unresolved.db"
ALERT_BUS       = _DATA_DIR / "alert_bus_fallback.jsonl"
BEHAVIOR_LOG    = _BASE / "logs" / "behavior_flags.json"
TG_CONFIG       = _BASE / "rex_rexxie_telegram_config.json"
BRIEF_LOG       = _BASE / "logs" / "nightly_briefs.jsonl"

BRIEF_LOG.parent.mkdir(parents=True, exist_ok=True)

# ── Role constants ────────────────────────────────────────────────────────────
ROLE_CHAIRMAN = "chairman"
ROLE_STAFF    = "staff"
ROLE_GUEST    = "guest"

_ALLOWED_ROLES = {ROLE_CHAIRMAN, ROLE_STAFF}

# ── Window ────────────────────────────────────────────────────────────────────
DEFAULT_LOOKBACK_HOURS = 24


# ══════════════════════════════════════════════════════════════════════════════
# SECTION BUILDERS (each returns a dict with count + content)
# ══════════════════════════════════════════════════════════════════════════════

def _window_meta(lookback_hours: int) -> Dict[str, Any]:
    """Required metadata: covered window, generation timestamp."""
    now       = datetime.now(timezone.utc)
    window_start = now - timedelta(hours=lookback_hours)
    return {
        "generated_at":       now.isoformat(),           # Required ①
        "window_start":       window_start.isoformat(),  # Required ②
        "window_end":         now.isoformat(),            # Required ②
        "window_hours":       lookback_hours,
        "window_label":       (
            f"{window_start.strftime('%b %d %H:%M')} → "
            f"{now.strftime('%b %d %H:%M')} UTC"
        ),
    }


def _count_rex_events(lookback_hours: int) -> Dict[str, Any]:
    """Count events from rex_events.db within the window."""
    if not EVENTS_DB.exists():
        return {"total": 0, "by_type": {}, "source": "rex_events.db", "available": False}

    cutoff = (datetime.now(timezone.utc) - timedelta(hours=lookback_hours)).isoformat()
    try:
        conn = sqlite3.connect(str(EVENTS_DB))
        conn.row_factory = sqlite3.Row
        rows = conn.execute("""
            SELECT event_type, COUNT(*) as cnt
            FROM events
            WHERE created_at >= ?
            GROUP BY event_type
            ORDER BY cnt DESC
        """, (cutoff,)).fetchall()
        conn.close()
        by_type = {r["event_type"]: r["cnt"] for r in rows}
        return {
            "total":     sum(by_type.values()),
            "by_type":   by_type,
            "source":    "rex_events.db",
            "available": True,
        }
    except sqlite3.OperationalError as e:
        log.warning("rex_events.db query error: %s", e)
        return {"total": 0, "by_type": {}, "source": "rex_events.db", "available": False, "error": str(e)}


def _count_alerts(lookback_hours: int) -> Dict[str, Any]:
    """Count alerts from alert_bus_fallback.jsonl within the window."""
    if not ALERT_BUS.exists():
        return {"total": 0, "by_level": {}, "source": "alert_bus", "available": False}

    cutoff    = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)
    by_level: Dict[str, int] = {}
    total     = 0

    try:
        with ALERT_BUS.open() as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    ts_raw = entry.get("timestamp") or entry.get("ts") or ""
                    try:
                        ts = datetime.fromisoformat(ts_raw.replace("Z", "+00:00"))
                        if ts < cutoff:
                            continue
                    except Exception:
                        pass
                    level = entry.get("level", "unknown")
                    by_level[level] = by_level.get(level, 0) + 1
                    total += 1
                except json.JSONDecodeError:
                    continue
    except Exception as e:
        return {"total": 0, "by_level": {}, "source": "alert_bus", "available": False, "error": str(e)}

    return {
        "total":     total,
        "by_level":  by_level,
        "source":    "alert_bus",
        "available": True,
    }


def _count_unresolved() -> Dict[str, Any]:
    """Count unresolved items from rex_unresolved.db."""
    if not UNRESOLVED_DB.exists():
        return {"total": 0, "source": "rex_unresolved.db", "available": False}
    try:
        conn = sqlite3.connect(str(UNRESOLVED_DB))
        row  = conn.execute("SELECT COUNT(*) as n FROM unresolved").fetchone()
        conn.close()
        return {"total": row[0] if row else 0, "source": "rex_unresolved.db", "available": True}
    except Exception as e:
        return {"total": 0, "source": "rex_unresolved.db", "available": False, "error": str(e)}


def _behavior_flags_summary(lookback_hours: int) -> Dict[str, Any]:
    """Summarize recent behavior flags (Chairman-only section)."""
    if not BEHAVIOR_LOG.exists():
        return {"total": 0, "flags": [], "available": False}
    try:
        data  = json.loads(BEHAVIOR_LOG.read_text())
        if not isinstance(data, list):
            return {"total": 0, "flags": [], "available": True}
        cutoff = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)
        recent = []
        for entry in data:
            ts_raw = entry.get("timestamp", "")
            try:
                ts = datetime.fromisoformat(ts_raw.replace("Z", "+00:00"))
                if ts < cutoff:
                    continue
            except Exception:
                pass
            recent.append({
                "flag_type": entry.get("flag_type", "unknown"),
                "severity":  entry.get("severity", "unknown"),
                "message":   entry.get("message", "")[:100],
            })
        return {"total": len(recent), "flags": recent[:10], "available": True}
    except Exception as e:
        return {"total": 0, "flags": [], "available": False, "error": str(e)}


def _cls_summary() -> Dict[str, Any]:
    """CLS v3 status snapshot (Chairman-only section)."""
    try:
        from core.cls_v3 import CLS_v3
        cls    = CLS_v3(dry_run=True)
        report = cls.status_report()
        return {
            "available":        True,
            "patterns_tracked": report.get("patterns_tracked", 0),
            "candidates_pending": report.get("candidates", {}).get("pending", 0),
            "candidates_approved": report.get("candidates", {}).get("approved", 0),
            "top_pattern": (
                report.get("top_patterns", [{}])[0].get("key", "none")
                if report.get("top_patterns") else "none"
            ),
        }
    except Exception as e:
        log.warning("CLS v3 summary error: %s", e)
        return {"available": False, "error": str(e)}


# ══════════════════════════════════════════════════════════════════════════════
# BRIEFING ENGINE
# ══════════════════════════════════════════════════════════════════════════════

class NightlyBrief:
    """
    Generates a structured nightly briefing for REX/Rexxie.

    Every briefing includes:
      • covered time window (start → end)
      • generation timestamp (UTC)
      • source/event counts used

    Role boundaries:
      • chairman → full briefing
      • staff    → operational summary only
      • guest    → error, not permitted

    The REXXIE decisions panel is read-only — CLS candidates are surfaced
    as read-only summary data; no writes happen during briefing generation.
    """

    def __init__(
        self,
        role:           str  = ROLE_CHAIRMAN,
        lookback_hours: int  = DEFAULT_LOOKBACK_HOURS,
    ):
        if role not in _ALLOWED_ROLES:
            raise PermissionError(
                f"NightlyBrief: role '{role}' is not permitted. "
                f"Allowed: {_ALLOWED_ROLES}"
            )
        self.role           = role
        self.lookback_hours = lookback_hours

    def generate(self) -> Dict[str, Any]:
        """
        Generate the full briefing structure.
        Returns a dict ready for Telegram formatting or API delivery.
        """
        # ── Required metadata (always present) ────────────────────────────────
        meta   = _window_meta(self.lookback_hours)
        events = _count_rex_events(self.lookback_hours)
        alerts = _count_alerts(self.lookback_hours)
        unresolved = _count_unresolved()

        # Required ③: source/event counts
        source_counts = {
            "rex_events":    events["total"],
            "alerts":        alerts["total"],
            "unresolved":    unresolved["total"],
        }

        brief: Dict[str, Any] = {
            # ── Required metadata ─────────────────────────────────────────────
            "generated_at":   meta["generated_at"],        # Required ①
            "window_start":   meta["window_start"],        # Required ②
            "window_end":     meta["window_end"],          # Required ②
            "window_label":   meta["window_label"],        # Human-readable ②
            "source_counts":  source_counts,               # Required ③
            # ── Context ───────────────────────────────────────────────────────
            "role":           self.role,
            "lookback_hours": self.lookback_hours,
        }

        # ── Operational section (staff + chairman) ────────────────────────────
        brief["operational"] = {
            "events":     events,
            "alerts":     alerts,
            "unresolved": unresolved,
        }

        # ── Chairman-only sections ────────────────────────────────────────────
        if self.role == ROLE_CHAIRMAN:
            brief["behavior_flags"] = _behavior_flags_summary(self.lookback_hours)
            brief["cls_summary"]    = _cls_summary()    # read-only CLS snapshot
        # NOTE: staff role gets no behavior_flags and no cls_summary — intentional

        # ── Log the brief (append-only) ────────────────────────────────────────
        self._log_brief(brief)

        return brief

    def _log_brief(self, brief: Dict[str, Any]) -> None:
        """Append brief metadata to nightly_briefs.jsonl (no content, just header)."""
        log_entry = {
            "generated_at":  brief["generated_at"],
            "window_start":  brief["window_start"],
            "window_end":    brief["window_end"],
            "role":          brief["role"],
            "source_counts": brief["source_counts"],
        }
        try:
            with BRIEF_LOG.open("a") as f:
                f.write(json.dumps(log_entry) + "\n")
        except Exception as e:
            log.warning("Brief log write failed: %s", e)

    def format_telegram(self, brief: Dict[str, Any]) -> str:
        """Format the brief as a Telegram-safe message (no HTML, plain text)."""
        lines = [
            "📋 REX Nightly Brief",
            f"🕐 Window: {brief['window_label']}",
            f"🗓️  Generated: {brief['generated_at'][:16]} UTC",
            "",
            "📊 Source counts:",
            f"  • Events:     {brief['source_counts']['rex_events']}",
            f"  • Alerts:     {brief['source_counts']['alerts']}",
            f"  • Unresolved: {brief['source_counts']['unresolved']}",
        ]

        ops = brief.get("operational", {})
        alerts = ops.get("alerts", {})
        if alerts.get("total", 0) > 0:
            lines.append("")
            lines.append("⚠️ Alert breakdown:")
            for level, count in alerts.get("by_level", {}).items():
                lines.append(f"  • {level}: {count}")

        events = ops.get("events", {})
        if events.get("total", 0) > 0 and events.get("by_type"):
            lines.append("")
            lines.append("📌 Event types:")
            for etype, count in list(events["by_type"].items())[:5]:
                lines.append(f"  • {etype}: {count}")

        # Chairman-only sections
        if self.role == ROLE_CHAIRMAN:
            flags = brief.get("behavior_flags", {})
            if flags.get("total", 0) > 0:
                lines.append("")
                lines.append(f"🔍 Behavior flags: {flags['total']}")
                for flag in flags.get("flags", [])[:3]:
                    lines.append(f"  • [{flag['severity']}] {flag['flag_type']}: {flag['message'][:60]}")

            cls_s = brief.get("cls_summary", {})
            if cls_s.get("available"):
                lines.append("")
                lines.append(
                    f"🧠 CLS v3: {cls_s['patterns_tracked']} patterns tracked, "
                    f"{cls_s['candidates_pending']} pending approval"
                )
                if cls_s.get("candidates_pending", 0) > 0:
                    lines.append("  → Reply 'cls candidates' to review")

        unresolved_count = brief["source_counts"]["unresolved"]
        if unresolved_count > 0:
            lines.append("")
            lines.append(f"❓ Unresolved items: {unresolved_count} — check REX dashboard")

        return "\n".join(lines)

    def send_telegram(self, brief: Dict[str, Any]) -> bool:
        """Send formatted brief via Rexxie Telegram bot. Returns True on success."""
        if not TG_CONFIG.exists():
            log.warning("Telegram config not found, cannot send brief")
            return False

        try:
            cfg     = json.loads(TG_CONFIG.read_text())
            token   = cfg.get("bot_token", "")
            chat_id = cfg.get("owner_chat_id") or cfg.get("chairman_chat_id") or ""

            if not token or not chat_id:
                log.warning("Incomplete Telegram config")
                return False

            text    = self.format_telegram(brief)
            payload = json.dumps({"chat_id": chat_id, "text": text}).encode()
            req     = urllib.request.Request(
                f"https://api.telegram.org/bot{token}/sendMessage",
                data    = payload,
                headers = {"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                result = json.loads(resp.read())
                if result.get("ok"):
                    log.info("Nightly brief sent via Telegram")
                    return True
                else:
                    log.error("Telegram error: %s", result)
                    return False
        except Exception as e:
            log.error("send_telegram failed: %s", e)
            return False


# ══════════════════════════════════════════════════════════════════════════════
# CLI
# ══════════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="REX Nightly Brief Generator")
    parser.add_argument("--role",    default="chairman",
                        choices=["chairman", "staff"],
                        help="Role for brief (affects content sections)")
    parser.add_argument("--hours",   default=24, type=int,
                        help="Lookback window in hours (default: 24)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Generate and print without sending Telegram")
    parser.add_argument("--json",    action="store_true",
                        help="Print raw JSON output")
    args = parser.parse_args()

    logging.basicConfig(
        level   = logging.INFO,
        format  = "%(asctime)s [NightlyBrief] %(levelname)s %(message)s",
        datefmt = "%Y-%m-%dT%H:%M:%S",
    )

    brief_gen = NightlyBrief(role=args.role, lookback_hours=args.hours)
    result    = brief_gen.generate()

    if args.json:
        print(json.dumps(result, indent=2))
        return

    formatted = brief_gen.format_telegram(result)
    print("\n" + "═" * 55)
    print(formatted)
    print("═" * 55)

    if not args.dry_run:
        ok = brief_gen.send_telegram(result)
        print(f"\n{'✅ Sent via Telegram' if ok else '❌ Telegram send failed'}")
    else:
        print("\n[dry-run: Telegram not sent]")


if __name__ == "__main__":
    main()
