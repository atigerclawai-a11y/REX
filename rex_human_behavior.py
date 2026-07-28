"""
rex_human_behavior.py
─────────────────────
Rexxie GOJ – Human-Like Behavior Post-Processor

Strips AI filler phrases, controls verbosity, enforces tone consistency,
and makes responses feel warm and direct — like a real admin assistant,
not a language model.

Usage:
    from rex_human_behavior import humanize

    raw = "Certainly! That's a great question. I'd be happy to help you..."
    clean = humanize(raw, context="goj")
"""

from __future__ import annotations

import re
import logging
from typing import Optional

logger = logging.getLogger("rex.human_behavior")

# ─────────────────────────────────────────────
# FILLER PHRASE BANKS
# These are stripped from the START of responses
# ─────────────────────────────────────────────

_OPENING_FILLERS: list[tuple[str, str]] = [
    # pattern → replacement (empty = delete the whole opener)
    (r"^Certainly[,!\.]*\s*", ""),
    (r"^Of course[,!\.]*\s*", ""),
    (r"^Absolutely[,!\.]*\s*", ""),
    (r"^Sure[,!\.]*\s*", ""),
    (r"^Great[,!\.]*\s*", ""),
    (r"^Great question[,!\.]*\s*", ""),
    (r"^That'?s? a great question[,!\.]*\s*", ""),
    (r"^Excellent question[,!\.]*\s*", ""),
    (r"^Wonderful[,!\.]*\s*", ""),
    (r"^Fantastic[,!\.]*\s*", ""),
    (r"^Happy to help[,!\.]*\s*", ""),
    (r"^I'?d be happy to help[,!\.]*\s*", ""),
    (r"^I'?m happy to help[,!\.]*\s*", ""),
    (r"^I'?d be glad to help[,!\.]*\s*", ""),
    (r"^I'?d love to help[,!\.]*\s*", ""),
    (r"^Of course[,!]?\s*", ""),
    (r"^Noted[,!\.]*\s*", ""),
    (r"^Hello[,!]?\s*(?:there[,!]?)?\s*", ""),
    (r"^Hi[,!]?\s*(?:there[,!]?)?\s*", ""),
    (r"^Hey[,!]?\s*(?:there[,!]?)?\s*", ""),
    (r"^Thank you for (?:asking|reaching out|your message)[,!\.]*\s*", ""),
    (r"^Thanks for (?:asking|reaching out|your message)[,!\.]*\s*", ""),
    (r"^As an AI (?:language model|assistant)[,\s]*", ""),
    (r"^As an AI[,\s]*", ""),
    (r"^As a (?:helpful |digital |virtual )?assistant[,\s]*", ""),
    (r"^I (?:understand|see|hear you)[,!\.]*\s*", ""),
    (r"^I'?m sorry to hear that[,\s]*", "I understand — "),
    (r"^I apologize for any confusion[,\s]*", ""),
    (r"^Let me (?:go ahead and |just )?", ""),
    (r"^Allow me to\s*", ""),
    (r"^I'?ll go ahead and\s*", ""),
]

# Phrases stripped ANYWHERE in the response
_INLINE_FILLERS: list[tuple[str, str]] = [
    (r"\bfeel free to\b", "you can"),
    (r"\bdon'?t hesitate to\b", ""),
    (r"\bplease don'?t hesitate to (?:ask|reach out)[^.]*\.\s*", ""),
    (r"\bif you have any (?:other |more |further )?questions[^.]*\.\s*", ""),
    (r"\bhope this helps[.!]*\s*", ""),
    (r"\bI hope that (?:helps|answers your question)[.!]*\s*", ""),
    (r"\bIs there anything else I can help you with\??[^.]*[.!]?\s*", ""),
    (r"\bIs there anything else[^?]*\?\s*", ""),
    (r"\bLet me know if you need (?:anything else|further help|more information)[^.]*\.\s*", ""),
    (r"\bPlease let me know if[^.]*\.\s*", ""),
    (r"\bAs always[,\s]*", ""),
    (r"\bOf course[,!\s]*", ""),
    (r"\bCertainly[,!\s]*", ""),
    (r"\bAbsolutely[,!\s]*", ""),
    (r"\bDefinitely[,!\s]*", ""),
    # Mid-response AI identity leaks
    (r"As an AI (?:language model|assistant)[,\s]*", ""),
    (r"As an AI[,\s]*", ""),
    (r"As a (?:helpful |digital |virtual )?assistant[,\s]*", ""),
    # Closing padding lines
    (r"\bIn conclusion[,\s]+", ""),
    (r"\bTo summarize[,\s]+", "In short, "),
    (r"\bIn summary[,\s]+", "In short, "),
]

