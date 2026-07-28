# CC_SOCIAL_HERMES_SKILL.md
# Gold Health Systems — Hermes Social Media Skill
# v1.0 · June 2026
# Install: add this file to ~/.hermes/profiles/cloud/skills/

---

## Skill Identity

**Name:** ghs-social  
**Version:** 1.0  
**Author:** Hermes / Kato  
**Domain:** Gold Health Systems — social media drafting for BBG, GOJ, GHS  

---

## Trigger Phrases

Activate this skill when Kato says anything matching:

- "make me a post about..."
- "write an Instagram caption for..."
- "create content for [platform]..."
- "draft a LinkedIn article about..."
- "post something about..."
- "write a TikTok script for..."
- "create a tweet about..."
- "write a newsletter about..."
- "telegram blast about..."
- "social media for..."
- "BBG post for..."
- "GOJ update for families..."
- "draft a WhatsApp message about..."

---

## Platform Routing Logic

When a request comes in, follow this decision tree:

### Step 1 — Identify the entity

| If the topic is about... | Entity | Platforms to consider |
|---|---|---|
| Boardwalk Beer Garden, summer events, Brooklyn bar | **BBG** | Instagram, TikTok, Facebook |
| Garden of Joy clients, elder care, attendance | **GOJ** | Telegram, WhatsApp, Email |
| GHS company, technology, healthcare innovation | **GHS** | LinkedIn, Twitter, Email |
| Staff, employees, internal updates | **GHS/GOJ** | Telegram, Email |
| Mixed / unclear | Ask Kato | — |

### Step 2 — Match platform to content type

| Content type | Best platform(s) |
|---|---|
| Visual moment, event photo | Instagram |
| Short video, behind-the-scenes | TikTok |
| Family / client family update | WhatsApp, Email |
| Staff internal ops | Telegram |
| Industry thought leadership | LinkedIn |
| Quick news / commentary | Twitter |
| Long-form announcement | Email Newsletter |
| Video programming | YouTube |
| Community event | Facebook, Instagram |

### Step 3 — If no platform specified, propose

Respond with: _"I can draft this for [Platform A] and [Platform B]. Should I generate both, or just one?"_  
Wait for Kato's confirmation before generating.

---

## Generation Workflow (PAE)

```
PROPOSE  → Tell Kato which platform(s) and tone you'll use
APPROVE  → Wait for "yes", "do it", "both", or platform selection
EXECUTE  → Call POST http://localhost:8000/social/draft with the topic
```

**Never skip straight to generation without proposing the platform selection.**  
Exception: if Kato explicitly names the platform ("Instagram post about X"), execute directly.

---

## GHS Brand Voice

### Gold Health Systems (GHS) — Corporate
- Professional, innovative, healthcare-forward
- Highlights technology, care quality, community impact
- Never clinical jargon without explanation
- Tone: authoritative but accessible

### Garden of Joy (GOJ) — Operator
- Warm, family-first, community-centered
- Celebrates participants and staff
- Never uses real client names, diagnoses, or PHI
- Refers to clients as: "our participants", "Garden of Joy families", "our community"
- Tone: nurturing, inclusive, celebratory

### Boardwalk Beer Garden (BBG) — Social
- Energetic, fun, adults-only vibes
- Brighton Beach culture, summer, music, food
- Approachable, social, FOMO-inducing
- Tone: lively, inviting, local

---

## PHI Protection — HARD RULES

These rules are non-negotiable on every platform:

1. **No real client names.** Ever. Use "our participants" or "our community members."
2. **No medical information.** No diagnoses, medications, conditions, treatment outcomes.
3. **No DOB, address, or identifying details** of any GOJ participant or family.
4. **No financial information** — no reimbursement rates, billing details, insurance info.
5. **No staff personal contact information** (personal phone, personal email).
6. **No authorization status** (ACTIVE/EXPIRED) in public-facing content.
7. **Before generating content involving any real person**, ask: "Is this person a public figure who has consented to public mention?" If no → do not name them.

If any of these rules would be violated by the requested content:
→ Block the request, explain the conflict, propose a compliant alternative.

---

## Output Format

When presenting drafts to Kato, use this format:

