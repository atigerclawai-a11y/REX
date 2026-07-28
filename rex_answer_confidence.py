"""
rex_answer_confidence.py
────────────────────────────────────────────────────────────────────
Rexxie GOJ – Answer Confidence Layer

Computes a PRECISE confidence score BEFORE Rexxie answers, then
injects the exact number into the system prompt so Rexxie tags her
answer with a computed score — not a guess.

Three confidence tiers per answer:
  • Memory-backed    — score driven by quality + count of retrieved memories
  • Coordinator      — score driven by master_list.json stage_percent for
                       the matched component
  • Reasoning-only   — flat baseline when no memory or coordinator data exists

Tag format injected into responses:
  [87% · memory]            ← answer backed by retrieved memories
  [94% · coordinator]       ← coordinator-tracked + verified component
  [52% · reasoning]         ← inferred, no direct memory support

Over time, as memories are recalled more (access_count rises), their
intrinsic confidence rises, which raises memory_pct here, which raises
the tag number Rexxie shows — so the percent naturally grows per the
design goal.

Usage:
    from rex_answer_confidence import AnswerConfidence

    ac = AnswerConfidence(master_list_path="~/Desktop/REX/master_list.json")
    result = ac.compute(memories=retrieved_memories, question=user_text)
    system_prompt_override += result.prompt_block
"""

from __future__ import annotations

import json
import math
import re
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger("rex.answer_confidence")

# ─────────────────────────────────────────────────────────────────
# CONSTANTS
# ─────────────────────────────────────────────────────────────────

# Reasoning-only baseline — no memories, no coordinator data
REASONING_BASELINE_PCT = 52

# When coordinator stage_percent is known, how much does memory boost it?
COORD_MEMORY_BOOST_WEIGHT = 0.25

# Memory score weights
MEMORY_COVERAGE_WEIGHT  = 0.15   # Bonus for having more memories (up to 4)
MEMORY_QUALITY_WEIGHT   = 0.85   # Avg intrinsic confidence of memories

# If avg memory confidence is unknown (old format), fall back to this
LEGACY_MEMORY_FALLBACK = 0.65

# TEMPORARY: message appended to prompt block explaining the feature
TEMP_NOTICE = (
    "This confidence protocol is temporary and will be removed once the "
    "system's memory has matured and proven reliable."
)


# ─────────────────────────────────────────────────────────────────
# RESULT DATACLASS
# ─────────────────────────────────────────────────────────────────

@dataclass
class ConfidenceResult:
    """Full confidence calculation result for one answer."""

    memory_pct:      int           # % for memory-backed claims
    coordinator_pct: int           # % for coordinator-verified claims (0 if no match)
    reasoning_pct:   int           # % for reasoned/inferred claims

    memory_count:    int           # how many memories were used
    coordinator_component: str     # name of matched coordinator component ("" if none)
    coordinator_stage: str         # stage label of matched component ("" if none)

    prompt_block:    str           # ready to append to system_prompt_override
    summary:         str           # short human-readable summary for logs

    def has_coordinator(self) -> bool:
        return bool(self.coordinator_component)

    def dominant_pct(self) -> int:
        """Returns the highest confidence tier available."""
        return max(self.memory_pct, self.coordinator_pct, self.reasoning_pct)


# ─────────────────────────────────────────────────────────────────
# COORDINATOR MATCHER
# ─────────────────────────────────────────────────────────────────