# ─────────────────────────────────────────────
# VERBOSITY CONTROL
# Truncate if response is bloated
# ─────────────────────────────────────────────

_MAX_CHARS_DEFAULT = 1200   # Telegram comfortable read length
_MAX_CHARS_BRIEF   = 500    # For quick factual replies
_MAX_CHARS_REPORT  = 3500   # For reports/summaries

# ─────────────────────────────────────────────
# TONE RULES
# GOJ context: warm, direct, professional
# ─────────────────────────────────────────────

_TONE_REPLACEMENTS: list[tuple[str, str]] = [
    # Passive → active voice shortcuts
    (r"\bit should be noted that\b", "note:"),
    (r"\bit is important to note that\b", "important:"),
    (r"\bit is worth mentioning that\b", "also:"),
    (r"\bit would be advisable to\b", "you should"),
    (r"\bone might consider\b", "consider"),
    (r"\bin order to\b", "to"),
    (r"\bat this point in time\b", "now"),
    (r"\bdue to the fact that\b", "because"),
    (r"\bfor the purpose of\b", "to"),
    (r"\bwith regard to\b", "about"),
    (r"\bwith respect to\b", "about"),
    (r"\bprior to\b", "before"),
    (r"\bsubsequent to\b", "after"),
    (r"\butilize\b", "use"),
    (r"\bfacilitate\b", "help"),
    (r"\binitiate\b", "start"),
    (r"\bcommence\b", "start"),
    (r"\bterminate\b", "end"),
    (r"\bprovide assistance\b", "help"),
    (r"\bprovide support\b", "support"),

    # GOJ-specific clarity
    (r"\bmember(?:s)? of the program\b", "participants"),
    (r"\bindividual(?:s)? receiving services\b", "participants"),
]


def _strip_opening_fillers(text: str) -> str:
    """Remove AI opener phrases from the beginning of the response.

    Two-pass strategy:
    1. Strip standalone single-word/short openers (Certainly!, Sure!, etc.)
       that are followed immediately by more content.
    2. Strip full filler sentences from the opener list.
    """
    # Pass 1: Remove pure standalone openers (single word + punctuation only)
    standalone_pattern = r'^(?:Certainly|Of course|Absolutely|Sure|Great|Wonderful|Fantastic|Noted)[,!\.]+\s+'
    text = re.sub(standalone_pattern, '', text, count=1, flags=re.IGNORECASE).lstrip()
    if text and text[0].islower():
        text = text[0].upper() + text[1:]

    # Pass 2: Remove full filler SENTENCES at the start.
    # A filler sentence is one that matches an opener pattern AND ends with . or !
    # We only strip if the whole sentence is the filler (no real content mixed in).
    sentence_openers = [
        r"^(That'?s? a great question[.!]+)\s+",
        r"^(Excellent question[.!]+)\s+",
        r"^(Great question[.!]+)\s+",
        r"^(I'?d be (?:happy|glad|delighted) to help(?:\s+you)?[.!]+)\s+",
        r"^(I'?m happy to help(?:\s+you)?[.!]+)\s+",
        r"^(Happy to help(?:\s+you)?[.!]+)\s+",
        r"^(As an AI (?:language model|assistant)[,.]? I (?:can|will|want to) (?:help|assist)[^.!]*[.!]+)\s+",
        r"^(As an AI[,.]? [^.!]{0,60}[.!]+)\s+",
        r"^(I understand[.!]+)\s+",
        r"^(I see[.!]+)\s+",
        r"^(Thank you for (?:asking|reaching out|your message)[.!]+)\s+",
        r"^(Thanks for (?:asking|reaching out|your message)[.!]+)\s+",
        r"^(Hello(?:,? (?:there|Kato))?[.!]+)\s+",
        r"^(Hi(?:,? (?:there|Kato))?[.!]+)\s+",
    ]
    for pattern in sentence_openers:
        new_text = re.sub(pattern, '', text, count=1, flags=re.IGNORECASE)
        if new_text != text:
            text = new_text.lstrip()
            if text and text[0].islower():
                text = text[0].upper() + text[1:]
            break  # Only strip one full sentence

    return text


