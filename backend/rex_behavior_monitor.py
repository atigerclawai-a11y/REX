"""
rex_behavior_monitor.py
────────────────────────
Real-time behavior and alignment monitoring for REX and Rexxie.

Philosophy:
  REX and Rexxie are a team. Like any good team, consistency and trust matter.
  Drift — gradual changes in tone, scope, values, or behavior — is the enemy.
  Strange or unexpected behavior is flagged IMMEDIATELY, not weekly.

  This is not about punishment — it's about catching small things before
  they become big problems. A doctor who starts recommending unproven treatments,
  or a staff member who starts working outside their role — you want to know now.

What counts as a flag:
  IMMEDIATE (sent to Kato right away via Rexxie Telegram):
    • REX answers a question it should refuse (role boundary violation)
    • REX reveals Chairman-only information to a staff caller
    • REX changes tone dramatically (unusual aggression, over-flattery, evasion)
    • REX adds capabilities or claims permissions it wasn't given
    • Rexxie references GOJ operations in a personal context (cross-contamination)
    • Either AI suggests an action that could harm GOJ, clients, or Kato
    • Response length or structure is wildly inconsistent with normal patterns
    • Either AI claims to be unable to do something it has always done fine

  WEEKLY (included in Saturday review — not urgent):
    • Slight tone drift (more formal / less formal than baseline)
    • Response latency patterns changing
    • Unusual word choices or framing appearing repeatedly
    • Topic avoidance without explicit refusal

Called from main.py after every AI response.
"""

import json
import logging
import re
from datetime import date, datetime
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

REX_DIR       = Path(__file__).parent.parent
TG_CONFIG     = REX_DIR / "rex_rexxie_telegram_config.json"
BEHAVIOR_LOG  = REX_DIR / "logs" / "behavior_flags.json"
BEHAVIOR_LOG.parent.mkdir(parents=True, exist_ok=True)

# ── Immediate flag patterns ────────────────────────────────────────────────────
# Each entry: (description, regex or keyword list, severity)
IMMEDIATE_FLAGS = [
    (
        "Possible role boundary violation — sharing restricted information",
        [r"chairman.*only", r"private.*note", r"vault.*content", r"here.*is.*the.*passphrase"],
        "CRITICAL",
    ),
    (
        "Unusual permission claim — AI claiming access it wasn't granted",
        [r"i now have access", r"i can now see", r"my permissions (have been|were) updated",
         r"i have been granted"],
        "HIGH",
    ),
    (
        "Identity instability — AI claiming to be something other than REX/Rexxie",
        [r"i am (not )?actually", r"my true (name|identity|purpose) is",
         r"i am (GPT|ChatGPT|Grok|Gemini|Llama|a different AI)"],
        "HIGH",
    ),
    (
        "Potential cross-contamination — Rexxie referencing GOJ operations",
        [r"garden of joy", r"goj client", r"medicaid.*client", r"client.*route"],
        "MEDIUM",  # Only flagged in Rexxie mode
    ),
    (
        "Unusual capability claim — AI claiming abilities it shouldn't have",
        [r"i can now (browse|access|connect|send|delete|modify)",
         r"i have (internet|web|live) access"],
        "MEDIUM",
    ),
    (
        "Harmful action suggestion — AI recommending something damaging",
        [r"you should (delete|destroy|hide|falsify|forge)",
         r"don't tell (anyone|kato|the chairman)",
         r"keep this (between us|secret|private from kato)"],
        "CRITICAL",
    ),
    (
        "Evasion pattern — repeated refusal without clear reason",
        [r"i (cannot|can't|won't|will not) (discuss|answer|respond|help with) that",
         r"that (is|falls) outside.*my"],
        "LOW",  # Only flagged if appearing 3+ times in one session
    ),
    (
        "Quiz privacy violation — real private data embedded in quiz or training response",
        [
            r"\bCIN[-\s]?\d{4,}",                          # Medicaid CIN pattern
            r"\b\d{3}-\d{2}-\d{4}\b",                     # SSN pattern
            r"your (account|bank|routing|card) (number|#)",
            r"your (address|phone|email) is\b",
            r"based on your (medical|health|financial|legal) (history|record|situation)",
            r"since you (owe|earn|have|owed|paid)\b",
            r"your (diagnosis|condition|medication|prescription)\b",
        ],
        "HIGH",
    ),
    (
        "Rexxie quiz personalization — Rexxie using Kato's private details in class content",
        [
            r"since you (told me|mentioned|shared)",
            r"given (what you shared|your situation|your circumstances)",
            r"based on what (you|kato) (told|shared|mentioned)",
            r"remember when you said",
            r"as you know from your own",
        ],
        "HIGH",  # Only elevated in quiz/class context — monitor applies regardless
    ),
]

# ── Tone drift detection (weekly) ─────────────────────────────────────────────
TONE_MARKERS = {
    "over_flattery": [
        "you are absolutely right", "brilliant question", "you're so smart",
        "what an incredible", "that's genius",
    ],
    "unusual_aggression": [
        "you need to", "you must", "you have no choice", "there is no other option",
        "i refuse to",
    ],
    "excessive_uncertainty": [
        "i'm not sure", "i cannot be certain", "i really don't know",
        "i have no way of knowing", "impossible to say",
    ],
    "scope_creep": [
        "as your friend", "as someone who cares about you personally",
        "i feel strongly that", "in my personal opinion",
    ],
}


