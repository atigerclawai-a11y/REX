#!/usr/bin/env python3
"""
CC_safe_update.py — update an existing build WITHOUT spawning duplicates/false gateways
=======================================================================================
Kato's rule: any change to an already-made build must (1) find THE canonical
served version, (2) edit only a COPY of it, (3) swap that copy into the SAME
section/port in place — never a new file, site, port, or subdomain. This agent
enforces exactly that, with automatic backup + verify + rollback.

Workflow:
    python3 CC_safe_update.py list                       # show the registered canonical builds
    python3 CC_safe_update.py locate  <artifact>         # find the one true file + where it serves
    python3 CC_safe_update.py stage   <artifact>         # make an editable COPY → prints its path
    python3 CC_safe_update.py promote <artifact> [copy]  # backup canonical, swap copy in, verify (auto-rollback on fail)
    python3 CC_safe_update.py verify  <artifact>         # is it serving?
    python3 CC_safe_update.py register <artifact> <file> <serves_at> [local]

    # Unknown artifact? It falls back to scraping with CC_latest_build_finder.

Registry: ~/.rex_infra/build_registry.json   (the map of artifact → canonical file + serving location)
Backups:  <canonical>.bak_<timestamp>  (kept next to the file, never deleted automatically)
"""

import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

HOME = Path.home()
REGISTRY = HOME / ".rex_infra" / "build_registry.json"
FINDER = HOME / "Desktop" / "REX" / "CC_latest_build_finder.py"


def _expand(p: str) -> Path:
    return Path(os.path.expanduser(p))


def load_registry() -> dict:
    if REGISTRY.exists():
        try:
            return json.loads(REGISTRY.read_text()).get("artifacts", {})
        except Exception as e:
            print(f"⚠️  bad registry: {e}")
    return {}


def save_registry(arts: dict) -> None:
    data = {"_comment": "Canonical build registry for CC_safe_update.", "artifacts": arts}
    REGISTRY.parent.mkdir(parents=True, exist_ok=True)
    REGISTRY.write_text(json.dumps(data, indent=2))


def resolve(artifact: str) -> tuple[str, dict] | tuple[None, None]:
    """Match an artifact by key or alias."""
    arts = load_registry()
    q = artifact.lower().strip()
    if q in arts:
        return q, arts[q]
    for key, entry in arts.items():
        if q == key.lower() or q in [a.lower() for a in entry.get("aliases", [])]:
            return key, entry
    return None, None


