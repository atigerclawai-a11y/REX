#!/usr/bin/env python3
"""
CC_latest_build_finder.py — find the LATEST / BEST build of an artifact
========================================================================
The recurring problem: the deployed version of something (a HUD, a command
center, a dashboard) is an old draft, while richer/newer builds sit buried in
files or past Claude sessions. This agent scrapes BOTH and ranks them.

It scores each candidate on three axes — not just mtime — because "latest by
date" is often a stripped rebuild, while the real build is older but far richer:
  • richness  : file size + count of distinct feature markers
  • recency   : modified time
  • liveness  : does it point at PUBLIC endpoints (works remotely) or localhost?

Usage:
    python3 CC_latest_build_finder.py "command center"     # rank builds
    python3 CC_latest_build_finder.py jarvis --json
    python3 CC_latest_build_finder.py "command center" --sessions   # also index session transcripts

Output: ranked table + a clear WINNER with provenance + deployability note.
Report: ~/.rex_infra/build_finder_last.json
"""

import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

HOME = Path.home()
REPORT_PATH = HOME / ".rex_infra" / "build_finder_last.json"

# Where builds tend to live
SCAN_ROOTS = [
    HOME / "Desktop" / "REX",
    HOME / "workspace",
    HOME / "Documents",
    HOME / ".hermes",
    HOME / "Desktop" / "REX_Backups",
]
SKIP_DIRS = {"node_modules", ".git", ".venv", ".venv-ocr", "site-packages",
             "Caches", ".next/cache", "__pycache__", "release", "target"}
BUILD_EXTS = {".html", ".htm"}

# Feature markers — more distinct hits ⇒ richer build
FEATURE_MARKERS = [
    "goj live", "attendance", "present", "menu", "driver", "route",
    "authoriz", "client", "kanban", "terminal", "notebook", "victoria",
    "masha", "revenue", "billing", "chart", "map", "calendar", "proposal",
    "signature", "ocr", "telegram", "drive ingest",
]
PUBLIC_HOSTS = ["rex.hermestigerclaw.com", "hermestigerclaw.com",
                "goldhealthsys.com", "netlify.app", "railway"]
LOCAL_RE = re.compile(r"localhost:\d+|127\.0\.0\.1:\d+")
TITLE_RE = re.compile(r"<title>([^<]*)</title>", re.I)
SESSIONS_DIR = HOME / ".claude" / "projects"

# Scoring weights
W_RICHNESS, W_RECENCY, W_LIVENESS = 0.5, 0.3, 0.2
RECENCY_FULL_DAYS = 7.0  # newer than this ⇒ full recency points


def _iter_files():
    for root in SCAN_ROOTS:
        if not root.exists():
            continue
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
            for fn in filenames:
                if Path(fn).suffix.lower() in BUILD_EXTS:
                    yield Path(dirpath) / fn


# Files that match keywords but are NOT app builds (graph viz, data dumps, deps)
JUNK_PATTERNS = ("graph.html", "graphify", "file_browser", "node_modules",
                 "/tmp/reports/", "test_links", "tauri-codegen")
MAX_BUILD_BYTES = 5_000_000  # >5MB ⇒ a data dump, not a UI build


def score_build(path: Path, query: str) -> dict | None:
    pn = str(path).lower()
    if any(j in pn for j in JUNK_PATTERNS):
        return None
    try:
        if path.stat().st_size > MAX_BUILD_BYTES:
            return None
    except Exception:
        return None
    try:
        text = path.read_text(errors="ignore")
    except Exception:
        return None
    low = text.lower()
    q = query.lower()
    name_hit = q in path.name.lower()
    body_hit = q in low or any(w in low for w in q.split())
    if not (name_hit or body_hit):
        return None

    size = len(text)
    features = sorted({m for m in FEATURE_MARKERS if m in low})
    title_m = TITLE_RE.search(text)
    title = title_m.group(1).strip() if title_m else "(no title)"
    local_hits = len(set(LOCAL_RE.findall(text)))
    public_hits = sum(1 for h in PUBLIC_HOSTS if h in low)
    try:
        mtime = path.stat().st_mtime
    except Exception:
        mtime = 0

    # liveness: public endpoints good, localhost-only bad for remote deploy
    if public_hits and not local_hits:
        liveness = 1.0
    elif public_hits and local_hits:
        liveness = 0.6
    elif local_hits:
        liveness = 0.2
    else:
        liveness = 0.5  # static, no data calls

    return {
        "path": str(path).replace(str(HOME), "~"),
        "abs_path": str(path),
        "size": size,
        "mtime": mtime,
        "mtime_str": time.strftime("%Y-%m-%d %H:%M", time.localtime(mtime)) if mtime else "?",
        "title": title,
        "features": features,
        "feature_count": len(features),
        "local_endpoints": local_hits,
        "public_endpoints": public_hits,
        "liveness": round(liveness, 2),
        "is_backup": any(b in str(path).lower() for b in ("backup", "snapshot", "_bak", ".bak")),
    }