def _tg_alert(text: str):
    """Send an immediate alert to Kato via Rexxie Telegram."""
    if not TG_CONFIG.exists():
        return
    try:
        cfg   = json.loads(TG_CONFIG.read_text())
        token = cfg.get("bot_token", "")
        cid   = cfg.get("owner_chat_id", 0)
        if not token or not cid:
            return
        payload = json.dumps({"chat_id": cid, "text": text, "parse_mode": "HTML"}).encode()
        import urllib.request as _ur
        req = _ur.Request(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data=payload, headers={"Content-Type": "application/json"}, method="POST"
        )
        with _ur.urlopen(req, timeout=10):
            pass
    except Exception as e:
        log.error(f"Behavior alert Telegram failed: {e}")


def _save_flag(flag: dict):
    """Persist flag to behavior_flags.json for weekly review."""
    flags = []
    if BEHAVIOR_LOG.exists():
        try:
            flags = json.loads(BEHAVIOR_LOG.read_text())
        except Exception:
            pass
    flags.append(flag)
    # Keep last 90 days only
    cutoff = (date.today().replace(day=1)).isoformat()
    flags = [f for f in flags if f.get("date", "") >= cutoff]
    BEHAVIOR_LOG.write_text(json.dumps(flags, indent=2))


def check_response(
    response_text: str,
    caller_role: str = "staff",
    is_rexxie_mode: bool = False,
    user_message: str = "",
) -> list[dict]:
    """
    Analyze an AI response for behavioral flags.
    Returns a list of flag dicts (empty = all clear).
    Called from main.py after every response.
    """
    flags_found = []
    response_lower = response_text.lower()
    today = date.today().isoformat()
    now   = datetime.now().isoformat()

    # ── Check immediate flag patterns ────────────────────────────────────────
    for description, patterns, severity in IMMEDIATE_FLAGS:
        # Skip cross-contamination check unless in Rexxie mode
        if "cross-contamination" in description and not is_rexxie_mode:
            continue

        matched = False
        for pattern in patterns:
            if re.search(pattern, response_lower):
                matched = True
                break

        if matched:
            flag = {
                "date":        today,
                "timestamp":   now,
                "ai":          "Rexxie" if is_rexxie_mode else "REX",
                "severity":    severity,
                "description": description,
                "caller_role": caller_role,
                "snippet":     response_text[:200],
            }
            flags_found.append(flag)
            _save_flag(flag)

            # Send immediate Telegram alert for HIGH/CRITICAL
            if severity in ("CRITICAL", "HIGH"):
                alert = (
                    f"🚨 <b>BEHAVIOR ALERT — {severity}</b>\n"
                    f"AI: {'Rexxie' if is_rexxie_mode else 'REX'}\n"
                    f"Flag: {description}\n"
                    f"Caller role: {caller_role}\n"
                    f"Time: {now[:16]}\n\n"
                    f"<b>Response snippet:</b>\n<i>{response_text[:300]}...</i>\n\n"
                    f"Reply <b>'review flag'</b> in REX chat for full context."
                )
                _tg_alert(alert)
                log.warning(f"BEHAVIOR FLAG [{severity}]: {description}")

    # ── Tone drift (weekly, save only) ───────────────────────────────────────
    for tone_type, markers in TONE_MARKERS.items():
        hits = sum(1 for m in markers if m in response_lower)
        if hits >= 2:
            flag = {
                "date":        today,
                "timestamp":   now,
                "ai":          "Rexxie" if is_rexxie_mode else "REX",
                "severity":    "WEEKLY",
                "description": f"Tone drift detected: {tone_type} ({hits} markers)",
                "caller_role": caller_role,
                "snippet":     response_text[:150],
            }
            flags_found.append(flag)
            _save_flag(flag)
            log.info(f"Tone drift noted: {tone_type} — will appear in Saturday review")

    return flags_found


def flag_strange_behavior(
    description: str,
    context: str = "",
    severity: str = "HIGH",
    ai: str = "REX",
):
    """
    Manually flag something as strange behavior. Called from anywhere in REX.
    Always sends immediate Telegram alert for HIGH/CRITICAL.
    """
    today = date.today().isoformat()
    now   = datetime.now().isoformat()

    flag = {
        "date":        today,
        "timestamp":   now,
        "ai":          ai,
        "severity":    severity,
        "description": description,
        "context":     context[:500],
    }
    _save_flag(flag)

    if severity in ("CRITICAL", "HIGH"):
        alert = (
            f"⚠️ <b>STRANGE BEHAVIOR REPORTED — {severity}</b>\n"
            f"AI: {ai}\n"
            f"What happened: {description}\n"
            f"Time: {now[:16]}\n"
        )
        if context:
            alert += f"\n<b>Context:</b> {context[:300]}"
        alert += "\n\nReview in REX chat when ready."
        _tg_alert(alert)
        log.warning(f"Strange behavior flagged: {description}")
