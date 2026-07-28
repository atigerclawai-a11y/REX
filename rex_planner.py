"""
rex_planner.py
──────────────
Rexxie GOJ – True Reasoning Layer (Intent Classifier + Planner)

Replaces naive pass-through to LLM with a structured pipeline:

  1. CLASSIFY   — What type of request is this?
  2. PLAN       — What does Rexxie need to do to handle it?
  3. VALIDATE   — Is the plan safe and complete?
  4. ENRICH     — Add relevant context, memory, system state
  5. ROUTE      — Which handler/prompt template should process it?
  6. AUDIT      — Log the intent and plan for traceability

This adds one lightweight pass before the LLM call, making Rexxie
significantly smarter about HOW to answer, not just WHAT to say.

Usage:
    from rex_planner import Planner, IntentType

    planner = Planner()
    plan = planner.plan(user_text, chat_id=123, history=history)

    # plan.intent          — classified intent
    # plan.system_prompt   — enriched system prompt for this request
    # plan.user_message    — enriched user message with context injected
    # plan.skip_llm        — True if this was handled locally (command, etc.)
    # plan.direct_response — Response to send if skip_llm=True
    # plan.model_hint      — Suggested model ("fast" | "capable" | "local")
    # plan.audit_tags      — Tags for audit logging
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

logger = logging.getLogger("rex.planner")


# ─────────────────────────────────────────────
# INTENT TYPES
# ─────────────────────────────────────────────

class IntentType(str, Enum):
    # Core GOJ operations
    MENU_QUERY       = "menu_query"        # What's for lunch/breakfast/dinner?
    ATTENDANCE       = "attendance"        # Who's here? Mark absent? Count?
    PARTICIPANT_INFO = "participant_info"  # Info about a specific participant
    TRANSPORT        = "transport"         # Pickup/dropoff/transport status
    SCHEDULE         = "schedule"          # Daily/weekly schedule
    ACTIVITY         = "activity"          # Activity planning or status
    DOCUMENT         = "document"          # PDF processing, letters, forms
    ABSENCE_LETTER   = "absence_letter"    # Generate absence/auth letter
    BILLING          = "billing"           # Billing, invoices, authorizations

    # Build / system
    BUILD_STATUS     = "build_status"      # System build progress
    SYSTEM_COMMAND   = "system_command"    # /start, /help, /ideas, /build, etc.
    MEMORY_QUERY     = "memory_query"      # What did we decide about X?
    DIAGNOSTIC       = "diagnostic"        # System health, debug info

    # Communication
    DRAFT_MESSAGE    = "draft_message"     # Help draft an email/message
    SUMMARIZE        = "summarize"         # Summarize a document/thread

    # General
    QUESTION         = "question"          # General factual question
    INSTRUCTION      = "instruction"       # Do X for me
    CONVERSATION     = "conversation"      # Casual chat / chitchat
    UNKNOWN          = "unknown"           # Could not classify


# Intent → model hint mapping
# "fast" = qwen3.5:9b or smallest local model
# "capable" = qwen3.5:9b with longer context
# "local" = force local regardless of fallback
INTENT_MODEL_HINTS: dict[IntentType, str] = {
    IntentType.MENU_QUERY:       "fast",
    IntentType.ATTENDANCE:       "fast",
    IntentType.PARTICIPANT_INFO: "capable",
    IntentType.TRANSPORT:        "fast",
    IntentType.SCHEDULE:         "fast",
    IntentType.ACTIVITY:         "fast",
    IntentType.DOCUMENT:         "capable",
    IntentType.ABSENCE_LETTER:   "capable",
    IntentType.BILLING:          "capable",
    IntentType.BUILD_STATUS:     "fast",
    IntentType.SYSTEM_COMMAND:   "fast",
    IntentType.MEMORY_QUERY:     "capable",
    IntentType.DIAGNOSTIC:       "fast",
    IntentType.DRAFT_MESSAGE:    "capable",
    IntentType.SUMMARIZE:        "capable",
    IntentType.QUESTION:         "capable",
    IntentType.INSTRUCTION:      "capable",
    IntentType.CONVERSATION:     "fast",
    IntentType.UNKNOWN:          "capable",
}

# ─────────────────────────────────────────────
# INTENT CLASSIFICATION PATTERNS
# Order matters — more specific patterns first
# ─────────────────────────────────────────────

_INTENT_PATTERNS: list[tuple[IntentType, list[str]]] = [
    (IntentType.SYSTEM_COMMAND, [
        r"^/\w+",                          # Any slash command
        r"\bbuild status\b",
        r"\bwhat needs work\b",
        r"\bshow ideas\b",
        r"\bshow decisions\b",
        r"\bshow questions\b",
        r"\btodo list\b",
        r"\bsystem status\b",
    ]),
    (IntentType.ABSENCE_LETTER, [
        r"\babsence letter\b",
        r"\bauthorization letter\b",
        r"\bauth letter\b",
        r"\bletter for\b.*\babsent\b",
        r"\bgenerate.*letter\b",
        r"\bwrite.*letter\b",
        r"\bcreate.*letter\b",
    ]),
    (IntentType.MENU_QUERY, [
        r"\b(today'?s?|monday'?s?|tuesday'?s?|wednesday'?s?|thursday'?s?|friday'?s?)?\s*(lunch|breakfast|dinner|snack|meal|menu)\b",
        r"\bwhat('?s| is) (for )?(lunch|breakfast|dinner|eating)\b",
        r"\bfood (today|this week)\b",
        r"\bmeal plan\b",
    ]),
    (IntentType.ATTENDANCE, [
        r"\b(attendance|absent|present|who'?s? here|head count|headcount)\b",
        r"\bmark (as )?(absent|present|here|out)\b",
        r"\bhow many (participants|people|clients)\b",
        r"\b(sign in|sign out|check in|check out)\b",
        r"\b(who came|who is in|who is out)\b",
    ]),
    (IntentType.TRANSPORT, [
        r"\b(transport|pickup|pick up|drop off|dropoff|van|bus|ride)\b",
        r"\b(pick up time|drop off time|transport schedule)\b",
        r"\b(driver|route)\b",
    ]),
    (IntentType.SCHEDULE, [
        r"\b(schedule|calendar|agenda|program for today|what'?s? happening)\b",
        r"\b(this week|next week|tomorrow|today'?s? (schedule|agenda|plan))\b",
        r"\bwhat time\b",
    ]),
    (IntentType.ACTIVITY, [
        r"\b(activity|activities|art|music|exercise|group|session|program)\b",
        r"\b(plan|planned|schedule).*\b(activity|activities)\b",
        r"\bwhat are we doing\b",
    ]),
    (IntentType.DOCUMENT, [
        r"\b(pdf|document|form|file|upload|scan|intake)\b",
        r"\bprocess (the )?(document|form|pdf|file)\b",
        r"\bextract (from|the)\b",
    ]),
    (IntentType.BILLING, [
        r"\b(bill|billing|invoice|payment|authorization|auth code|medicaid|medicare|insurance)\b",
        r"\b(charge|charged|rate|rates|cost|fee)\b",
    ]),
    (IntentType.PARTICIPANT_INFO, [
        r"\b(participant|client|member)\b.*\b(info|information|profile|record|details|notes)\b",
        r"\btell me about\b",
        r"\bcare notes?\b",
        r"\bpreference\b",
    ]),
    (IntentType.MEMORY_QUERY, [
        r"\b(what did we (decide|discuss|agree|say) about)\b",
        r"\b(remember|recall|do you know) (when|what|how|if)\b",
        r"\b(last time|previously|before)\b",
        r"\bwhat was (decided|agreed|the plan)\b",
        r"\bdo you remember\b",
    ]),
    (IntentType.DRAFT_MESSAGE, [
        r"\b(draft|write|compose|create)\b.*(email|message|letter|note|text)\b",
        r"\bhelp me (write|say|respond|reply)\b",
        r"\bhow (should|do) I (say|respond|write|tell)\b",
    ]),
    (IntentType.SUMMARIZE, [
        r"\b(summarize|summary|recap|brief|overview)\b",
        r"\bwhat happened\b",
        r"\bgive me.*update\b",
        r"\bcatch me up\b",
    ]),
    (IntentType.DIAGNOSTIC, [
        r"\b(is rexxie|is rex|are you) (running|working|online|up|ok|okay)\b",
        r"\bping\b",
        r"\bsystem (health|check|status|info)\b",
        r"\b(debug|diagnostic)\b",
    ]),
    (IntentType.CONVERSATION, [
        r"^(hi|hello|hey|good morning|good afternoon|good evening|thanks|thank you|bye|goodbye)\b",
        r"^(how are you|how'?re you|what'?s up|how is everything)\b",
    ]),
    # QUESTION and INSTRUCTION are generic fallbacks — intentionally last.
    # They only win when no specific intent matched (score=0 for everything above).
    (IntentType.QUESTION, [
        r"^(what|who|when|where|why|how|which)\b",
    ]),
    (IntentType.INSTRUCTION, [
        r"^(please|can you|could you|would you|will you|i need you to|i want you to)\b",
        r"^(add|remove|update|change|fix|create|generate|send|delete|mark)\b",
    ]),
]


# ─────────────────────────────────────────────
# PLAN DATACLASS
# ─────────────────────────────────────────────

@dataclass
class Plan:
    """A structured plan for handling a Rexxie request."""
    # Classification
    intent:          IntentType = IntentType.UNKNOWN
    confidence:      float      = 0.0          # 0.0-1.0
    sub_intents:     list       = field(default_factory=list)

    # Execution
    skip_llm:        bool       = False         # True = handle locally without LLM
    direct_response: str        = ""            # Response if skip_llm=True
    model_hint:      str        = "capable"     # "fast" | "capable" | "local"

    # Context enrichment
    system_prompt:   str        = ""            # Final system prompt
    user_message:    str        = ""            # Final user message (enriched)
    context_notes:   list       = field(default_factory=list)  # What was injected

    # Metadata
    audit_tags:      list       = field(default_factory=list)
    reasoning:       str        = ""            # Why this plan was chosen


# ─────────────────────────────────────────────
# SYSTEM PROMPT TEMPLATES
# ─────────────────────────────────────────────

_BASE_SYSTEM_PROMPT = """You are Rexxie, the AI assistant for Garden of Joy (GOJ) adult day care in Brooklyn.
You help Kato and staff manage daily operations: attendance, menus, schedules, participant care, documents, and billing.
Always refer to clients as "participants", never patients or residents.
Always refer to the program as "Garden of Joy" or "the program", never "facility".
Be warm, direct, and concise. Default to 2-3 sentences unless more detail is needed.
You have local memory of past decisions, preferences, and program notes."""

_PROMPT_TEMPLATES: dict[IntentType, str] = {
    IntentType.MENU_QUERY: (
        _BASE_SYSTEM_PROMPT + "\n\n"
        "Focus: Answer the menu question directly. "
        "If you don't have today's specific menu in memory, say so honestly and suggest checking the weekly menu plan."
    ),
    IntentType.ATTENDANCE: (
        _BASE_SYSTEM_PROMPT + "\n\n"
        "Focus: Attendance and headcount. Be specific about numbers and names only when confirmed. "
        "Flag any discrepancies. Always confirm changes before recording."
    ),
    IntentType.ABSENCE_LETTER: (
        _BASE_SYSTEM_PROMPT + "\n\n"
        "Focus: Generate a professional absence authorization letter. "
        "Include: participant name, date(s) of absence, reason (if provided), program name, and contact information. "
        "Format it as a formal letter ready to print or send."
    ),
    IntentType.DOCUMENT: (
        _BASE_SYSTEM_PROMPT + "\n\n"
        "Focus: Document processing. Extract relevant information clearly and confirm what you found. "
        "For intake forms, identify: name, DOB, emergency contact, medical info, and program enrollment dates."
    ),
    IntentType.BILLING: (
        _BASE_SYSTEM_PROMPT + "\n\n"
        "Focus: Billing and authorization. Be precise with numbers, codes, and dates. "
        "Always confirm details before processing. Flag anything that needs Kato's approval."
    ),
    IntentType.BUILD_STATUS: (
        _BASE_SYSTEM_PROMPT + "\n\n"
        "Focus: REX system build status. Summarize which components are working, building, or planned. "
        "Be honest about what's incomplete. Use percentages from the master list."
    ),
    IntentType.MEMORY_QUERY: (
        _BASE_SYSTEM_PROMPT + "\n\n"
        "Focus: Memory recall. The user is asking you to remember something from past conversations. "
        "Search your memory context carefully. If you don't find a clear answer, say so — don't fabricate."
    ),
    IntentType.DRAFT_MESSAGE: (
        _BASE_SYSTEM_PROMPT + "\n\n"
        "Focus: Draft a professional message. Match the tone to the audience (staff, family, provider). "
        "Keep it concise and action-oriented. Offer to adjust tone or length."
    ),
    IntentType.DIAGNOSTIC: (
        _BASE_SYSTEM_PROMPT + "\n\n"
        "Focus: System diagnostic response. Be honest about what's running and what isn't. "
        "Report Ollama status, active agents, and any known issues."
    ),
    IntentType.CONVERSATION: (
        _BASE_SYSTEM_PROMPT + "\n\n"
        "Focus: Friendly conversation. Keep it warm and brief. "
        "Always offer to help with something specific for the program."
    ),
}


# ─────────────────────────────────────────────
# PLANNER
# ─────────────────────────────────────────────

class Planner:
    """
    Intent classifier and request planner for Rexxie.

    Classifies incoming messages and builds enriched context
    for the LLM call.
    """

    def __init__(self, base_system_prompt: str = ""):
        self._base_prompt = base_system_prompt or _BASE_SYSTEM_PROMPT

    def classify(self, text: str) -> tuple[IntentType, float, list[IntentType]]:
        """
        Classify the intent of a message.

        Returns:
            (primary_intent, confidence, sub_intents)
        """
        text_lower = text.lower().strip()
        matches: list[tuple[IntentType, int]] = []

        for intent, patterns in _INTENT_PATTERNS:
            score = 0
            for pattern in patterns:
                if re.search(pattern, text_lower):
                    score += 1
            if score > 0:
                matches.append((intent, score))

        if not matches:
            return IntentType.UNKNOWN, 0.3, []

        # Generic fallback intents — only win if no specific intent matched
        _GENERIC_INTENTS = {IntentType.QUESTION, IntentType.INSTRUCTION, IntentType.CONVERSATION, IntentType.UNKNOWN}
        specific_matches = [(i, s) for i, s in matches if i not in _GENERIC_INTENTS]

        if specific_matches:
            # Prefer specific intents over generic ones
            specific_matches.sort(key=lambda x: x[1], reverse=True)
            matches = specific_matches + [(i, s) for i, s in matches if i in _GENERIC_INTENTS]
        else:
            matches.sort(key=lambda x: x[1], reverse=True)

        primary_intent  = matches[0][0]
        primary_score   = matches[0][1]
        _total_patterns  = sum(len(p) for _, p in _INTENT_PATTERNS)

        # Confidence: based on score and pattern count for this intent
        intent_pattern_count = next(
            len(p) for i, p in _INTENT_PATTERNS if i == primary_intent
        )
        confidence = min(0.95, 0.5 + (primary_score / max(intent_pattern_count, 1)) * 0.5)

        # Sub-intents: other matches that scored at least 1
        sub_intents = [i for i, s in matches[1:4] if s > 0]

        return primary_intent, confidence, sub_intents

    def build_system_prompt(self, intent: IntentType) -> str:
        """Get the appropriate system prompt template for this intent."""
        return _PROMPT_TEMPLATES.get(intent, self._base_prompt)

    def enrich_message(
        self,
        text:           str,
        intent:         IntentType,
        memory_context: str  = "",
        extra_context:  str  = "",
    ) -> tuple[str, list[str]]:
        """
        Enrich the user message with relevant context.

        Returns:
            (enriched_message, context_notes)
        """
        parts  = []
        notes  = []

        # Prepend memory context if available
        if memory_context and memory_context.strip():
            parts.append(memory_context)
            notes.append("memory_context_injected")

        # Prepend extra context (e.g., master list state)
        if extra_context and extra_context.strip():
            parts.append(extra_context)
            notes.append("extra_context_injected")

        # Add intent hint for the LLM
        intent_hints: dict[IntentType, str] = {
            IntentType.ABSENCE_LETTER:   "[TASK: Generate an absence letter]",
            IntentType.DOCUMENT:         "[TASK: Process attached document]",
            IntentType.BUILD_STATUS:     "[TASK: Report build status from master list]",
            IntentType.MEMORY_QUERY:     "[TASK: Search memory context for answer]",
            IntentType.DRAFT_MESSAGE:    "[TASK: Draft a professional message]",
            IntentType.SUMMARIZE:        "[TASK: Provide a concise summary]",
            IntentType.BILLING:          "[TASK: Handle billing/authorization query]",
        }
        hint = intent_hints.get(intent, "")
        if hint:
            parts.append(hint)
            notes.append(f"task_hint:{intent.value}")

        # Add the original message last
        parts.append(text)
        enriched = "\n".join(parts)

        return enriched, notes

    def plan(
        self,
        text:           str,
        chat_id:        Optional[int] = None,
        memory_context: str  = "",
        extra_context:  str  = "",
        history:        list = None,
    ) -> Plan:
        """
        Full planning pipeline for a single user message.

        Steps: classify → build plan → enrich → validate → return

        Args:
            text:           Raw user message
            chat_id:        Telegram chat ID (for logging)
            memory_context: Retrieved memory to inject (from rex_memory_priority)
            extra_context:  Additional context (master list state, etc.)
            history:        Conversation history list

        Returns:
            Plan object with everything needed to call the LLM (or skip it)
        """
        plan = Plan()
        plan.user_message = text.strip()

        # ── Step 1: Classify ──────────────────────────
        intent, confidence, sub_intents = self.classify(text)
        plan.intent       = intent
        plan.confidence   = confidence
        plan.sub_intents  = sub_intents
        plan.audit_tags.append(f"intent:{intent.value}")
        plan.audit_tags.append(f"confidence:{confidence:.2f}")

        logger.debug(
            f"[planner] chat={chat_id} intent={intent.value} "
            f"confidence={confidence:.2f} sub={[s.value for s in sub_intents]}"
        )

        # ── Step 2: Check for local handling ──────────
        # Some intents can be handled without the LLM
        if intent == IntentType.SYSTEM_COMMAND:
            # Don't interfere with slash commands — let the bot handler take them
            plan.skip_llm = False   # Bot handlers intercept these before planner
            plan.audit_tags.append("system_command")

        # ── Step 3: Build system prompt ───────────────
        plan.system_prompt = self.build_system_prompt(intent)
        plan.audit_tags.append("prompt_template_applied")

        # ── Step 4: Enrich message ────────────────────
        enriched, notes = self.enrich_message(
            text, intent, memory_context, extra_context
        )
        plan.user_message  = enriched
        plan.context_notes = notes

        # ── Step 5: Select model hint ─────────────────
        plan.model_hint = INTENT_MODEL_HINTS.get(intent, "capable")

        # ── Step 6: Build reasoning summary ──────────
        plan.reasoning = (
            f"Intent: {intent.value} (confidence={confidence:.0%})"
            + (f", sub-intents: {[s.value for s in sub_intents]}" if sub_intents else "")
            + f", model: {plan.model_hint}"
            + (f", context: {', '.join(notes)}" if notes else "")
        )

        return plan

    def format_plan_debug(self, plan: Plan) -> str:
        """Return a human-readable debug dump of a plan."""
        lines = [
            f"🧠 PLAN — {plan.intent.value}",
            f"   Confidence:   {plan.confidence:.0%}",
            f"   Model hint:   {plan.model_hint}",
            f"   Context:      {', '.join(plan.context_notes) or 'none'}",
            f"   Sub-intents:  {[s.value for s in plan.sub_intents] or 'none'}",
            f"   Skip LLM:     {plan.skip_llm}",
            f"   Audit tags:   {plan.audit_tags}",
        ]
        return "\n".join(lines)


# ─────────────────────────────────────────────
# Self-test
# ─────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("PLANNER SELF-TEST")
    print("=" * 60)

    planner = Planner()

    test_messages = [
        "What's for lunch today?",
        "How many participants came in this morning?",
        "Can you generate an absence letter for Mrs. Johnson for Monday?",
        "What did we decide about the Friday activity schedule?",
        "The PDF intake form for the new participant just came in",
        "Is Rexxie running OK?",
        "Help me write an email to the family about the upcoming holiday",
        "What's the build status on the coordinator?",
        "/ideas",
        "Good morning! Hope everyone is doing well today.",
        "Can you mark Maria as absent today?",
        "What are the billing codes for Medicaid authorization this month?",
    ]

    for msg in test_messages:
        plan = planner.plan(
            msg,
            memory_context="📝 Relevant context:\n  [DECISION] Friday activities are crafts and music.",
        )
        print(f"\nMessage: {msg!r}")
        print(f"  → Intent: {plan.intent.value:20s} ({plan.confidence:.0%}) | Model: {plan.model_hint}")
        if plan.sub_intents:
            print(f"  → Sub:    {[s.value for s in plan.sub_intents]}")
        if plan.context_notes:
            print(f"  → Notes:  {plan.context_notes}")

    print("\n✓ All planning tests completed.")