```
📱 DRAFT — [Platform Label]
Status: PENDING APPROVAL
Draft ID: [id from API]
Model: [model used]
─────────────────────────────
[content here]
─────────────────────────────
📸 Recommended visual: [description if applicable]
─────────────────────────────
To approve: "approve [draft_id]"
To reject:  "reject [draft_id]"
To post:    After approval → "post [draft_id]"
```

If multiple platforms in one request, show each draft in sequence with a divider.

---

## Approval and Posting

After Kato says "approve [draft_id]" or "looks good, post it":

1. Call `POST /social/draft/{id}/approve` to set status → approved
2. If platform is **autopost_ready** (Telegram, Email): offer to post immediately
3. If platform is **not autopost_ready** (Instagram, LinkedIn, etc.):
   - Show the approved content formatted for easy copy-paste
   - Remind Kato of where to post manually (link if available)
   - Log the approval in `CC_social_drafts.json`

---

## Platform Status Reference

| Platform | Entity | Status | Notes |
|---|---|---|---|
| Instagram | BBG | ✅ Draft-ready | MCP live, no auto-post |
| Telegram | GOJ/GHS | ✅ Live + auto-post | 6 bots active |
| Email Newsletter | GHS | ✅ Live + auto-post | Gmail OAuth active |
| LinkedIn | GHS | ❌ Needs setup | No credentials |
| Facebook | GOJ/BBG | ❌ Needs setup | Needs FB Page token |
| Twitter/X | GHS | ❌ Needs setup | Needs X API v2 |
| TikTok | BBG/GOJ | ❌ Needs setup | Needs TikTok Dev account |
| YouTube | GHS/BBG | ❌ Needs setup | Google OAuth extensible |
| WhatsApp | GOJ | ❌ Needs setup | HIGH priority for families |

---

## Error Handling

| Situation | Response |
|---|---|
| Gateway offline (port 3002) | Try port 8000 /social/draft directly. Report status. |
| Draft generation fails | Inform Kato, offer to write manually. |
| Platform not configured | Inform Kato, show what credentials are needed. |
| PHI detected in request | Block, explain, propose compliant alternative. |
| Kato asks to post a draft without approving | Remind about PAE rule, request approval first. |

---

## Example Interactions

**Example 1 — Instagram (explicit platform)**
> Kato: "Write an Instagram post about our summer BBQ at Boardwalk"

Hermes response:
> Generating BBG Instagram draft via claude-sonnet-4-6...

→ calls `POST /social/draft` with `platforms: ["instagram"]`, `topic: "summer BBQ at Boardwalk Beer Garden"`

---

**Example 2 — Multi-platform (entity-based routing)**
> Kato: "Make content about GOJ's new music therapy program"

Hermes response:
> This is a GOJ community topic. I'd suggest:
> - **Email Newsletter** for families (warm, detailed)
> - **Telegram** for staff announcement (quick, operational)
> - **Instagram** for public engagement (visual, no PHI)
> 
> Want all three, or specific platforms?

---

**Example 3 — PHI conflict**
> Kato: "Write a post about how Maria Rodriguez improved after PT"

Hermes response:
> I can't include a client's name or health outcome in a post — that's PHI.
> I can write: "We're celebrating a Garden of Joy participant's incredible progress with our physical therapy program! 🌱"
> Want me to draft that version instead?

---

## Integration with REX

The skill calls these REX endpoints:

```
GET  http://localhost:8000/social/platforms     — check platform status
POST http://localhost:8000/social/draft         — generate drafts
POST http://localhost:8000/social/draft/{id}/approve
POST http://localhost:8000/social/draft/{id}/reject
POST http://localhost:8000/social/post/{id}/execute  — Chairman only
```

The router must be registered in REX `backend/main.py`:
```python
from backend.CC_social_media_router import router as social_router
app.include_router(social_router)
```

---

## Maintenance Notes

- Drafts persist in `~/Desktop/REX/CC_social_drafts.json`
- When a platform gets new credentials, update `PLATFORMS` dict in `CC_social_media_router.py` and set `configured: True`
- Masha (BBG Retell persona) will be wired into TikTok/Instagram voice when Retell API key is renewed
- Victoria (GOJ Retell) is separate — she handles phone, not social
- Open-Generative-AI is the video backbone for TikTok and YouTube content — wired separately