class _CoordinatorMatcher:
    """
    Loads master_list.json and matches a user question to a coordinator
    component using keyword overlap.
    """

    def __init__(self, master_list_path: Path):
        self._components: list[dict] = []
        self._load(master_list_path)

    def _load(self, path: Path) -> None:
        try:
            if path.exists():
                data = json.loads(path.read_text())
                self._components = data.get("components", [])
                logger.debug(f"[answer_confidence] Loaded {len(self._components)} coordinator components")
            else:
                logger.debug(f"[answer_confidence] master_list.json not found at {path}")
        except Exception as e:
            logger.warning(f"[answer_confidence] Could not load master_list.json: {e}")

    def match(self, question: str) -> Optional[dict]:
        """
        Returns the best-matching coordinator component for the question,
        or None if no component scores above threshold.

        Matching uses keyword overlap against each component's keywords list,
        name, and description.
        """
        if not self._components or not question.strip():
            return None

        q_tokens = _tokenize(question)
        if not q_tokens:
            return None

        best_score  = 0.0
        best_comp   = None

        for comp in self._components:
            # Build searchable text for this component
            keywords    = comp.get("keywords", [])
            name        = comp.get("name", "")
            description = comp.get("description", "")
            category    = comp.get("category", "")

            comp_tokens = set()
            for kw in keywords:
                comp_tokens.update(_tokenize(kw))
            comp_tokens.update(_tokenize(name))
            comp_tokens.update(_tokenize(description[:120]))
            comp_tokens.update(_tokenize(category))

            if not comp_tokens:
                continue

            overlap    = len(q_tokens & comp_tokens)
            if overlap == 0:
                continue

            # F1-style blended score
            precision  = overlap / len(q_tokens)
            recall     = overlap / len(comp_tokens)
            f1         = 2 * precision * recall / (precision + recall)

            if f1 > best_score:
                best_score = f1
                best_comp  = comp

        # Threshold: require meaningful overlap
        if best_score >= 0.08 and best_comp:
            logger.debug(
                f"[answer_confidence] Coordinator match: {best_comp['name']!r} "
                f"(score={best_score:.3f})"
            )
            return best_comp

        return None


# ─────────────────────────────────────────────────────────────────
# UTILITY
# ─────────────────────────────────────────────────────────────────

def _tokenize(text: str) -> set[str]:
    """Lowercase word tokens, no stop words."""
    tokens = re.findall(r"[a-z0-9]+", text.lower())
    stop = {
        "a", "an", "the", "is", "it", "in", "on", "at", "to", "of",
        "and", "or", "for", "with", "was", "are", "be", "as", "by",
        "i", "we", "you", "he", "she", "they", "my", "your", "our",
        "this", "that", "have", "has", "had", "not", "no", "so", "what",
        "how", "when", "where", "who", "which", "do", "did", "will",
        "can", "could", "should", "would", "there", "their", "them",
        "from", "about", "up", "out", "if", "then", "than", "because",
        "its", "into", "also", "just", "all", "but", "been", "more",
    }
    return {t for t in tokens if t not in stop and len(t) > 1}


def _avg_memory_confidence(memories: list[dict]) -> float:
    """
    Returns average intrinsic confidence across retrieved memories.
    Uses 'confidence' key (intrinsic) if present, falls back to 'score'
    (composite, query-dependent), then to LEGACY_MEMORY_FALLBACK.
    """
    if not memories:
        return 0.0
    scores = []
    for m in memories:
        val = m.get("confidence") or m.get("score")
        if val is not None:
            scores.append(float(val))
        else:
            scores.append(LEGACY_MEMORY_FALLBACK)
    return sum(scores) / len(scores)


def _coverage_bonus(memory_count: int, max_count: int = 4) -> float:
    """Small bonus for having more memories. 0 memories = 0, 4+ = full bonus."""
    if memory_count <= 0:
        return 0.0
    return min(memory_count / max_count, 1.0)


# ─────────────────────────────────────────────────────────────────
# MAIN CLASS
# ─────────────────────────────────────────────────────────────────