def rank(cands: list, now: float) -> list:
    if not cands:
        return cands
    max_size = max(c["size"] for c in cands) or 1
    max_feat = max(c["feature_count"] for c in cands) or 1
    for c in cands:
        richness = 0.6 * (c["feature_count"] / max_feat) + 0.4 * (c["size"] / max_size)
        age_days = (now - c["mtime"]) / 86400 if c["mtime"] else 999
        recency = max(0.0, 1.0 - age_days / RECENCY_FULL_DAYS) if age_days < RECENCY_FULL_DAYS else \
            max(0.0, 0.3 - (age_days - RECENCY_FULL_DAYS) / 90)
        score = W_RICHNESS * richness + W_RECENCY * recency + W_LIVENESS * c["liveness"]
        # backups slightly demoted — prefer a working tree copy of equal content
        if c["is_backup"]:
            score *= 0.9
        c["richness"] = round(richness, 3)
        c["recency"] = round(recency, 3)
        c["score"] = round(score, 4)
    return sorted(cands, key=lambda c: c["score"], reverse=True)


def scan_sessions(query: str, limit_days: int = 14) -> list:
    """Light index of session transcripts that wrote/edited files matching query."""
    hits = []
    if not SESSIONS_DIR.exists():
        return hits
    cutoff = time.time() - limit_days * 86400
    q = query.lower()
    for jf in SESSIONS_DIR.glob("*/*.jsonl"):
        try:
            if jf.stat().st_mtime < cutoff:
                continue
        except Exception:
            continue
        try:
            for line in jf.open(errors="ignore"):
                if '"file_path"' not in line or "html" not in line.lower():
                    continue
                if q not in line.lower() and not any(w in line.lower() for w in q.split()):
                    continue
                m = re.search(r'"file_path"\s*:\s*"([^"]+\.html?)"', line)
                if m:
                    hits.append({
                        "session": jf.name[:18],
                        "file": m.group(1).replace(str(HOME), "~"),
                        "mtime": time.strftime("%Y-%m-%d %H:%M", time.localtime(jf.stat().st_mtime)),
                    })
        except Exception:
            continue
    # dedupe by file
    seen, out = set(), []
    for h in hits:
        if h["file"] in seen:
            continue
        seen.add(h["file"])
        out.append(h)
    return out[:40]


def render(query, ranked, sessions):
    L = [f"\n{'═'*70}", f"  LATEST BUILD FINDER — query: \"{query}\"",
         f"  {datetime.now().strftime('%Y-%m-%d %H:%M')}", "═" * 70]
    if not ranked:
        L.append("  No candidate builds found.")
        return "\n".join(L)
    win = ranked[0]
    L.append(f"\n🏆 WINNER (score {win['score']}):")
    L.append(f"   {win['path']}")
    L.append(f"   {win['title']} · {win['size']:,}b · {win['mtime_str']} · {win['feature_count']} features")
    deploy = ("✅ uses public endpoints — deploy-ready" if win["liveness"] >= 0.9 else
              "⚠️ points at localhost — must repoint endpoints to public BEFORE deploy"
              if win["local_endpoints"] and not win["public_endpoints"] else
              "⚠️ mixed endpoints — verify before deploy")
    L.append(f"   deployability: {deploy}")
    L.append(f"\n  RANKED ({len(ranked)}):")
    L.append(f"   {'score':>6} {'size':>9} {'feat':>4} {'live':>4} {'modified':>16}  path")
    for c in ranked[:12]:
        L.append(f"   {c['score']:>6} {c['size']:>9,} {c['feature_count']:>4} "
                 f"{c['liveness']:>4} {c['mtime_str']:>16}  {c['path']}")
    if sessions:
        L.append(f"\n  SESSION TRANSCRIPTS that touched matching builds ({len(sessions)}):")
        for s in sessions[:15]:
            L.append(f"   {s['mtime']}  {s['file']}  (session {s['session']})")
    L.append("\n" + "═" * 70)
    return "\n".join(L)


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    flags = {a for a in sys.argv[1:] if a.startswith("--")}
    if not args:
        print("usage: CC_latest_build_finder.py \"<query>\" [--json] [--sessions]")
        sys.exit(1)
    query = args[0]
    now = time.time()

    cands = []
    for f in _iter_files():
        sc = score_build(f, query)
        if sc:
            cands.append(sc)
    ranked = rank(cands, now)
    sessions = scan_sessions(query) if "--sessions" in flags else []

    report = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "query": query,
        "winner": ranked[0] if ranked else None,
        "ranked": ranked,
        "sessions": sessions,
    }
    try:
        REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
        REPORT_PATH.write_text(json.dumps(report, indent=2))
    except Exception:
        pass

    if "--json" in flags:
        print(json.dumps(report, indent=2))
    else:
        print(render(query, ranked, sessions))


if __name__ == "__main__":
    main()
