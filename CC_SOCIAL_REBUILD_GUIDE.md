# CC_SOCIAL_REBUILD_GUIDE.md
# Gold Health Systems — Social Media System Rebuild
# v1.0 · June 4, 2026

---

## What This Document Is

This is the output of a full social media audit conducted June 4, 2026. It maps every social media channel, bot, and service in the GHS ecosystem, documents their current status, and provides a step-by-step activation guide for the new Hermes Social Media Router.

---

## AUDIT FINDINGS

### What Was Found

The audit scanned:
- `~/Desktop/REX/` — REX FastAPI backend
- `~/.hermes-cloud/` — BBG social pipeline + Hermes MCP servers
- `~/Documents/` — GOJ working files
- Hermes config backups in `~/Desktop/REX/CC_june4_backup_20260604_174528/`

**Key discovery:** The "9 social channels" are distributed across 3 layers:
1. Hermes MCP servers (what Hermes can talk to)
2. Active bots/personas (Masha, Victoria, Telegram bots)
3. Aspirational platforms (configured in code, no live credentials)

---

## PLATFORM-BY-PLATFORM AUDIT

### 1. Instagram — @boardwalkbeergarden
**Status: ✅ MCP Configured · ⚠️ No Auto-posting**

- Account: @boardwalkbeergarden (account ID: `27923669980556036`)
- Entity: BBG (Boardwalk Beer Garden, Brighton Beach)
- MCP server: `~/.hermes-cloud/mcp-servers/instagram_mcp.py`
- Credential: `META_IG_ACCESS_TOKEN` (in Hermes env)
- What works: Hermes can read Instagram via MCP, draft captions
- What doesn't: No auto-posting workflow. No n8n workflow wired.
- Gap: Token may need refresh. No auto-post n8n workflow exists.

**To activate auto-posting:**
1. Verify `META_IG_ACCESS_TOKEN` is valid: `curl -s "https://graph.facebook.com/v19.0/me?access_token=$META_IG_ACCESS_TOKEN"`
2. Create n8n workflow: Webhook → HTTP Request → Instagram Graph API POST
3. Wire n8n webhook URL into `CC_social_media_router.py` (`PLATFORMS["instagram"]["autopost_ready"] = True`)

---

### 2. Telegram — 6 Active Bots
**Status: ✅ Live · ✅ Auto-posting Ready**

Active bots:
| Bot | Handle | Purpose |
|-----|---------|---------|
| Hermes | @Hermes_Cloud_May_bot | Main AI interface |
| Rexxie | @goldhealth_rexxie_bot | Kato private (never expose) |
| Hermie | @HermieChatt_bot | Local Hermie interface |
| GOJ Ops | @RexOfGold_bot | GOJ operations |
| Billing | @GOJReceipts_bot | GOJ billing |
| Attendance | @GojAttendance_bot | GOJ attendance |

- MCP server: `~/.hermes-cloud/mcp-servers/telegram_mcp.py`
- Credential: `TELEGRAM_BOT_TOKEN` (in Hermes env)
- Status: Fully operational. Auto-posting ready.

**This is the most operational social channel in the stack.**

---

### 3. Email Newsletter — Gmail OAuth
**Status: ✅ Live · ✅ Auto-send via rex_gmail.py**

- Account: atigerclawai@gmail.com
- OAuth token: `~/.rex_google_token.json` (symlinked from `~/.hermes/shared/google_token.json`)
- Module: `~/Desktop/REX/backend/rex_gmail.py`
- Status: Fully operational. Can send, read, search, label emails.
- Gap: No newsletter template. No mailing list management.

**Newsletter activation:**
1. Draft content via social router
2. Use `rex_gmail.py` to send via Gmail API
3. For broadcast to family list: compile contact list → batch send

---

### 4. LinkedIn — NOT CONFIGURED
**Status: ❌ No credentials · Priority 2**

- Account: None created
- Required: LinkedIn Company Page or personal profile with content creation rights
- API: LinkedIn Marketing API v2

**To activate:**
1. Create GHS LinkedIn Company Page
2. Apply for LinkedIn Marketing Developer Platform access
3. Generate Page Access Token via LinkedIn OAuth 2.0
4. Add `LINKEDIN_ACCESS_TOKEN` + `LINKEDIN_PAGE_ID` to Hermes `.env`
5. Create `~/.hermes-cloud/mcp-servers/linkedin_mcp.py`
6. Set `PLATFORMS["linkedin"]["configured"] = True` in router

---

### 5. Facebook — NOT CONFIGURED
**Status: ❌ No credentials · Priority 3**

- Likely sharable with Instagram META credentials (same Business Suite)
- Required: Facebook Page + Page Access Token
- API: Meta Graph API v19+