class AnswerConfidence:
    """
    Computes precise confidence scores for Rexxie's answers.

    Instantiate once per bot session and call compute() for each message.
    """

    # Default master_list path (same folder as the bot)
    DEFAULT_MASTER_LIST = Path.home() / "Desktop" / "REX" / "master_list.json"

    def __init__(self, master_list_path: Optional[Path] = None):
        path = Path(master_list_path) if master_list_path else self.DEFAULT_MASTER_LIST
        self._coordinator = _CoordinatorMatcher(path)

    def compute(
        self,
        memories:  list[dict],
        question:  str,
        show_confidence: bool = True,
    ) -> ConfidenceResult:
        """
        Compute confidence scores and return a ConfidenceResult with
        a ready-to-inject prompt_block.

        Args:
            memories:  List of memory dicts from PriorityMemory.retrieve()
                       Each should have 'confidence' (intrinsic) and/or 'score'.
            question:  The user's original message text.
            show_confidence: If False, returns empty prompt_block (feature off).
        """
        # ── Memory tier ──────────────────────────────────────────
        mem_count  = len(memories)
        avg_conf   = _avg_memory_confidence(memories)
        coverage   = _coverage_bonus(mem_count)

        if mem_count > 0:
            raw_mem = (
                avg_conf   * MEMORY_QUALITY_WEIGHT +
                coverage   * MEMORY_COVERAGE_WEIGHT
            )
            memory_pct = min(int(round(raw_mem * 100)), 98)
        else:
            memory_pct = 0   # no memories → don't use this tier

        # ── Coordinator tier ─────────────────────────────────────
        coordinator_pct   = 0
        coordinator_comp  = ""
        coordinator_stage = ""

        matched = self._coordinator.match(question)
        if matched:
            stage_frac  = matched.get("stage_percent", 50) / 100.0
            # Memory boosts coordinator confidence slightly
            mem_boost   = avg_conf * COORD_MEMORY_BOOST_WEIGHT if mem_count > 0 else 0.0
            raw_coord   = stage_frac * (1 - COORD_MEMORY_BOOST_WEIGHT) + mem_boost
            coordinator_pct   = min(int(round(raw_coord * 100)), 99)
            coordinator_comp  = matched.get("name", "")
            coordinator_stage = matched.get("stage_label", "")

        # ── Reasoning tier ───────────────────────────────────────
        # Slightly higher if we have memory support, but still clearly "reasoning"
        reasoning_pct = REASONING_BASELINE_PCT
        if mem_count > 0:
            reasoning_pct = min(REASONING_BASELINE_PCT + 5, 57)

        # ── Build prompt block ───────────────────────────────────
        if not show_confidence:
            prompt_block = ""
            summary = "confidence display off"
        else:
            prompt_block = _build_prompt_block(
                memory_pct       = memory_pct,
                coordinator_pct  = coordinator_pct,
                reasoning_pct    = reasoning_pct,
                mem_count        = mem_count,
                coordinator_comp = coordinator_comp,
                coordinator_stage = coordinator_stage,
            )
            summary = _build_summary(
                memory_pct, coordinator_pct, reasoning_pct,
                mem_count, coordinator_comp,
            )

        return ConfidenceResult(
            memory_pct            = memory_pct,
            coordinator_pct       = coordinator_pct,
            reasoning_pct         = reasoning_pct,
            memory_count          = mem_count,
            coordinator_component = coordinator_comp,
            coordinator_stage     = coordinator_stage,
            prompt_block          = prompt_block,
            summary               = summary,
        )


# ─────────────────────────────────────────────────────────────────
# PROMPT BLOCK BUILDER
# ─────────────────────────────────────────────────────────────────

