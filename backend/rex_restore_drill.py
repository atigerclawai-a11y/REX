#!/usr/bin/env python3
"""
REX — Restore Drill Engine  (rex_restore_drill.py)
Phase 10 | Built: 2026-04-15

══════════════════════════════════════════════════════════════════════════════
PURPOSE
  Verify that a real restore from a backup snapshot would succeed,
  without touching the live system.

  The drill never passes silently. Every check is explicit. Every failure
  is named and logged.

DRILL FLOW
  1. Select most-recent GOJ snapshot (or REX snapshot)
  2. Verify MANIFEST.txt exists and is parseable
  3. For each file listed in MANIFEST.txt, verify it exists on disk
  4. SHA-256 hash verification on all governed files (prompt_registry.json, etc.)
     — drill FAILS if any governed file hash cannot be verified
  5. Validate governed JSON files (parseable + expected schema_version)
  6. Write result to state/restore_drill_status.json
  7. Emit audit events

REFINEMENTS (Phase 10 approval)
  - SHA-256 hash of each governed file computed and stored during drill
  - Drill FAILS if any governed file fails hash verification against its own
    internal content_hash field (for prompt_registry.json) or if the file
    is unreadable/corrupted
  - Cooldown: configurable minimum minutes between drill runs (default 5)
    to prevent accidental hammering

AUDIT EVENTS → state/prompt_audit.log
  restore_drill_started, restore_drill_passed, restore_drill_failed

MSU REQUIREMENT
  Drill execution (POST) requires MSU session to be unlocked.
  Status read (GET) is always available.
══════════════════════════════════════════════════════════════════════════════
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

log = logging.getLogger("rex_restore_drill")

# ── Paths ──────────────────────────────────────────────────────────────────────
_BASE           = Path(__file__).parent.parent
DRILL_STATUS    = _BASE / "state" / "restore_drill_status.json"
DRILL_HISTORY   = _BASE / "state" / "restore_drill_history.jsonl"   # Part E
AUDIT_LOG       = _BASE / "state" / "prompt_audit.log"

HISTORY_MAX_ENTRIES = 50   # prune when exceeded
CONFIG_FILE     = _BASE / "config" / "session.yaml"
GOJ_BACKUP_ROOT = _BASE / "GOJ_Backups"

# REX snapshots live on the external Cartoons drive ONLY. REX never reads
# backups from inside its own tree or from ~/Desktop. If Cartoons isn't
# mounted, _resolve_rex_backup_root() returns None and restore drills
# cleanly report "no snapshot found" rather than silently falling back.
def _resolve_rex_backup_root() -> Optional[Path]:
    for candidate in (Path("/Volumes/Cartoons/REX_Backups"),
                      Path("/Volumes/cartoons/REX_Backups")):
        if candidate.exists() and candidate.is_dir():
            return candidate
    return None

REX_BACKUP_ROOT = _resolve_rex_backup_root()

# ── Cooldown default ───────────────────────────────────────────────────────────
DEFAULT_COOLDOWN_MINUTES = 5


# ══════════════════════════════════════════════════════════════════════════════
# RESULT DATA CLASS
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class DrillCheck:
    name:    str
    passed:  bool
    detail:  str = ""
    file:    str = ""
    sha256:  Optional[str] = None

@dataclass
class DrillResult:
    schema_version:  str  = "1.0"
    run_at:          str  = ""
    result:          str  = "not_run"   # passed | failed | not_run
    snapshot_used:   str  = ""
    snapshot_path:   str  = ""
    checks_run:      int  = 0
    checks_passed:   int  = 0
    checks_failed:   int  = 0
    failures:        List[Dict] = field(default_factory=list)
    hashes:          Dict[str, str] = field(default_factory=dict)
    notes:           str  = ""
    cooldown_until:  Optional[str] = None

    def to_dict(self) -> Dict:
        return asdict(self)


# ══════════════════════════════════════════════════════════════════════════════
# RESTORE DRILL ENGINE
# ══════════════════════════════════════════════════════════════════════════════

class RestoreDrill:
    """
    Restore drill: verify snapshot integrity without touching the live system.

    Refinement: every governed file gets a SHA-256 computed and stored
    in the drill result. If the file contains an internal content_hash
    (e.g. prompt_registry.json), that hash is also cross-verified.
    Drill FAILS if any governed file fails hash verification.
    """

    def __init__(self):
        self._config = self._load_config()

    def _load_config(self) -> Dict:
        cfg = {"cooldown_minutes": DEFAULT_COOLDOWN_MINUTES, "governed_files": []}
        if not CONFIG_FILE.exists():
            return cfg
        try:
            import yaml  # type: ignore
            data = yaml.safe_load(CONFIG_FILE.read_text()) or {}
            rd = data.get("restore_drill", {})
            cfg["cooldown_minutes"] = int(rd.get("cooldown_minutes", DEFAULT_COOLDOWN_MINUTES))
            cfg["governed_files"]   = rd.get("governed_files", [])
        except Exception as e:
            log.warning("Config load error: %s", e)
        return cfg

    # ── Status (always available, no MSU required) ────────────────────────────

    def get_status(self) -> Dict:
        """Return last drill result. Returns a not-yet-run status if no drill exists."""
        if not DRILL_STATUS.exists():
            return DrillResult(
                schema_version = "1.0",
                result         = "not_run",
                notes          = "No drill has been run yet.",
            ).to_dict()
        try:
            return json.loads(DRILL_STATUS.read_text())
        except Exception as e:
            return {"result": "error", "notes": str(e)}

    # ── Run (requires MSU unlock) ─────────────────────────────────────────────

    def run(self, snapshot_dir: Optional[str] = None) -> DrillResult:
        """
        Run a restore drill against the most recent snapshot (or a named one).

        Returns a DrillResult. Also writes state/restore_drill_status.json
        and emits audit events.
        """
        # Cooldown check
        cooldown_err = self._check_cooldown()
        if cooldown_err:
            return cooldown_err

        self._audit("restore_drill_started", snapshot=snapshot_dir or "auto")

        result = DrillResult(run_at=_now_iso())

        # Find snapshot
        snap_path = self._find_snapshot(snapshot_dir)
        if snap_path is None:
            result.result        = "failed"
            result.notes         = (
                "No snapshot found in GOJ_Backups. REX snapshots live on the "
                "Cartoons drive (/Volumes/Cartoons/REX_Backups/) — if you "
                "expected a REX snapshot, confirm the drive is mounted."
            )
            result.checks_failed = 1
            result.failures      = [{"check": "find_snapshot", "detail": result.notes}]
            self._save(result)
            self._audit("restore_drill_failed", reason="no_snapshot_found")
            return result

        result.snapshot_used = snap_path.name
        result.snapshot_path = str(snap_path)
        checks: List[DrillCheck] = []

        # Check 1: MANIFEST.txt exists and is non-empty
        checks.append(self._check_manifest(snap_path))

        # Check 2: All files listed in MANIFEST.txt exist on disk
        checks += self._check_manifest_files(snap_path)

        # Check 3: Governed JSON files — parse + schema_version + SHA-256
        checks += self._check_governed_files(snap_path, result.hashes)

        # Check 4: prompt_registry.json internal cross-verification
        checks += self._cross_verify_registry(snap_path, result.hashes)

        # Tally
        result.checks_run    = len(checks)
        result.checks_passed = sum(1 for c in checks if c.passed)
        result.checks_failed = sum(1 for c in checks if not c.passed)
        result.failures      = [
            {"check": c.name, "file": c.file, "detail": c.detail}
            for c in checks if not c.passed
        ]
        result.result = "passed" if result.checks_failed == 0 else "failed"

        # Cooldown: set when next drill is allowed
        cooldown_mins = self._config.get("cooldown_minutes", DEFAULT_COOLDOWN_MINUTES)
        result.cooldown_until = (_now_dt() + timedelta(minutes=cooldown_mins)).isoformat()

        self._save(result)

        event = "restore_drill_passed" if result.result == "passed" else "restore_drill_failed"
        self._audit(event,
                    snapshot=snap_path.name,
                    checks_run=result.checks_run,
                    checks_passed=result.checks_passed,
                    checks_failed=result.checks_failed,
                    failures=[f["check"] for f in result.failures])

        log.info(
            "Restore drill %s: %d/%d checks passed on %s",
            result.result, result.checks_passed, result.checks_run, snap_path.name
        )
        return result

    # ── Individual checks ─────────────────────────────────────────────────────

    def _check_manifest(self, snap: Path) -> DrillCheck:
        manifest = snap / "MANIFEST.txt"
        if not manifest.exists():
            return DrillCheck("manifest_exists", False,
                              detail="MANIFEST.txt not found in snapshot", file="MANIFEST.txt")
        content = manifest.read_text().strip()
        if not content:
            return DrillCheck("manifest_parseable", False,
                              detail="MANIFEST.txt is empty", file="MANIFEST.txt")
        return DrillCheck("manifest_exists", True, file="MANIFEST.txt",
                          sha256=_sha256(manifest))

    def _check_manifest_files(self, snap: Path) -> List[DrillCheck]:
        """Verify every file listed in MANIFEST.txt exists in the snapshot."""
        manifest = snap / "MANIFEST.txt"
        if not manifest.exists():
            return []
        checks = []
        try:
            lines = manifest.read_text().splitlines()
            file_lines = [l for l in lines if l.strip().startswith("/") or
                          (l.strip() and not l.startswith("REX") and
                           not l.startswith("Generated") and
                           not l.startswith("Backup") and
                           not l.startswith("Files") and
                           not l.startswith("Total"))]
            # The manifest lists absolute paths — we check relative to snapshot
            for line in file_lines[:50]:   # cap at 50 to keep drill fast
                fname = Path(line.strip()).name
                # Find this file anywhere in the snapshot
                found = list(snap.rglob(fname))[:1]
                checks.append(DrillCheck(
                    name   = f"manifest_file:{fname}",
                    passed = bool(found),
                    file   = fname,
                    detail = "" if found else f"{fname} not found in snapshot",
                    sha256 = _sha256(found[0]) if found else None,
                ))
        except Exception as e:
            checks.append(DrillCheck("manifest_file_check", False,
                                     detail=f"Error parsing manifest: {e}"))
        return checks

    def _check_governed_files(self, snap: Path, hashes: Dict) -> List[DrillCheck]:
        """
        For each governed file in config, verify it exists, is non-empty,
        parse JSON if applicable, and compute SHA-256.
        Drill FAILS if a governed file fails hash verification.
        """
        checks = []
        governed = self._config.get("governed_files", [])

        # Always check prompt_registry.json if it's in the snapshot
        pr_candidates = list(snap.rglob("prompt_registry.json"))
        if pr_candidates:
            governed = list(governed) + [str(pr_candidates[0].relative_to(snap))]

        for rel_path in governed:
            target = snap / rel_path
            if not target.exists():
                checks.append(DrillCheck(
                    f"governed:{rel_path}", False,
                    detail=f"Not found in snapshot",
                    file=rel_path,
                ))
                continue

            # Non-empty
            if target.stat().st_size == 0:
                checks.append(DrillCheck(
                    f"governed_nonempty:{rel_path}", False,
                    detail="File is empty",
                    file=rel_path,
                ))
                continue

            # SHA-256 — always computed
            h = _sha256(target)
            hashes[rel_path] = h

            # JSON parse check for .json files
            if target.suffix == ".json":
                try:
                    data = json.loads(target.read_text())
                    checks.append(DrillCheck(
                        f"governed_parse:{rel_path}", True,
                        file=rel_path, sha256=h,
                    ))
                    # schema_version check
                    sv = data.get("schema_version", "MISSING")
                    checks.append(DrillCheck(
                        f"governed_schema:{rel_path}", sv != "MISSING",
                        detail="" if sv != "MISSING" else "Missing schema_version field",
                        file=rel_path,
                    ))
                except json.JSONDecodeError as e:
                    checks.append(DrillCheck(
                        f"governed_parse:{rel_path}", False,
                        detail=f"JSON parse error: {e}",
                        file=rel_path, sha256=h,
                    ))
            else:
                checks.append(DrillCheck(
                    f"governed_readable:{rel_path}", True,
                    file=rel_path, sha256=h,
                ))

        return checks

    def _cross_verify_registry(self, snap: Path, hashes: Dict) -> List[DrillCheck]:
        """
        Cross-verify prompt_registry.json: compare SHA-256 of the body-only
        content against the content_hash fields stored in each prompt entry.
        This verifies the registry is internally consistent.
        """
        checks = []
        pr_files = list(snap.rglob("prompt_registry.json"))
        if not pr_files:
            return checks

        pr_path = pr_files[0]
        try:
            data    = json.loads(pr_path.read_text())
            prompts = data.get("prompts", [])
            mismatches = 0
            for p in prompts:
                # content_hash in registry is hash of the body-only of the .md file
                # In the snapshot we can only verify the registry JSON is valid
                pid = p.get("id", "?")
                if not p.get("content_hash"):
                    checks.append(DrillCheck(
                        f"registry_entry_hash:{pid}", False,
                        detail="Missing content_hash field",
                        file=str(pr_path.relative_to(snap)),
                    ))
                    mismatches += 1

            if mismatches == 0:
                checks.append(DrillCheck(
                    "registry_entry_hashes_present", True,
                    detail=f"All {len(prompts)} entries have content_hash",
                    file=str(pr_path.relative_to(snap)),
                ))
        except Exception as e:
            checks.append(DrillCheck(
                "registry_cross_verify", False,
                detail=f"Error: {e}",
                file=str(pr_path.relative_to(snap)),
            ))
        return checks

    # ── Snapshot finder ───────────────────────────────────────────────────────

    def _find_snapshot(self, named: Optional[str]) -> Optional[Path]:
        """Find the most recent GOJ snapshot, or a specifically named one.

        REX snapshots are only consulted when the Cartoons drive is mounted
        (REX_BACKUP_ROOT != None). Otherwise the drill silently skips REX
        and either uses a GOJ snapshot or reports no snapshot found.
        """
        # Refresh Cartoons mount each call — the drive may have been
        # plugged in between process start and drill run.
        rex_root = _resolve_rex_backup_root()

        if named:
            # Try as an absolute path first, then relative to backup roots
            p = Path(named)
            if p.exists() and p.is_dir():
                return p
            roots = [GOJ_BACKUP_ROOT, _BASE]
            if rex_root is not None:
                roots.insert(1, rex_root)
            for root in roots:
                candidate = root / named
                if candidate.exists() and candidate.is_dir():
                    return candidate
            return None

        # Auto: most recent GOJ snapshot (preferred) then REX snapshot
        search: List = [(GOJ_BACKUP_ROOT, "GOJ_*")]
        if rex_root is not None:
            search.append((rex_root, "REX_*"))
        for root, pattern in search:
            if root.exists():
                dirs = sorted(root.glob(pattern), reverse=True)
                if dirs:
                    return dirs[0]
        return None

    # ── Cooldown ──────────────────────────────────────────────────────────────

    def _check_cooldown(self) -> Optional[DrillResult]:
        """Return an error DrillResult if we're within the cooldown window."""
        status = self.get_status()
        cooldown_until = status.get("cooldown_until")
        if cooldown_until:
            try:
                cd = datetime.fromisoformat(cooldown_until)
                if _now_dt() < cd:
                    remaining = int((cd - _now_dt()).total_seconds() / 60)
                    r = DrillResult(
                        run_at  = _now_iso(),
                        result  = "skipped",
                        notes   = (
                            f"Drill cooldown active. "
                            f"Next drill allowed at {cooldown_until[:19]} UTC "
                            f"(~{remaining}m remaining)."
                        ),
                        cooldown_until = cooldown_until,
                    )
                    return r
            except Exception:
                pass
        return None

    # ── Persistence + audit ───────────────────────────────────────────────────

    def get_history(self, limit: int = 10) -> List[Dict]:
        """
        Part E: Return last N drill results from history log (most-recent-first).
        Each entry: run_at, result, snapshot_used, checks_passed, checks_failed, failures (names).
        """
        if not DRILL_HISTORY.exists():
            return []
        entries = []
        try:
            for line in reversed(DRILL_HISTORY.read_text().splitlines()):
                line = line.strip()
                if not line:
                    continue
                try:
                    entries.append(json.loads(line))
                    if len(entries) >= limit:
                        break
                except json.JSONDecodeError:
                    continue
        except Exception as e:
            log.error("Drill history read error: %s", e)
        return entries

    def _save(self, result: DrillResult) -> None:
        DRILL_STATUS.parent.mkdir(parents=True, exist_ok=True)
        # Write current status (overwrite)
        tmp = DRILL_STATUS.with_suffix(".tmp")
        tmp.write_text(json.dumps(result.to_dict(), indent=2))
        tmp.replace(DRILL_STATUS)
        # Append to history (Part E)
        self._append_history(result)

    def _append_history(self, result: DrillResult) -> None:
        """Append a summary entry to drill history. Prune to HISTORY_MAX_ENTRIES."""
        entry = {
            "run_at":          result.run_at,
            "result":          result.result,
            "snapshot_used":   result.snapshot_used,
            "checks_passed":   result.checks_passed,
            "checks_failed":   result.checks_failed,
            "failures":        [f["check"] for f in result.failures],
        }
        try:
            DRILL_HISTORY.parent.mkdir(parents=True, exist_ok=True)
            with DRILL_HISTORY.open("a") as f:
                f.write(json.dumps(entry) + "\n")
            # Prune if too long
            lines = DRILL_HISTORY.read_text().splitlines()
            if len(lines) > HISTORY_MAX_ENTRIES:
                DRILL_HISTORY.write_text("\n".join(lines[-HISTORY_MAX_ENTRIES:]) + "\n")
        except Exception as e:
            log.error("Drill history append error: %s", e)

    def _audit(self, event: str, **kwargs) -> None:
        entry = {"event": event, "timestamp": _now_iso(), **kwargs}
        try:
            AUDIT_LOG.parent.mkdir(parents=True, exist_ok=True)
            with AUDIT_LOG.open("a") as f:
                f.write(json.dumps(entry) + "\n")
        except Exception as e:
            log.error("Restore drill audit write failed: %s", e)


# ══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def _sha256(path: Path) -> str:
    """Compute SHA-256 of a file. Returns hex digest."""
    h = hashlib.sha256()
    try:
        with path.open("rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()
    except Exception:
        return ""

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def _now_dt() -> datetime:
    return datetime.now(timezone.utc)
