#!/usr/bin/env python3
"""
CC_chairman_assistant.py — Kato's personal SMS assistant (Chairman Assistant).

Kato-only: texts from his number (347-587-9913) → chairman mode; anyone else gets a
polite decline. Sensitive actions (timesheets/payroll/data pulls) require a PIN.
GOJ data is DE-IDENTIFIED before any cloud LLM call (reuses Gate 1 / Presidio).

Commands (no LLM needed): "help", "results"/"calls" (today's de-id GOJ summary).
Anything else → conversational reply via Claude (de-identified).

Security: the Twilio webhook (--serve) validates X-Twilio-Signature (fail-closed).
Set TWILIO_AUTH_TOKEN and CHAIRMAN_WEBHOOK_URL (the public https URL) in ~/.hermes/.env.

Test:   python3 CC_chairman_assistant.py "results"            # as Kato
        python3 CC_chairman_assistant.py --from +15551234567 "hi"   # as a stranger
Serve:  python3 CC_chairman_assistant.py --serve               # Twilio SMS webhook on :8110
"""
import os, re, sys, json, html, time, datetime, tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from CC_chairman_notify import goj_summary, henv, KATO  # reuse

SESSION_PATH = Path.home() / "Desktop" / "REX" / "logs" / "chairman_session.json"
SENSITIVE = ("timesheet", "payroll", "salary", "ssn", "financ", "bank", "vault")
PIN_TTL = 300          # seconds a PIN prompt stays valid
PIN_MAX_FAILS = 3      # wrong PINs before lockout
LOCKOUT = 900          # seconds locked out after too many fails


def _pin() -> str:
    return henv("CHAIRMAN_PIN") or ""   # read lazily so a rotated PIN takes effect


def _norm(n: str) -> str:
    """Full-E.164 digit normalization (no last-10 truncation → no cross-country collision)."""
    return re.sub(r"\D", "", n or "")


def _is_kato(frm: str) -> bool:
    return bool(_norm(frm)) and _norm(frm) == _norm(KATO)


def _load_session() -> dict:
    if SESSION_PATH.exists():
        try:
            return json.loads(SESSION_PATH.read_text())
        except Exception:
            pass
    return {}


def _save_session(s: dict):
    SESSION_PATH.parent.mkdir(parents=True, exist_ok=True)
    # atomic write with 0600 perms (contains pending-action state)
    fd, tmp = tempfile.mkstemp(dir=str(SESSION_PATH.parent), prefix=".sess_")
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w") as f:
            json.dump(s, f)
        os.replace(tmp, SESSION_PATH)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    try:
        os.chmod(SESSION_PATH, 0o600)
    except OSError:
        pass


def _llm_reply(body: str) -> str:
    """Conversational reply via Claude, de-identified first (fail-safe)."""
    # Gate 1 / Presidio: must strip all PHI or we refuse to leave the Mac.
    try:
        sys.path.insert(0, str(Path.home() / "Desktop" / "dashboard"))
        import akc_tokenizer as gate
    except ImportError:
        return "I can't answer that securely right now (Gate 1 unavailable). Try 'results' or 'help'."
    try:
        safe, mapping = gate.assert_safe_for_cloud(body)  # raises if PHI survives
    except Exception:
        return "I can't answer that securely — it may contain protected info. Try 'results' or 'help'."
    try:
        sys.path.insert(0, str(Path.home() / "Desktop" / "REX" / "backend"))
        from config import Settings
        import anthropic
        client = anthropic.Anthropic(api_key=Settings().get_api_key("anthropic"))
        msg = client.messages.create(
            model=os.environ.get("REX_CHAIRMAN_MODEL", "claude-sonnet-4-6"),
            max_tokens=300,
            system=("You are Kato's concise personal assistant (Chairman of Gold Health "
                    "Systems). Reply briefly and warmly for SMS. Kato dislikes fluff."),
            messages=[{"role": "user", "content": safe}],
        )
        out = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text").strip()
        return gate.get_gate().detokenize(out, mapping) if mapping else out
    except Exception:
        return "Assistant is offline. Try 'results' or 'help'."