def _strip_inline_fillers(text: str) -> str:
    """Remove AI filler phrases from inside the response."""
    for pattern, replacement in _INLINE_FILLERS:
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
    # Clean up double spaces and blank lines created by removal
    text = re.sub(r'  +', ' ', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def _apply_tone(text: str) -> str:
    """Apply tone replacements for active, direct language."""
    for pattern, replacement in _TONE_REPLACEMENTS:
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
    return text


def _control_verbosity(text: str, mode: str = "default") -> str:
    """
    Trim response if it exceeds length target for mode.
    mode: "default" | "brief" | "report"
    """
    limits = {
        "default": _MAX_CHARS_DEFAULT,
        "brief":   _MAX_CHARS_BRIEF,
        "report":  _MAX_CHARS_REPORT,
    }
    limit = limits.get(mode, _MAX_CHARS_DEFAULT)

    if len(text) <= limit:
        return text

    # Trim at a sentence boundary near the limit
    trimmed = text[:limit]
    # Find last sentence end
    last_end = max(
        trimmed.rfind('. '),
        trimmed.rfind('.\n'),
        trimmed.rfind('! '),
        trimmed.rfind('? '),
    )
    if last_end > limit * 0.6:
        trimmed = trimmed[:last_end + 1]
    else:
        # No good sentence break — just cut and add ellipsis
        trimmed = trimmed.rstrip() + "…"

    logger.debug(f"[humanize] Trimmed response from {len(text)} → {len(trimmed)} chars")
    return trimmed


def _fix_trailing_whitespace(text: str) -> str:
    """Clean up trailing whitespace and normalize line endings."""
    lines = text.splitlines()
    lines = [l.rstrip() for l in lines]
    # Remove trailing blank lines
    while lines and not lines[-1]:
        lines.pop()
    return "\n".join(lines)


def _detect_response_mode(text: str, context: str = "goj") -> str:
    """
    Detect if this is a brief, default, or report response.
    Used to pick verbosity limit.
    """
    text_lower = text.lower()
    report_signals = [
        "here is a summary", "here's a summary", "build status",
        "the following", "overview:", "report:", "breakdown:",
        "---", "===", "components:"
    ]
    brief_signals = [
        "yes", "no", "done", "ok", "noted", "got it",
        "confirmed", "sure", "will do"
    ]

    if any(s in text_lower for s in report_signals) or text.count('\n') > 8:
        return "report"
    if len(text) < 120 or any(text_lower.strip().startswith(s) for s in brief_signals):
        return "brief"
    return "default"


def humanize(
    text: str,
    context: str = "goj",
    force_mode: Optional[str] = None,
    skip_verbosity: bool = False,
) -> str:
    """
    Main entry point. Run a raw LLM response through all behavior filters.

    Args:
        text:           Raw response text from LLM
        context:        "goj" (default) — may add context-specific rules later
        force_mode:     Override verbosity mode ("brief" | "default" | "report")
        skip_verbosity: If True, skip length trimming (use for reports)

    Returns:
        Cleaned, humanized response string
    """
    if not text or not text.strip():
        return text

    original_len = len(text)

    # Step 1: Strip opening filler
    text = _strip_opening_fillers(text)

    # Step 2: Strip inline filler
    text = _strip_inline_fillers(text)

    # Step 3: Apply tone corrections
    text = _apply_tone(text)

    # Step 4: Control verbosity
    if not skip_verbosity:
        mode = force_mode or _detect_response_mode(text, context)
        text = _control_verbosity(text, mode)

    # Step 5: Final cleanup
    text = _fix_trailing_whitespace(text)

    # Step 6: Ensure response starts with a capital letter
    if text and text[0].islower():
        text = text[0].upper() + text[1:]

    if len(text) != original_len:
        logger.debug(f"[humanize] {original_len} → {len(text)} chars, mode={force_mode or 'auto'}")

    return text


# ─────────────────────────────────────────────
# Quick self-test
# ─────────────────────────────────────────────

if __name__ == "__main__":
    samples = [
        "Certainly! That's a great question. I'd be happy to help you with the menu for today. The participants will be having chicken and rice.",
        "Of course! As an AI language model, I can tell you that the attendance for Monday was 14 participants.",
        "Sure! Let me go ahead and provide you with a summary of today's build status. The following components are currently building:\n- Build Coordinator: 30%\n- Workflow Audit Layer: 40%\nIs there anything else I can help you with?",
        "Great! I understand. Due to the fact that Mrs. Johnson was absent, you should notify her family prior to the end of day. Please don't hesitate to ask if you need anything else.",
        "Yes, that's confirmed.",
    ]

    print("=" * 60)
    print("HUMANIZE SELF-TEST")
    print("=" * 60)
    for i, sample in enumerate(samples, 1):
        result = humanize(sample)
        print(f"\n[Sample {i}]")
        print(f"  BEFORE: {sample[:100]}...")
        print(f"  AFTER:  {result[:100]}...")
    print("\n✓ All samples processed.")