**To activate:**
1. Create GOJ/BBG Facebook Pages (or use existing if present)
2. In Meta Business Suite: generate Page Access Token (long-lived)
3. Same app as Instagram → Page token from existing META app
4. Add `FACEBOOK_PAGE_ID` + `FACEBOOK_PAGE_TOKEN` to Hermes `.env`
5. Create `~/.hermes-cloud/mcp-servers/facebook_mcp.py`

---

### 6. Twitter / X — NOT CONFIGURED
**Status: ❌ No credentials · Priority 4**

- Hermes has `x_search` in platform_toolsets (can search Twitter)
- But no write/post credentials
- Required: X Developer Account + Elevated Access + OAuth 2.0

**To activate:**
1. Go to developer.twitter.com → Create app with "Read and Write" permission
2. Generate Bearer Token + Access Token + Secret
3. Add `X_BEARER_TOKEN`, `X_API_KEY`, `X_API_SECRET`, `X_ACCESS_TOKEN`, `X_ACCESS_SECRET` to Hermes `.env`
4. Create `~/.hermes-cloud/mcp-servers/twitter_mcp.py`

---

### 7. TikTok — NOT CONFIGURED
**Status: ❌ No credentials · Priority 5**

- Open-Generative-AI handles video generation (200+ models, macOS arm64 DMG)
- TikTok API requires a creator account + business account verification
- Video content pipeline: Open-Generative-AI → manual upload OR TikTok API

**To activate:**
1. Create TikTok Business Account for BBG or GOJ
2. Register at developers.tiktok.com
3. Apply for Content Posting API access (requires review)
4. Generate client_key + client_secret
5. Add to Hermes `.env`
6. Wire Open-Generative-AI output into TikTok upload flow

---

### 8. YouTube — NOT CONFIGURED
**Status: ❌ No credentials · ⚡ Easy to activate (Google OAuth already live)**

- Google OAuth is already live (`~/.rex_google_token.json`)
- YouTube Data API v3 uses same Google credentials
- Just needs YouTube channel linked + scope `youtube.upload` added to OAuth

**To activate (fastest unconfigured platform):**
1. Create GHS YouTube channel linked to Google account
2. In Google Cloud Console: add YouTube Data API v3 to existing project
3. Re-run OAuth: `python backend/rex_gmail.py --setup` (add youtube.upload scope)
4. Add `YOUTUBE_CHANNEL_ID` to Hermes `.env`
5. Create `~/.hermes-cloud/mcp-servers/youtube_mcp.py`

---

### 9. WhatsApp Business — NOT CONFIGURED
**Status: ❌ No credentials · ⚡ High priority for GOJ families**

- Channel directory has `whatsapp: []` — supported but empty
- Meta WhatsApp Business API requires verified business number
- Highest business value: direct family communication for GOJ

**To activate:**
1. Get a dedicated phone number for GOJ WhatsApp Business
2. Register at business.whatsapp.com
3. Meta Business Verification process (requires business docs)
4. Generate WhatsApp API token via Meta Business Suite
5. Add `WHATSAPP_TOKEN` + `WHATSAPP_PHONE_NUMBER_ID` to Hermes `.env`
6. Create `~/.hermes-cloud/mcp-servers/whatsapp_mcp.py`

---

## BOT & PERSONA AUDIT

### Masha (BBG Persona)
- Platform: Retell AI
- Status: ⚠️ 404 — likely expired API key
- Purpose: BBG voice persona, social engagement
- Fix: Renew Retell API key at retellai.com → update `RETELL_API_KEY` in Hermes `.env`
- Note: When live, wire Masha into Instagram/TikTok caption voice

### Victoria (Viktoriya — GOJ)
- Platform: Retell AI
- Status: ⚠️ 404 — same key issue
- Purpose: GOJ M12 appointment confirmation calls
- Phone: 347-587-9913 (transfer number)
- Fix: Same — renew Retell API key
- Note: Victoria is phone/voice, not social media. Different from Masha.

### Hyperframes (Video Tool)
- Version: v0.5.3 at `~/.hyperframes/config.json`
- Status: ⚠️ Installed, NOT operational (1 command ever run)
- Replaced by: Open-Generative-AI (Tier 1 for BBG video)
- Action: Leave dormant. Do not enable unless Open-Generative-AI fails.

### Open-Generative-AI (Video)
- Status: macOS arm64 DMG installed, 200+ models
- Purpose: Tier 1 for BBG video content
- Use case: Generate video for TikTok/YouTube/Instagram Reels
- Action: Wire into TikTok and YouTube pipelines when those platforms are activated

### Krea.ai
- Status: ❌ NOT on disk
- Was planned for AI image generation
- Alternative: Use Hermes image_gen toolset or Claude Vision for image descriptions

---

## THE NEW ARCHITECTURE

