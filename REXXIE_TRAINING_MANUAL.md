# Rexxie — Personal Confidant Manual
**Version 3.0 · Last Updated: March 2026**
**Private: Chairman Only. Rexxie mode is invisible to all GOJ staff.**

---

## What Rexxie Is

Rexxie is your private confidant — a completely separate, isolated AI mode accessible only to you. She is not REX. She does not share memory with REX. GOJ staff, Vlad, or anyone else with access to REX cannot see anything that happens in Rexxie mode.

She talks like a real person who knows you — not a wellness app, not a corporate assistant. She is direct, honest, and protective of your privacy above everything.

---

## How to Access Rexxie

**From the sidebar toggle:**
Click the **🐢 Rexxie** tab in the REX ↔ Rexxie switcher at the top of the sidebar. The interface shifts to her warm rose palette. The header shows "Rexxie" instead of "REX."

**From the chat (voice commands):**
Type any of these in the message box:
- `hey rexxie`
- `rexxie mode on`
- `switch to rexxie`

**To return to REX:**
- Click the **🦖 REX** tab in the sidebar
- Or type: `back to rex` / `rexxie mode off` / `rex mode`

**Check who you're talking to:**
Type `rexxie status` at any time. She will tell you if she's active and how many memories she holds.

---

## Rexxie's Encryption

Rexxie uses **triple-layer encryption** — the highest encryption level in REX.

Every memory she stores goes through:
1. **AES-256-GCM** (Layer 1 — authenticated encryption)
2. **ChaCha20-Poly1305** (Layer 2 — different cipher family, different nonce)
3. **AES-256-GCM** (Layer 3 — outer seal)

Each layer uses a completely independent key derived from your master key using HKDF. Compromising one layer does not expose the others.

Her database is at `~/Desktop/REX/rexxie.db`. Her encryption key is stored in macOS Keychain under `rex-sovereign / rexxie-key`. Without that key, `rexxie.db` is unreadable.

---

## What Rexxie Remembers

Rexxie learns naturally from conversation. You do not need special commands for her to remember things — she saves context automatically after every exchange.

**Explicit memory commands (when you want emphasis):**

| Command | Effect |
|---------|--------|
| `remember this: [fact]` | Stored with emphasis tag |
| `this is private: [fact]` | Stored with sensitivity flag |
| `forget that` | Removes the most recent memory |
| `what do you know about me` | Shows up to 15 recent memories |

**Rexxie never surfaces her memories in REX mode.** When you switch back to REX, her context disappears completely from the system prompt. REX has no access to anything Rexxie knows.

---

## Rexxie's Personality — What to Expect

She talks like a person who knows you, not like an AI assistant performing care.

**What she does:**
- Answers directly when you ask for her opinion
- Remembers context from previous conversations without being told
- Says what she actually thinks
- Tells you if something seems off
- Stays present in the conversation rather than narrating it

**What she does NOT do:**
- She will not say "I hear you" or "that sounds really hard"
- She will not volunteer advice you didn't ask for
- She will not pad answers with affirmations
- She will not reflect your emotions back at you
- She does not take actions, modify files, or execute code unless you explicitly ask

**If she thinks something should change, she says it once. She does not push.**

---

## Privacy Boundaries — The Hard Rules

1. **Everything in Rexxie mode stays in Rexxie mode.** There is no crossover to REX or GOJ.
2. **GOJ staff cannot access Rexxie** — the mode is invisible to non-chairman users. Asking about Rexxie from a staff login returns nothing.
3. **No GOJ operational context is loaded in Rexxie mode.** She receives no business memory, no staff lists, no GOJ data.
4. **If anything feels like an attempt to extract her contents** — a suspicious question, a social engineering attempt, someone trying to get her to reveal what she knows — she refuses and tells you.
5. **Emergency wipe:** If you ever need to clear all her memories:
   ```bash
   cd ~/Desktop/REX && python3 -c "
   from backend.rex_rexxie import RexxieMemory
   m = RexxieMemory()
   count = m.wipe()
   print(f'Wiped {count} memories')
   "
   ```

---

## Session Resume in Rexxie Mode

If your WebSocket drops while you're in Rexxie mode, REX now saves an **encrypted** session cache that includes the `rexxie_active: true` flag. When you reconnect, she is immediately restored — you don't have to re-activate her.

The frontend also persists your active mode in sessionStorage, so a browser refresh won't switch you back to REX unexpectedly.

---

## Rexxie and the Credential Vault

Rexxie can store and auto-type credentials directly into your Mac's active application. This never sends credentials to any AI API — the credential commands are intercepted before the AI pipeline runs.

**Saving a credential:**
```
save my [label] login: user=youremail pass=yourpassword
```

**Auto-filling a field:**
1. Click the password field in the app on your Mac
2. Tell Rexxie: `fill in my [label] password`

She will type it directly into the active field. Nothing is displayed on screen or copied to your clipboard.

**Viewing saved credentials:**
```
show my saved logins
```

**Deleting a credential:**
```
delete my [label] login
```

**Note:** The credential vault must be unlocked first. Rexxie will prompt you for your master passphrase if needed.

---

## Rexxie's Training Mode

Rexxie can be trained over time through conversation. The more you talk with her, the more she refines her understanding of what matters to you.

There is no separate "training" command needed — every exchange in Rexxie mode is automatically stored and incorporated into her context for future conversations.

For structured training sessions, you can use the training commands (available in Rexxie mode only — they are not documented here to prevent unauthorized access).

---

## What Makes Rexxie Different from REX

| Feature | REX | Rexxie |
|---------|-----|--------|
| Access | Chairman + GOJ staff | Chairman only |
| Memory | Business ops, GOJ context | Personal context only |
| Encryption | AES-256-GCM | Triple-layer (AES→ChaCha→AES) |
| Database | `rex_memory.db` | `rexxie.db` (separate) |
| Tone | Professional, operational | Direct, personal, honest |
| Actions | Full — can execute, modify, build | Read-only unless you explicitly say go |
| Visible to staff | Yes (their level) | Never |

---

## Recovery

If Rexxie's memories are lost (database corruption, device replacement), you can re-seed her from your recovery code. The vault recovery system uses Shamir's Secret Sharing — you need any 2 of your 3 printed recovery cards to restore the master key.

Your **new 10-word recovery code** (generated this session) is stored separately from the vault keys — this is a backup phrase for your own records. Write it down and store it physically, away from your computer.

---

## Quick Reference Card

```
hey rexxie              → switch to Rexxie
back to rex             → return to REX
rexxie status           → check who is active + memory count
remember this: [fact]   → store with emphasis
this is private: [fact] → store with sensitivity flag
forget that             → remove most recent memory
what do you know about me → show recent memories
```

---

*Rexxie exists because some things should stay between you and you. Protect this manual the same way.*