def http_alive(url: str) -> tuple[bool, int]:
    """A serving endpoint returns ANY HTTP code (200/3xx/401/403 all mean 'up'); 0/5xx = down."""
    if not url:
        return True, 0  # nothing to verify (e.g. a daemon) — treat as ok
    req = urllib.request.Request(url, headers={"User-Agent": "safe-update/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return True, r.getcode()
    except urllib.error.HTTPError as e:
        return (e.code < 500), e.code   # 401/403/404 = server is up
    except Exception:
        return False, 0


# ── commands ──────────────────────────────────────────────────────────────────

def cmd_list():
    arts = load_registry()
    print(f"\n{len(arts)} registered canonical build(s):\n")
    for key, e in arts.items():
        cf = _expand(e["canonical"])
        exists = "✅" if cf.exists() else "❌MISSING"
        print(f"  {key:16} {exists}  {e['canonical']}")
        print(f"  {'':16}     serves: {e.get('serves_at') or e.get('local') or '(daemon)'}  [{e.get('kind')}]")
    print()


def cmd_locate(artifact: str):
    key, e = resolve(artifact)
    if not e:
        print(f"'{artifact}' not registered — scraping with CC_latest_build_finder…\n")
        if FINDER.exists():
            subprocess.run([sys.executable, str(FINDER), artifact])
        else:
            print("  (build finder not found)")
        return
    cf = _expand(e["canonical"])
    print(f"\n🎯 {key}")
    print(f"   canonical : {e['canonical']}  ({'exists' if cf.exists() else 'MISSING'}, "
          f"{cf.stat().st_size:,}b)" if cf.exists() else f"   canonical : {e['canonical']} (MISSING)")
    print(f"   serves at : {e.get('serves_at') or e.get('local')}")
    print(f"   kind      : {e.get('kind')}")
    print(f"   ⚠️  Edit a COPY (stage), then promote — never create a new file/port.\n")


def cmd_stage(artifact: str):
    key, e = resolve(artifact)
    if not e:
        print(f"❌ '{artifact}' not registered. Use: register <artifact> <file> <serves_at>")
        return
    cf = _expand(e["canonical"])
    if not cf.exists():
        print(f"❌ canonical missing: {cf}")
        return
    ts = time.strftime("%Y%m%d_%H%M%S")
    working = cf.with_suffix(cf.suffix + f".working_{ts}")
    shutil.copy2(cf, working)
    print(f"\n✅ staged editable copy:\n   {working}")
    print(f"\n   Edit THAT file. When ready:")
    print(f"     python3 CC_safe_update.py promote {key}")
    print(f"   (promotes the newest .working_* copy into {e['canonical']} in place)\n")


def _latest_working(cf: Path) -> Path | None:
    cands = sorted(cf.parent.glob(cf.name + ".working_*"), key=lambda p: p.stat().st_mtime, reverse=True)
    return cands[0] if cands else None


def cmd_promote(artifact: str, explicit_copy: str | None = None):
    key, e = resolve(artifact)
    if not e:
        print(f"❌ '{artifact}' not registered.")
        return
    cf = _expand(e["canonical"])
    working = _expand(explicit_copy) if explicit_copy else _latest_working(cf)
    if not working or not working.exists():
        print(f"❌ no staged copy found. Run: python3 CC_safe_update.py stage {key}")
        return

    # 1. backup the current canonical
    ts = time.strftime("%Y%m%d_%H%M%S")
    backup = cf.with_suffix(cf.suffix + f".bak_{ts}")
    shutil.copy2(cf, backup)
    print(f"  📦 backed up canonical → {backup.name}")

    # 2. swap the copy in place (SAME path = same section/port; no new gateway)
    shutil.copy2(working, cf)
    print(f"  🔁 promoted {working.name} → {cf.name} (in place)")

    # 3. restart if needed, then verify it still serves
    restart = (e.get("restart") or "").replace("$UID", str(os.getuid()))
    if restart:
        subprocess.run(restart, shell=True, capture_output=True)
        time.sleep(5)
    target = e.get("local") or e.get("serves_at")
    ok, code = http_alive(target) if target else (True, 0)
    if ok:
        print(f"  ✅ verified serving ({target or 'daemon'} → HTTP {code or 'n/a'})")
        print(f"  done — {key} updated in place, no duplicate created. Backup: {backup.name}")
    else:
        # 4. auto-rollback on failure
        shutil.copy2(backup, cf)
        if restart:
            subprocess.run(restart, shell=True, capture_output=True)
        print(f"  ❌ verify FAILED ({target} → HTTP {code}) — ROLLED BACK to backup. No change shipped.")


def cmd_verify(artifact: str):
    key, e = resolve(artifact)
    if not e:
        print(f"❌ '{artifact}' not registered.")
        return
    target = e.get("local") or e.get("serves_at")
    ok, code = http_alive(target) if target else (True, 0)
    print(f"  {key}: {'✅ up' if ok else '❌ DOWN'}  ({target or 'daemon'} → HTTP {code or 'n/a'})")


def cmd_register(artifact: str, file: str, serves_at: str = "", local: str = ""):
    arts = load_registry()
    arts[artifact.lower()] = {
        "canonical": file, "serves_at": serves_at, "local": local,
        "kind": "custom", "restart": "", "aliases": [],
    }
    save_registry(arts)
    print(f"✅ registered '{artifact}' → {file}")


def main():
    a = sys.argv[1:]
    if not a:
        print(__doc__); return
    cmd = a[0]
    if cmd == "list":
        cmd_list()
    elif cmd == "locate" and len(a) > 1:
        cmd_locate(a[1])
    elif cmd == "stage" and len(a) > 1:
        cmd_stage(a[1])
    elif cmd == "promote" and len(a) > 1:
        cmd_promote(a[1], a[2] if len(a) > 2 else None)
    elif cmd == "verify" and len(a) > 1:
        cmd_verify(a[1])
    elif cmd == "register" and len(a) >= 3:
        cmd_register(a[1], a[2], a[3] if len(a) > 3 else "", a[4] if len(a) > 4 else "")
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