```
Kato / Hermes
     ↓
"Make me a post about [topic]"
     ↓
CC_SOCIAL_HERMES_SKILL.md
     ↓ (PAE: Propose → Approve → Execute)
CC_social_media_router.py (FastAPI, port 8000)
     ↓
LiteLLM → Platform-specific model
  instagram   → claude-sonnet-4-6
  telegram    → deepseek-v4-pro
  email       → deepseek-v4-pro
  linkedin    → deepseek-v4-pro
  tiktok      → claude-sonnet-4-6
  twitter     → grok-3-fast
  facebook    → claude-haiku-4-5
  youtube     → claude-sonnet-4-6
  whatsapp    → claude-haiku-4-5
     ↓
CC_social_drafts.json (pending_review)
     ↓
Kato approves
     ↓
autopost platforms → MCP/n8n execute
manual platforms   → copy-paste with formatting
```

---

## INSTALLATION STEPS

### Step 1 — Register the router in REX

Add to `~/Desktop/REX/backend/main.py`:

```python
# In the imports section (near other backend imports):
from backend.CC_social_media_router import router as social_router

# After app = FastAPI(...) and existing router registrations:
app.include_router(social_router)
```

Then restart REX:
```bash
# Dev:
source ~/debate-chamber/.venv/bin/activate
cd ~/Desktop/REX
uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload

# Production:
launchctl unload ~/Library/LaunchAgents/com.rex.backend.plist
sleep 3
launchctl load ~/Library/LaunchAgents/com.rex.backend.plist
```

### Step 2 — Verify endpoints live
```bash
curl -s http://localhost:8000/social/platforms | python3 -m json.tool | head -40
```

### Step 3 — Install Hermes skill

Copy skill file to Hermes skills directory:
```bash
cp ~/Desktop/REX/CC_SOCIAL_HERMES_SKILL.md ~/.hermes/profiles/cloud/skills/ghs-social.md
```

Then reload Hermes skills (or restart gateway).

### Step 4 — Open command center

Open in browser:
```bash
open ~/Desktop/REX/CC_social_media_command_center.html
```

The command center connects to `http://localhost:8000/social/` and stores drafts in localStorage as cache.

---

## ACTIVATION PRIORITY ORDER

### Tier 1 — Ready Now (no new credentials needed)

| Platform | Action |
|---|---|
| Telegram | Already live. Register router, done. |
| Email Newsletter | Already live. Register router, done. |
| Instagram | Verify META_IG_ACCESS_TOKEN, test draft flow. No auto-post yet. |

### Tier 2 — Easy Wins (small credential work)

| Platform | Effort | Business Value |
|---|---|---|
| YouTube | Low (Google OAuth extensible) | Medium — video archive |
| WhatsApp | Medium (Meta verification) | HIGH — GOJ families |

### Tier 3 — Full Setup Required

| Platform | Effort | Business Value |
|---|---|---|
| LinkedIn | Medium | Medium — B2B, GHS positioning |
| Facebook | Medium (META already started) | Medium — community |
| Twitter/X | Medium | Low-medium — commentary |
| TikTok | High (API review + video pipeline) | High — BBG brand |

---

## BIGGEST GAPS IDENTIFIED

1. **WhatsApp is the highest-value gap.** GOJ has 425 clients with families who could receive appointment reminders, schedule changes, and updates via WhatsApp. Nothing exists for this. One phone number + Meta verification unlocks it.

2. **Instagram has MCP but no posting workflow.** The `instagram_mcp.py` exists and the token is configured — but there's no n8n workflow or router endpoint to actually push a post. Drafting works; posting doesn't.

3. **Masha and Victoria are both dead.** Same Retell API key expired for both. One key renewal fixes both phone personas.

4. **Content has no video path.** Open-Generative-AI generates video but there's no pipeline from it to TikTok/Instagram Reels/YouTube. The generation and the publishing are completely disconnected.

5. **No brand asset library.** No stored logos, colors, or approved visual templates. Every post starts from zero. A brand folder in Google Drive (already integrated) would fix this.

---

## FILES CREATED IN THIS REBUILD

| File | Purpose |
|---|---|
| `CC_social_media_router.py` | FastAPI router — all 9 platform drafters, PAE gate |
| `CC_SOCIAL_HERMES_SKILL.md` | Hermes skill — trigger phrases, routing, brand voice |
| `CC_social_media_command_center.html` | Dashboard — status, drafts, approve/reject/post |
| `CC_social_drafts.json` | Persistent draft store |
| `CC_SOCIAL_REBUILD_GUIDE.md` | This file |

All files follow `CC_` prefix convention and are saved to `~/Desktop/REX/`.

---

## NEXT STEPS FOR KATO

1. **Register router in main.py** (see Step 1 above) — 5 minutes
2. **Test draft flow**: `curl -X POST http://localhost:8000/social/draft -H "Content-Type: application/json" -d '{"topic":"Summer at BBG","platforms":["instagram","telegram"]}'`
3. **Renew Retell API key** to bring Masha and Victoria back
4. **Enable WhatsApp Business** — highest ROI action for GOJ
5. **Verify META_IG_ACCESS_TOKEN** for Instagram MCP
6. **Wire YouTube** (easiest expansion — same Google OAuth already live)
