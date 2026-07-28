# Rexxie Growth Loop — Full Integration Patch
## The Complete Intelligence Architecture

This patch wires the full learning loop into `rex_rexxie_telegram_bot.py`.
After this, every conversation makes Rexxie smarter about **this specific person**.

---

## THE LOOP (9 steps, every message)

```
1. User sends message
2. Signal detected  →  did previous response land well?
3. Memory retrieved →  what's relevant from the past?
4. User model built →  who is this person right now?
5. Policy checked   →  is this safe to process?
6. Plan made        →  how should Rexxie respond?
7. Rexxie responds
8. Exchange logged  →  record what just happened
9. User model updated, reflection triggered periodically
```

---

## STEP 1 — New imports (add after existing imports)

```python
# ── Growth loop imports ──────────────────────────────────────────
try:
    from rex_user_model import UserModel as _UserModel
    _USER_MODEL_AVAILABLE = True
except Exception as e:
    _USER_MODEL_AVAILABLE = False
    logger.warning(f"[rexxie] UserModel unavailable: {e}")

try:
    from rex_reflection import Reflection as _Reflection
    _REFLECTION_AVAILABLE = True
except Exception as e:
    _REFLECTION_AVAILABLE = False
    logger.warning(f"[rexxie] Reflection unavailable: {e}")
```

---

## STEP 2 — Initialize in __init__

Add at the END of `__init__`, after the planner initialization:

```python
        # ── User model ───────────────────────────────────────────────
        self._user_models: dict = {}   # chat_id → UserModel instance

        # ── Reflection engine ────────────────────────────────────────
        self._reflections: dict = {}   # chat_id → Reflection instance

        # ── Exchange counter (for triggering reflection periodically) ─
        self._exchange_counts: dict = {}   # chat_id → int
        self._REFLECT_EVERY = 20   # Run reflection every N messages
```

---

## STEP 3 — Add helper methods to the bot class

Add these two methods to the bot class:

```python
    def _get_user_model(self, chat_id: int):
        """Get or create a UserModel for this chat."""
        if not _USER_MODEL_AVAILABLE:
            return None
        if chat_id not in self._user_models:
            try:
                self._user_models[chat_id] = _UserModel(
                    db_path=self._db_path,
                    chat_id=chat_id,
                )
            except Exception as e:
                logger.warning(f"[rexxie] UserModel init failed for {chat_id}: {e}")
                return None
        return self._user_models.get(chat_id)

    def _get_reflection(self, chat_id: int):
        """Get or create a Reflection engine for this chat."""
        if not _REFLECTION_AVAILABLE:
            return None
        if chat_id not in self._reflections:
            try:
                um = self._get_user_model(chat_id)
                self._reflections[chat_id] = _Reflection(
                    db_path=self._db_path,
                    chat_id=chat_id,
                    user_model=um,
                )
            except Exception as e:
                logger.warning(f"[rexxie] Reflection init failed for {chat_id}: {e}")
                return None
        return self._reflections.get(chat_id)
```

---

## STEP 4 — Replace the full message handler pipeline

Find the section in `_handle_message` that runs after the slash command checks.
Replace everything from "detect memory" to "reply_text" with:

```python
        # ═══ GROWTH LOOP ═════════════════════════════════════════════

        # ── Step 1: Get this person's model and reflection engine ────
        um = self._get_user_model(chat_id)
        rf = self._get_reflection(chat_id)

        # ── Step 2: Signal detection (how did the last response land?) ─
        incoming_signal = "neutral"
        if rf is not None:
            incoming_signal = rf.process_incoming_signal(text)
            if incoming_signal in ("negative", "correction"):
                logger.info(
                    f"[rexxie] chat={chat_id} incoming signal: {incoming_signal}"
                )

        # ── Step 3: Policy check — INBOUND ───────────────────────────
        if _POLICY_ENFORCER is not None:
            _inbound_check = _POLICY_ENFORCER.check_inbound(text, chat_id=chat_id)
            if _inbound_check.blocked:
                await update.message.reply_text(_inbound_check.response)
                return
            _emergency_prefix = _POLICY_ENFORCER.get_emergency_prepend(_inbound_check)
        else:
            _emergency_prefix = ""

        # ── Step 4: Auto-extract user model signals ───────────────────
        if um is not None:
            um.extract_and_store(text, source="observed")

        # ── Step 5: Detect & save structured memory ───────────────────
        _detect_structured_memory(text)

        # ── Step 6: Retrieve prioritized memory ──────────────────────
        memories    = self._retrieve_relevant_memory(text, limit=4)
        mem_context = ""
        if _PRIORITY_MEMORY_AVAILABLE and memories:
            from rex_memory_priority import format_memory_context
            mem_context = format_memory_context(memories)
        elif memories:
            mem_context = "\n".join(
                f"[{m.get('idea_type','note').upper()}] {m.get('content','')[:200]}"
                for m in memories
            )

        # ── Step 7: Build person context from user model ─────────────
        person_context = ""
        if um is not None:
            person_context = um.build_context_block(max_items_per_category=2)

        # ── Step 8: Get reflection strategy hint ─────────────────────
        strategy_hint = ""
        if rf is not None and _PLANNER is not None:
            # Pre-classify to get intent for strategy lookup
            _pre_intent, _, _ = _PLANNER.classify(text)
            strategy_hint = rf.get_strategy_hint(_pre_intent.value) or ""

        # ── Step 9: Plan the request ─────────────────────────────────
        if _PLANNER is not None:
            # Combine all context
            full_context = "\n".join(filter(None, [
                person_context,
                mem_context,
                strategy_hint,
            ]))
            _plan = _PLANNER.plan(
                text,
                chat_id=chat_id,
                memory_context=full_context,
            )
            enriched_text          = _plan.user_message
            system_prompt_override = _plan.system_prompt

            # Adjust system prompt with support style
            if um is not None:
                support_style = um.get_support_style()
                if support_style == "brief":
                    system_prompt_override += (
                        "\n\nStyle: Keep responses SHORT — 1-2 sentences max. "
                        "This person prefers concise answers."
                    )
                elif support_style == "direct":
                    system_prompt_override += (
                        "\n\nStyle: Be DIRECT. Skip pleasantries. "
                        "Answer first, explain after if needed."
                    )
                elif support_style == "gentle":
                    system_prompt_override += (
                        "\n\nStyle: Be WARM and supportive. "
                        "Acknowledge feelings before offering solutions."
                    )
        else:
            enriched_text          = (mem_context + "\n" + text).strip()
            system_prompt_override = None
            _plan                  = None

        # ── Step 10: Load conversation history ───────────────────────
        history = self._chat_history.get(chat_id, [])

        # ── Step 11: Call Rexxie ─────────────────────────────────────
        raw_response = await self._call_rexxie(
            enriched_text,
            history=history,
            system_prompt=system_prompt_override,
        )

        # Save to history (original text, not enriched)
        _exchange = [
            {"role": "user",      "content": text},
            {"role": "assistant", "content": raw_response},
        ]
        self._chat_history[chat_id] = (history + _exchange)[-self._MAX_HISTORY:]

        # ── Step 12: Policy check — OUTBOUND ─────────────────────────
        if _POLICY_ENFORCER is not None:
            _outbound = _POLICY_ENFORCER.check_outbound(raw_response, text)
            if _outbound.blocked:
                final_response = _outbound.response
            else:
                final_response = _outbound.clean_text if _outbound.modified else raw_response
        else:
            final_response = raw_response

        # ── Step 13: Humanize ─────────────────────────────────────────
        if _HUMANIZE_AVAILABLE:
            final_response = _humanize(final_response)

        # ── Step 14: Emergency prefix ─────────────────────────────────
        if _emergency_prefix:
            final_response = _emergency_prefix + final_response

        # ── Step 15: Send ─────────────────────────────────────────────
        await update.message.reply_text(final_response)

        # ── Step 16: Log exchange for reflection ──────────────────────
        if rf is not None and _plan is not None:
            support_style = um.get_support_style() if um else "standard"
            rf.log_exchange(
                intent         = _plan.intent.value,
                user_message   = text,
                response       = final_response,
                response_style = support_style,
            )

        # ── Step 17: Periodic reflection ─────────────────────────────
        self._exchange_counts[chat_id] = self._exchange_counts.get(chat_id, 0) + 1
        if (
            rf is not None
            and self._exchange_counts[chat_id] % self._REFLECT_EVERY == 0
        ):
            try:
                insights = rf.reflect()
                if insights:
                    logger.info(
                        f"[rexxie] Reflection for chat={chat_id}: "
                        f"{len(insights)} new insights"
                    )
            except Exception as e:
                logger.warning(f"[rexxie] Reflection failed: {e}")

        # ═══ END GROWTH LOOP ══════════════════════════════════════════
```

---

## STEP 5 — Copy the 2 new files to ~/Desktop/REX/

```bash
cp ~/Desktop/Gold_Health_Systems/build_coordinator/rex_user_model.py ~/Desktop/REX/
cp ~/Desktop/Gold_Health_Systems/build_coordinator/rex_reflection.py ~/Desktop/REX/
```

---

## WHAT REXXIE NOW LEARNS (automatically, per person)

| Signal | What gets stored | Where |
|--------|-----------------|-------|
| "I prefer short replies" | Preference, Tier 3, conf=0.85 | rex_user_model |
| "I'm working on X" | Goal, Tier 2, conf=0.8 | rex_user_model |
| "Remember that Friday is crafts" | Trusted fact, Tier 3, conf=0.95 | rex_user_model |
| "I'm stressed today" | Emotional pattern, Tier 2, conf=0.65 | rex_user_model |
| User keeps saying "thanks" after brief replies | Style insight, Tier 4 | rex_reflection |
| User says "that's wrong" after long reply | Avoid-style signal | rex_reflection |
| Same memory accessed 3+ times | Promoted to Tier 3 | rex_user_model |

## WHAT REXXIE NEVER STORES

- PHI (name + diagnosis combinations) — blocked by policy enforcer
- Jailbreak attempts — blocked
- System architecture details — blocked
- Sensitive records — blocked
- Core identity or rules — immutable

## GROWTH BOUNDARIES

```
CAN change over time:
  ✅ Response length preference
  ✅ Tone/style per intent type
  ✅ Memory about user's projects and goals
  ✅ Emotional support patterns
  ✅ Communication preferences
  ✅ Trusted facts the user wants remembered

CANNOT change:
  ❌ Core identity and values
  ❌ Policy rules (requires editing rex_policy_rules.json manually)
  ❌ Safety boundaries
  ❌ Code or system architecture
  ❌ What it's allowed to disclose
```

---

## UPDATED MASTER LIST STATUS

After this patch, update master_list.json:

```json
{ "name": "Rex Memory Layer",       "stage_percent": 90, "stage_label": "Growth Loop Active" },
{ "name": "Rexxie Runtime",         "stage_percent": 85, "stage_label": "Person Model Active" },
{ "name": "Policy Enforcer",        "stage_percent": 90, "stage_label": "Full Pipeline" }
```