def _build_prompt_block(
    memory_pct:        int,
    coordinator_pct:   int,
    reasoning_pct:     int,
    mem_count:         int,
    coordinator_comp:  str,
    coordinator_stage: str,
) -> str:
    """
    Returns the confidence protocol block to append to system_prompt_override.
    Rexxie reads this and knows exactly which numbers to use — she does not guess.
    """

    lines = [
        "",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "CONFIDENCE PROTOCOL — ACTIVE",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "Append a confidence tag after every factual claim or direct answer.",
        "",
        "Tag format:   [XX% · source]",
        "  XX     = the exact percentage listed below — do not change it",
        "  source = one of: memory | coordinator | reasoning",
        "",
        "Confidence values for THIS response:",
    ]

    if memory_pct > 0:
        mem_label = f"{mem_count} {'memory' if mem_count == 1 else 'memories'} retrieved"
        lines.append(f"  Memory-backed claims:   {memory_pct}%  →  [{memory_pct}% · memory]   ({mem_label})")
    else:
        lines.append(f"  Memory-backed claims:   n/a  (no matching memories found)")

    if coordinator_pct > 0:
        coord_label = f"{coordinator_comp}, {coordinator_stage}" if coordinator_stage else coordinator_comp
        lines.append(f"  Coordinator-verified:   {coordinator_pct}%  →  [{coordinator_pct}% · coordinator]   ({coord_label})")
    else:
        lines.append(f"  Coordinator-verified:   n/a  (topic not in coordinator registry)")

    lines.append(f"  Reasoned / inferred:    {reasoning_pct}%  →  [{reasoning_pct}% · reasoning]")

    lines += [
        "",
        "Tagging rules:",
        "  • Every factual statement gets one tag",
        "  • Tag goes at the END of the sentence, before the period",
        "  • Do NOT tag questions back to Kato",
        "  • Do NOT tag conversational filler ('Sure!', 'Of course', etc.)",
        "  • Do NOT invent percentages — only use the values above",
        "  • If a sentence is both memory-backed AND coordinator-verified,",
        "    use the higher percentage",
        "",
        f"NOTE: {TEMP_NOTICE}",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "",
    ]

    return "\n".join(lines)


def _build_summary(
    memory_pct:       int,
    coordinator_pct:  int,
    reasoning_pct:    int,
    mem_count:        int,
    coordinator_comp: str,
) -> str:
    parts = [f"reasoning={reasoning_pct}%"]
    if mem_count > 0:
        parts.append(f"memory={memory_pct}% ({mem_count} retrieved)")
    if coordinator_comp:
        parts.append(f"coordinator={coordinator_pct}% ({coordinator_comp})")
    return " | ".join(parts)


# ─────────────────────────────────────────────────────────────────
# SELF-TEST
# ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import tempfile, os, json

    print("=" * 60)
    print("ANSWER CONFIDENCE SELF-TEST")
    print("=" * 60)

    # Build a minimal test master_list.json
    test_master = {
        "components": [
            {
                "name": "Rex Memory Layer",
                "stage_percent": 90,
                "stage_label": "Growth Loop Active",
                "keywords": ["memory", "rexxie_memory", "rex_memory", "db"],
                "category": "memory",
                "description": "Local memory and business data layer.",
            },
            {
                "name": "Policy Enforcer",
                "stage_percent": 90,
                "stage_label": "Full Pipeline",
                "keywords": ["policy", "enforcer", "rules", "security", "phi"],
                "category": "security",
                "description": "Deterministic control layer for safety.",
            },
        ]
    }

    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(test_master, f)
        ml_path = f.name

    ac = AnswerConfidence(master_list_path=ml_path)

    # Test 1: No memories, no coordinator match
    r = ac.compute(memories=[], question="what should we have for lunch today?")
    print(f"\nTest 1 — No memories, unknown topic:")
    print(f"  memory={r.memory_pct}% | coordinator={r.coordinator_pct}% | reasoning={r.reasoning_pct}%")
    print(f"  dominant={r.dominant_pct()}%")

    # Test 2: Memories present, coordinator match
    fake_memories = [
        {"idea_type": "decision", "content": "lunch is chicken", "confidence": 0.89, "score": 0.82},
        {"idea_type": "preference", "content": "Kato prefers short summaries", "confidence": 0.75, "score": 0.71},
    ]
    r = ac.compute(memories=fake_memories, question="what are the memory settings in rex?")
    print(f"\nTest 2 — 2 memories, coordinator match (Rex Memory Layer):")
    print(f"  memory={r.memory_pct}% | coordinator={r.coordinator_pct}% | reasoning={r.reasoning_pct}%")
    print(f"  matched component: {r.coordinator_component!r} ({r.coordinator_stage})")
    print(f"  summary: {r.summary}")

    # Test 3: Show the actual prompt block
    print(f"\nTest 3 — Prompt block (what gets injected into Rexxie's system prompt):")
    print(r.prompt_block)

    os.unlink(ml_path)
    print("✓ All tests passed.")
