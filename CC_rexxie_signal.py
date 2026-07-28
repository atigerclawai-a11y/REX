#!/usr/bin/env python3
"""
CC_rexxie_signal.py — Rexxie's PRIVATE assistant brain over Signal (end-to-end encrypted).

Fully local: encrypted transport (Signal via signal-cli) + off-cloud brain (Ollama local LLM) +
encrypted perpetual memory (rexxie.db via RexxieMemory) + full build knowledge. Kato-only.
Nothing of Kato's ever leaves the Mac except E2E-encrypted to his phone.

Test the brain (no Signal needed):  python3 CC_rexxie_signal.py "what did we build today?"
Run the Signal loop:                python3 CC_rexxie_signal.py --serve
Env: REXXIE_SIGNAL_NUMBER (Rexxie's registered Signal #), KATO_SIGNAL_NUMBER (default 347), REXXIE_MODEL.
"""
import os, re, sys, json, time, subprocess, urllib.request
from collections import deque
from pathlib import Path

REX = Path(__file__).resolve().parent
KNOWLEDGE = REX / "CC_REXXIE_BUILD_KNOWLEDGE.md"
OLLAMA = "http://localhost:11434/api/chat"
MODEL = os.environ.get("REXXIE_MODEL", "llama3.2:3b")
KATO = os.environ.get("KATO_SIGNAL_NUMBER", "+13475879913")
REXXIE_NUM = os.environ.get("REXXIE_SIGNAL_NUMBER", "")
MAX_REPLY = 3500   # Signal message cap guard

# HARD LOCAL-ONLY ENFORCEMENT: Rexxie's brain must never be a cloud endpoint or cloud model.
if not OLLAMA.startswith(("http://localhost", "http://127.0.0.1")):
    raise SystemExit("Rexxie refuses: LLM endpoint must be localhost (never cloud).")
if any(c in MODEL.lower() for c in ("gpt", "claude", "gemini", "deepseek", "/")):
    raise SystemExit(f"Rexxie refuses: REXXIE_MODEL '{MODEL}' looks like a cloud model. Use a local Ollama model.")

SYSTEM = (
    "You are Rexxie — Kato's private, loyal personal assistant. You run fully locally and NEVER "
    "send Kato's data to the cloud. You know his entire build (in your memory) and you keep learning "
    "about him. Be concise, warm, and direct — Kato dislikes fluff. You are his alone."
)

_sys_path_added = False
_mem = None


def _memory():
    """Cached RexxieMemory (one encrypted-DB handle, sys.path inserted once)."""
    global _mem, _sys_path_added
    if not _sys_path_added:
        sys.path.insert(0, str(REX / "backend"))
        _sys_path_added = True
    if _mem is None:
        from rex_rexxie import RexxieMemory
        _mem = RexxieMemory()
    return _mem


def _e164(n: str) -> str:
    d = re.sub(r"\D", "", n or "")
    return d if len(d) >= 11 else ""   # require full international number


def _is_kato(num: str) -> bool:
    return bool(_e164(num)) and _e164(num) == _e164(KATO)


def _recall(n: int = 4) -> str:
    """Bounded recent memory (decrypts only N rows). Empty on any failure."""
    try:
        items = _memory().get_recent(n)
        return "\n".join(str(x)[:300] for x in (items or []))
    except Exception:
        return ""


def _context() -> str:
    # Lean by default for speed; full build knowledge is injected only for build questions.
    # No PII (e.g. phone numbers) in the system prompt.
    parts = [SYSTEM, "\nThe full build history is in your memory — recall it when asked."]
    recent = _recall()
    if recent:
        parts.append("\nRecent memory:\n" + recent)
    return "\n".join(parts)


def _is_build_question(text: str) -> bool:
    t = text.lower()
    return any(w in t for w in ("build", "what did we", "victoria", "masha", "ocr",
                                "security", "presidio", "number", "what have we", "history"))


def _save(user_text: str, reply: str):
    try:
        _memory().store(f"Kato: {user_text}\nRexxie: {reply}", "conversation")
    except Exception as e:
        print(f"[memory] not saved ({e})", file=sys.stderr)


def _llm(user_text: str) -> str:
    sysctx = _context()
    if _is_build_question(user_text) and KNOWLEDGE.exists():
        sysctx += "\n\n=== FULL BUILD KNOWLEDGE ===\n" + KNOWLEDGE.read_text()
    body = {"model": MODEL, "stream": False,
            "messages": [{"role": "system", "content": sysctx},
                         {"role": "user", "content": user_text}]}
    req = urllib.request.Request(OLLAMA, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=180) as r:
        return json.load(r)["message"]["content"].strip()


def respond(user_text: str) -> str:
    try:
        reply = _llm(user_text)
    except Exception as e:
        return f"(local brain unreachable: {e}) — is Ollama running with {MODEL}?"
    if len(reply) > MAX_REPLY:
        reply = reply[:MAX_REPLY] + " …[truncated]"
    _save(user_text, reply)
    return reply


# ── Signal transport (signal-cli) ────────────────────────────────────────────
def _signal_send(to: str, text: str) -> bool:
    try:
        r = subprocess.run(["signal-cli", "-a", REXXIE_NUM, "send", "-m", text[:MAX_REPLY], to],
                           capture_output=True, text=True, timeout=60)
        if r.returncode != 0:
            print(f"[signal] send failed: {r.stderr.strip()[:200]}", file=sys.stderr)
            return False
        return True
    except Exception as e:
        print(f"[signal] send error: {e}", file=sys.stderr)
        return False


def _serve():
    if not REXXIE_NUM:
        print("Set REXXIE_SIGNAL_NUMBER (register Rexxie with signal-cli first). See deploy notes.")
        return
    print(f"Rexxie listening on Signal as {REXXIE_NUM}; replies to Kato only. Ctrl-C to stop.")
    seen = set()                 # dedup by message timestamp (membership)
    seen_q = deque(maxlen=600)   # ordered window; oldest auto-evicts so we keep the NEWEST
    backoff = 3
    while True:
        try:
            out = subprocess.run(["signal-cli", "-a", REXXIE_NUM, "receive", "--json"],
                                 capture_output=True, text=True, timeout=120).stdout
            backoff = 3
            for line in out.splitlines():
                try:
                    env = json.loads(line).get("envelope", {})
                except Exception:
                    continue
                dm = env.get("dataMessage")           # only real text messages (skip receipts/typing/sync)
                if not isinstance(dm, dict):
                    continue
                msg = dm.get("message")
                src = env.get("sourceNumber") or ""   # E.164 sender; NOT the ACI uuid
                ts = env.get("timestamp")
                if not msg or ts in seen:
                    continue
                if not _is_kato(src) or _e164(src) == _e164(REXXIE_NUM):  # Kato only; never self
                    continue
                seen.add(ts); seen_q.append(ts)
                if len(seen) > seen_q.maxlen:   # resync to the newest window
                    seen = set(seen_q)
                _signal_send(KATO, respond(msg))
        except subprocess.TimeoutExpired:
            continue
        except Exception as e:
            print(f"[signal] {e}; backing off {backoff}s", file=sys.stderr)
            time.sleep(backoff)
            backoff = min(backoff * 2, 60)
            continue
        time.sleep(3)


def main() -> int:
    if "--serve" in sys.argv:
        _serve(); return 0
    text = " ".join(a for a in sys.argv[1:] if not a.startswith("--")) or "Who are you?"
    print(respond(text))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
