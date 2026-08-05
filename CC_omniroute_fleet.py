#!/usr/bin/env python3
"""
CC_omniroute_fleet.py — OmniRoute free-provider fleet monitor.

Borrows TokenRouter's "auto-enable public free models" idea SAFELY:
- Probes each bridge family through OmniRoute's OWN /v1/chat/completions
  (the safe path — requests flow through OmniRoute's built-in providers,
  which are curated public endpoints; this script NEVER scans localhost
  or opens raw connections to arbitrary ports).
- Maintains a persistent fleet-state JSON that the Hermes Studio panel
  and cron watchdogs can consume.
- Flags dead/rate-limited families so routes can be re-checked, NOT
  hammered (spaced probes, 1 model per family, max_tokens=3).

Usage:
  python3 CC_omniroute_fleet.py                 # full sweep → fleet_status.json
  python3 CC_omniroute_fleet.py --quick          # 1 probe per family only
  python3 CC_omniroute_fleet.py --json           # print state as JSON
  python3 CC_omniroute_fleet.py --family felo    # probe one family

State file: ~/.omniroute/fleet_status.json
"""
import argparse, json, os, sys, time, urllib.request, urllib.error

BASE = os.environ.get("OMNIROUTE_BASE", "http://127.0.0.1:20128")
KEY = os.environ.get("OMNIROUTE_API_KEY", "omr_a7f3c9e2d5b84167a0f3c8e1d2b4a9c6")
STATE_PATH = os.path.expanduser("~/.omniroute/fleet_status.json")
TIMEOUT = 18  # free bridges can be slow; keep per-probe cap sane
SPACING = 1.5  # seconds between probes — never hammer a free bridge

# One probe model per bridge family. Families come from OmniRoute's own
# model catalog (/v1/models); curated here so the sweep stays fast.
FAMILY_PROBES = [
    ("auto/best-coding", "auto"),
    ("auto/best-reasoning", "auto"),
    ("auto/best-fast", "auto"),
    ("auto/best-chat", "auto"),
    ("auto/best-vision", "auto"),
    ("auto/gemini", "auto"),
    ("auto/claude-sonnet", "auto"),
    ("auto/best-free", "auto"),
    ("aug/gpt5.2", "auggie"),
    ("ddgw/gpt-5.4-mini", "duckduckgo"),
    ("felo/felo-chat", "felo"),
    ("oc/deepseek-v4-flash-free", "opencode"),
    ("pepper/pepper-1", "chipotle"),
    ("tllm/CLAUDE_4_6_SONNET", "theoldllm"),
    ("veo-free/veo", "veofree"),
    ("mcode/terminal-code", "mcode"),
]


def probe(model: str) -> tuple[int, str]:
    """Return (status_code, short_message). 200 = alive."""
    body = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": "ping"}],
        "max_tokens": 3,
        "stream": False,  # OmniRoute SSE-streams by default; force JSON
    }).encode()
    req = urllib.request.Request(
        f"{BASE}/v1/chat/completions",
        data=body,
        headers={"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"},
    )
    try:
        t0 = time.time()
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            dt = round(time.time() - t0, 1)
            data = json.loads(resp.read().decode())
            content = (data.get("choices") or [{}])[0].get("message", {}).get("content", "")
            return resp.status, f"alive ({dt}s)" + (f" → {content[:20]}" if content else "")
    except urllib.error.HTTPError as e:
        return e.code, f"HTTP {e.code}"
    except urllib.error.URLError as e:
        return 0, f"conn-err {e.reason}"
    except Exception as e:
        return 0, f"err {type(e).__name__}"


def load_state() -> dict:
    try:
        return json.load(open(STATE_PATH))
    except Exception:
        return {"checked_at": None, "families": {}}


def save_state(state: dict):
    os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
    with open(STATE_PATH, "w") as f:
        json.dump(state, f, indent=2)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true", help="one probe per family")
    ap.add_argument("--json", action="store_true", help="print state as JSON")
    ap.add_argument("--family", type=str, default=None, help="probe one family")
    args = ap.parse_args()

    state = load_state()
    now = time.strftime("%Y-%m-%dT%H:%M:%S")

    probes = FAMILY_PROBES
    if args.family:
        probes = [p for p in probes if p[1] == args.family] or [(args.family, args.family)]

    alive = dead = 0
    for model, fam in probes:
        code, msg = probe(model)
        fam_state = state.setdefault("families", {}).setdefault(fam, {})
        fam_state.update({
            "probe_model": model,
            "status": "alive" if code == 200 else ("rate-limited" if code in (418, 429) else "down"),
            "code": code,
            "msg": msg,
            "checked_at": now,
        })
        if code == 200:
            alive += 1
        else:
            dead += 1
        if not args.json:
            mark = "✅" if code == 200 else ("⏳" if code in (418, 429) else "❌")
            print(f"  {mark} {fam:<14} {model:<32} [{code}] {msg}")
        time.sleep(SPACING)

    state["checked_at"] = now
    state["summary"] = {"families_probed": len(probes), "alive": alive, "down": dead}
    save_state(state)

    if args.json:
        print(json.dumps(state, indent=2))
    else:
        print(f"\nFleet: {alive}/{len(probes)} alive → {STATE_PATH}")


if __name__ == "__main__":
    main()