def handle_sms(frm: str, body: str) -> str:
    if not _is_kato(frm):
        return "This is a private line."
    text = (body or "").strip()
    low = text.lower()
    sess = _load_session()
    now = int(time.time())

    # Lockout after repeated wrong PINs
    if sess.get("lockout_until", 0) > now:
        mins = (sess["lockout_until"] - now) // 60 + 1
        return f"Too many wrong PINs. Locked for ~{mins} min."

    # PIN reply for a pending sensitive action
    pending = sess.get("awaiting_pin_for")
    if pending:
        # expired prompt
        if sess.get("pin_expires", 0) <= now:
            sess.pop("awaiting_pin_for", None); sess.pop("pin_from", None); sess.pop("pin_expires", None)
            _save_session(sess)
            return "That request expired. Re-send it if you still need it."
        # sender must match the one who started the prompt (defeats number-spoof racing)
        if sess.get("pin_from") and _norm(sess["pin_from"]) != _norm(frm):
            return "This is a private line."
        if _pin() and text == _pin():
            label = pending
            for k in ("awaiting_pin_for", "pin_from", "pin_expires", "pin_fails"):
                sess.pop(k, None)
            _save_session(sess)
            return f"PIN ok. (Action '{label}' — secure delivery to your email is pending a data source.)"
        # wrong PIN
        fails = int(sess.get("pin_fails", 0)) + 1
        if fails >= PIN_MAX_FAILS:
            for k in ("awaiting_pin_for", "pin_from", "pin_expires", "pin_fails"):
                sess.pop(k, None)
            sess["lockout_until"] = now + LOCKOUT
            _save_session(sess)
            return "Too many wrong PINs. Locked for ~15 min."
        sess["pin_fails"] = fails; _save_session(sess)
        return f"PIN incorrect ({PIN_MAX_FAILS - fails} left). Reply with your PIN, or text 'cancel'."

    if low == "cancel":
        for k in ("awaiting_pin_for", "pin_from", "pin_expires", "pin_fails"):
            sess.pop(k, None)
        _save_session(sess)
        return "Cancelled."

    if low in ("help", "menu", "?"):
        return ("Chairman Assistant. Try: 'results' (today's GOJ calls, de-identified), "
                "or just ask me a question. Sensitive items (timesheets) need your PIN.")
    if "result" in low or "call" in low:
        return goj_summary(datetime.date.today().isoformat())
    if any(s in low for s in SENSITIVE):
        if not _pin():
            return "Sensitive actions need a PIN, but none is set (CHAIRMAN_PIN in ~/.hermes/.env)."
        matched = next(s for s in SENSITIVE if s in low)  # store the keyword, not raw body
        sess.update({"awaiting_pin_for": matched, "pin_from": _norm(frm),
                     "pin_expires": now + PIN_TTL, "pin_fails": 0})
        _save_session(sess)
        return "That's sensitive — reply with your PIN to proceed."
    return _llm_reply(text)


def _serve(port: int = 8110):
    from http.server import BaseHTTPRequestHandler, HTTPServer
    import urllib.parse

    auth_token = henv("TWILIO_AUTH_TOKEN") or ""
    public_url = (henv("CHAIRMAN_WEBHOOK_URL") or "").strip()
    try:
        from twilio.request_validator import RequestValidator
        validator = RequestValidator(auth_token) if auth_token else None
    except ImportError:
        validator = None

    class H(BaseHTTPRequestHandler):
        def _deny(self, code=403):
            self.send_response(code); self.end_headers()

        def do_POST(self):
            n = int(self.headers.get("Content-Length", 0))
            raw = self.rfile.read(n).decode()
            form = urllib.parse.parse_qs(raw)
            params = {k: v[0] for k, v in form.items()}

            # Fail-closed Twilio signature validation (public surface).
            sig = self.headers.get("X-Twilio-Signature", "")
            if not (validator and public_url and sig and validator.validate(public_url, params, sig)):
                return self._deny(403)

            frm = (form.get("From") or [""])[0]
            body = (form.get("Body") or [""])[0]
            reply = handle_sms(frm, body)
            twiml = f"<Response><Message>{html.escape(reply)}</Message></Response>"
            self.send_response(200)
            self.send_header("Content-Type", "text/xml")
            self.end_headers()
            self.wfile.write(twiml.encode())

        def log_message(self, *a):
            pass

    if not (auth_token and public_url and validator):
        print("WARNING: TWILIO_AUTH_TOKEN / CHAIRMAN_WEBHOOK_URL / twilio lib missing — "
              "webhook will reject ALL requests (fail-closed). Set them in ~/.hermes/.env.")
    print(f"Chairman Assistant SMS webhook on :{port} (point the Twilio Messaging webhook here via the tunnel)")
    HTTPServer(("127.0.0.1", port), H).serve_forever()


def main() -> int:
    args = sys.argv[1:]
    if "--serve" in args:
        _serve()
        return 0
    frm = KATO
    if "--from" in args:
        i = args.index("--from"); frm = args[i + 1]; args = args[:i] + args[i + 2:]
    body = " ".join(args) or "help"
    print(handle_sms(frm, body))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
