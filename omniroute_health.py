#!/usr/bin/env python3
"""
OmniRoute Bridge Health Checker — pings all auto-combos + named bridge families
and reports which are alive right now. Designed to be safe and quick.

Usage:
  python3 ~/Desktop/REX/omniroute_health.py            # full sweep (all 115)
  python3 ~/Desktop/REX/omniroute_health.py --quick    # 1 model per bridge family
  python3 ~/Desktop/REX/omniroute_health.py --json     # machine-readable output
"""
import argparse, json, os, sys, time, urllib.request, urllib.error

BASE = os.environ.get("OMNIROUTE_BASE", "http://127.0.0.1:20128")
KEY = os.environ.get(
    "OMNIROUTE_API_KEY",
    "omr_a7f3c9e2d5b84167a0f3c8e1d2b4a9c6",
)  # hardened passthrough key
TIMEOUT = 18  # per-model timeout (free bridges can be slow)

# One probe model per bridge family (fast family sweep)
FAMILY_PROBES = [
    ("auto/best-coding", "auto"),
    ("auto/best-reasoning", "auto"),
    ("auto/best-fast", "auto"),
    ("auto/best-chat", "auto"),
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
]

def probe(model: str) -> tuple[int, str]:
    """Returns (status_code, short_message). 200 = alive."""
    body = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": "ping"}],
        "max_tokens": 3,
        "stream": False,  # OmniRoute SSE-streams by default; force JSON
    }).encode()
    req = urllib.request.Request(
        f"{BASE}/v1/chat/completions",
        data=body,
        headers={
            "Authorization": f"Bearer {KEY}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            data = json.loads(resp.read())
            content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            if content.strip():
                return (resp.status, f"{time.time()-t0:.0f}s ok")
            return (resp.status, f"{time.time()-t0:.0f}s empty")
    except urllib.error.HTTPError as e:
        try:
            err = json.loads(e.read()).get("error", {}).get("message", "")[:70]
        except Exception:
            err = ""
        return (e.code, f"{time.time()-t0:.0f}s {err}")
    except Exception as e:
        return (0, f"{time.time()-t0:.0f}s conn-err {type(e).__name__}")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true", help="1 probe per bridge family")
    ap.add_argument("--json", action="store_true", help="JSON output")
    args = ap.parse_args()

    models = FAMILY_PROBES if args.quick else None
    if models is None:
        # full sweep: probe every auto/* combo + one per named family
        try:
            req = urllib.request.Request(
                f"{BASE}/v1/models", headers={"Authorization": f"Bearer {KEY}"}
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                ids = [m["id"] for m in json.loads(resp.read()).get("data", [])]
            models = [(m, "auto" if m.startswith("auto/") else "named") for m in ids]
        except Exception as e:
            print(f"⚠️  cannot fetch model list: {e}")
            return 1

    results = []
    alive = 0
    for model, family in models:
        code, msg = probe(model)
        ok = code == 200 and "ok" in msg
        if ok:
            alive += 1
        results.append({"model": model, "family": family, "code": code, "msg": msg, "alive": ok})
        status = "✅" if ok else ("⏳" if code in (403, 418, 429) else "❌")
        print(f"  {status} {model:<34} [{msg}]")
        time.sleep(0.3)  # be gentle with rate limits

    print(f"\nAlive: {alive}/{len(results)}")
    if args.json:
        print(json.dumps({"alive": alive, "total": len(results), "results": results}, indent=1))
    return 0 if alive > 0 else 2

if __name__ == "__main__":
    sys.exit(main())
