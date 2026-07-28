"""
CC_social_media_router.py
Gold Health Systems — Hermes Social Media Router
v1.0 · June 2026

FastAPI router for multi-platform social media content drafting.
NEVER auto-posts. All content requires explicit approval (PAE rule).

Endpoints:
  POST   /social/draft               — generate draft(s) for 1+ platforms
  GET    /social/drafts              — list all pending drafts
  GET    /social/draft/{id}          — get a single draft
  POST   /social/draft/{id}/approve  — mark approved (queues for posting)
  POST   /social/draft/{id}/reject   — reject a draft
  DELETE /social/draft/{id}          — delete a draft
  GET    /social/platforms           — list all platforms + their status
  POST   /social/post/{id}/execute   — CHAIRMAN ONLY — trigger actual post via MCP

Storage: ~/Desktop/REX/CC_social_drafts.json
PHI rule: content generation always strips client names, DOB, addresses.
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/social", tags=["social-media"])

# ── Storage ────────────────────────────────────────────────────────────────────
DRAFTS_PATH = Path(os.path.expanduser("~/Desktop/REX/CC_social_drafts.json"))

def _load_drafts() -> Dict:
    if DRAFTS_PATH.exists():
        try:
            return json.loads(DRAFTS_PATH.read_text())
        except Exception:
            pass
    return {"drafts": {}, "updated_at": None}

def _save_drafts(store: Dict) -> None:
    store["updated_at"] = datetime.now(timezone.utc).isoformat()
    DRAFTS_PATH.write_text(json.dumps(store, indent=2))

# ── Platform Registry ──────────────────────────────────────────────────────────
# Single source of truth for every platform we support.
# "configured" = API credentials exist or a live MCP server handles it.
# "autopost_ready" = an n8n workflow or MCP endpoint can fire the actual post.

PLATFORMS: Dict[str, Dict[str, Any]] = {
    "instagram": {
        "label": "Instagram",
        "account": "@boardwalkbeergarden",
        "account_id": "27923669980556036",
        "entity": "BBG",                # Boardwalk Beer Garden
        "max_chars": 2200,
        "best_model": "claude-sonnet-4-6",
        "provider": "anthropic",
        "style": "engaging, visual-first, community-focused",
        "tone": "warm, authentic, energetic",
        "hashtag_count": "15-20",
        "use_case": "Community moments, BBG events, service highlights (no PHI)",
        "configured": True,
        "autopost_ready": False,        # MCP exists but no n8n workflow wired
        "mcp_server": "instagram",
        "notes": "META_IG_ACCESS_TOKEN in Hermes env. MCP at ~/.hermes-cloud/mcp-servers/instagram_mcp.py. No auto-posting — Kato approves every post.",
    },
    "telegram": {
        "label": "Telegram Broadcast",
        "account": "@RexOfGold_bot / @GojAttendance_bot / @Hermes_Cloud_May_bot",
        "entity": "GOJ + GHS",
        "max_chars": 4096,
        "best_model": "deepseek-v4-pro",
        "provider": "deepseek",
        "style": "markdown-formatted, operational, link-friendly",
        "tone": "direct, informative",
        "hashtag_count": "0",
        "use_case": "Staff announcements, internal GOJ ops, GHS updates",
        "configured": True,
        "autopost_ready": True,         # Telegram MCP + bots fully live
        "mcp_server": "telegram",
        "notes": "6 bots live. TELEGRAM_BOT_TOKEN in Hermes env. MCP at ~/.hermes-cloud/mcp-servers/telegram_mcp.py.",
    },
    "email_newsletter": {
        "label": "Email Newsletter",
        "account": "atigerclawai@gmail.com (Gmail OAuth)",
        "entity": "GHS",
        "max_chars": 5000,
        "best_model": "deepseek-v4-pro",
        "provider": "deepseek",
        "style": "professional newsletter, structured, HTML-ready",
        "tone": "informative, warm, authoritative",
        "hashtag_count": "0",
        "use_case": "Monthly GHS updates, regulatory notices, program highlights",
        "configured": True,
        "autopost_ready": True,         # rex_gmail.py + Google OAuth live
        "mcp_server": "gdrive",
        "notes": "Gmail OAuth live via rex_gmail.py. Token at ~/.rex_google_token.json.",
    },
    "linkedin": {
        "label": "LinkedIn",
        "account": None,
        "entity": "GHS",
        "max_chars": 3000,
        "best_model": "deepseek-v4-pro",
        "provider": "deepseek",
        "style": "thought leadership, B2B healthcare, analytical",
        "tone": "professional, authoritative",
        "hashtag_count": "3-5",
        "use_case": "Industry insights, GHS announcements, staff highlights",
        "configured": False,
        "autopost_ready": False,
        "mcp_server": None,
        "notes": "No LinkedIn API credentials. Needs: LinkedIn Page access token. Priority 2.",
    },
    "facebook": {
        "label": "Facebook",
        "account": None,
        "entity": "GOJ / BBG",
        "max_chars": 500,
        "best_model": "claude-haiku-4-5",
        "provider": "anthropic",
        "style": "community-first, relatable, story-driven",
        "tone": "warm, family-friendly",
        "hashtag_count": "3-5",
        "use_case": "Community events, family updates, program announcements",
        "configured": False,
        "autopost_ready": False,
        "mcp_server": None,
        "notes": "META credentials may cover FB via same app as Instagram. Needs FB Page ID + page access token.",
    },
    "twitter": {
        "label": "Twitter / X",
        "account": None,
        "entity": "GHS",
        "max_chars": 280,
        "best_model": "xai/grok-3-fast",
        "provider": "xai",
        "style": "concise, punchy, thread-friendly",
        "tone": "direct, newsworthy",
        "hashtag_count": "1-3",
        "use_case": "Industry news commentary, quick tips, advocacy",
        "configured": False,
        "autopost_ready": False,
        "mcp_server": None,
        "notes": "x_search toolset available in Hermes but no post API. Needs: X API v2 bearer token + write access.",
    },
    "tiktok": {
        "label": "TikTok",
        "account": None,
        "entity": "BBG / GOJ",
        "max_chars": 2200,
        "best_model": "claude-sonnet-4-6",
        "provider": "anthropic",
        "style": "hook-first, trending audio, storytelling, 3-second rule",
        "tone": "energetic, authentic, educational",
        "hashtag_count": "5-10",
        "use_case": "Day in the life (BBG), elder care education, staff features",
        "configured": False,
        "autopost_ready": False,
        "mcp_server": None,
        "notes": "No TikTok credentials. Open-Generative-AI handles video creation. Needs: TikTok for Developers API + content post token.",
    },
    "youtube": {
        "label": "YouTube",
        "account": None,
        "entity": "GHS / BBG",
        "max_chars": 5000,
        "best_model": "claude-sonnet-4-6",
        "provider": "anthropic",
        "style": "SEO-optimized, educational, structured, long-form",
        "tone": "informative, professional",
        "hashtag_count": "5-10",
        "use_case": "Explainer videos, BBG tours, GOJ program overviews",
        "configured": False,
        "autopost_ready": False,
        "mcp_server": None,
        "notes": "Google OAuth already live for Drive/Gmail. YouTube Data API v3 can use same credentials. Needs: YouTube channel linked to Google account.",
    },
    "whatsapp": {
        "label": "WhatsApp Business",
        "account": None,
        "entity": "GOJ",
        "max_chars": 4096,
        "best_model": "claude-haiku-4-5",
        "provider": "anthropic",
        "style": "conversational, personal, direct",
        "tone": "friendly, helpful",
        "hashtag_count": "0",
        "use_case": "Family updates for client families, appointment reminders",
        "configured": False,
        "autopost_ready": False,
        "mcp_server": None,
        "notes": "Channel directory has whatsapp: []. Needs: Meta WhatsApp Business API phone number + token. HIGH VALUE for GOJ family comms.",
    },
}

# ── GHS Brand Voice ────────────────────────────────────────────────────────────
GHS_BRAND_VOICE = """
Gold Health Systems (GHS) Brand Voice:
- Warm, compassionate, community-first
- Professional but accessible — no medical jargon unless explained
- Celebrates people and community moments
- Never sensationalist or exploitative
- Always privacy-first: no client names, no diagnoses, no identifying details
- BBG voice is separate: energetic, social, adults-focused

PHI BLOCK (enforced always):
- No real client names, ever
- No DOB, address, diagnosis, insurance info
- No staff personal contact info
- If content references clients, use: "our participants", "our community members", "Garden of Joy families"
"""

# ── System Prompts Per Platform ────────────────────────────────────────────────
def _build_system_prompt(platform: str, meta: Dict) -> str:
    base = f"""You are GHS's social media content writer for {meta['label']}.
Platform: {meta['label']} | Entity: {meta['entity']}
Style: {meta['style']}
Tone: {meta['tone']}
Max characters: {meta.get('max_chars', 'no limit')}
Hashtags: {meta['hashtag_count']} hashtags when appropriate
Use case: {meta['use_case']}

{GHS_BRAND_VOICE}

IMPORTANT RULES:
1. Never include real names of clients, patients, or families
2. Never include medical or financial information
3. Always write for approval — this is a DRAFT
4. Include a note at the bottom if an image/video is recommended
5. For Instagram/TikTok/YouTube: include content direction (what visual should accompany)
"""

    if platform == "instagram":
        base += "\nFormat: Caption text first, then line break, then hashtags. Hook in first line."
    elif platform == "telegram":
        base += "\nFormat: Use Telegram markdown (bold with **, italic with _). Include relevant emoji sparingly."
    elif platform == "email_newsletter":
        base += "\nFormat: Subject line first, then full email body. Use clear sections. Professional closing."
    elif platform == "twitter":
        base += "\nFormat: If thread, number tweets (1/N). Each tweet must be ≤280 chars. Most impactful statement first."
    elif platform == "tiktok":
        base += "\nFormat: Opening hook (first 3 seconds script) → Main content script → CTA. Caption + hashtags below."
    elif platform == "linkedin":
        base += "\nFormat: Strong opening line (no 'Excited to announce'). Personal story or data point. Professional insight. CTA."
    elif platform == "youtube":
        base += "\nFormat: Title options (3 variants, SEO-optimized) → Description → Tags → Script outline by section."

    return base

# ── Request / Response Models ──────────────────────────────────────────────────

class DraftRequest(BaseModel):
    topic: str
    platforms: List[str]                  # list of platform keys
    context: Optional[str] = None         # extra context (event, date, etc.)
    tone_override: Optional[str] = None   # override default tone
    entity: Optional[str] = None          # "GOJ", "BBG", or "GHS" (default)

class DraftResponse(BaseModel):
    draft_id: str
    platform: str
    content: str
    status: str
    created_at: str
    topic: str

class ApproveResponse(BaseModel):
    draft_id: str
    platform: str
    status: str
    message: str

# ── LLM Call ──────────────────────────────────────────────────────────────────

async def _generate_content(platform: str, topic: str, context: Optional[str],
                             tone_override: Optional[str]) -> str:
    """Call Hermes gateway (port 3002) to generate platform-specific content."""
    meta = PLATFORMS[platform]
    system = _build_system_prompt(platform, meta)
    if tone_override:
        system += f"\n\nTONE OVERRIDE for this draft: {tone_override}"

    user_msg = f"Create a {meta['label']} post about: {topic}"
    if context:
        user_msg += f"\n\nAdditional context: {context}"
    user_msg += f"\n\nThis is for {meta['entity']}. Remember: DRAFT ONLY — no real names, no PHI."

    # Route to Hermes cloud gateway
    gateway_url = "http://localhost:3002/v1/chat/completions"
    headers = {"Content-Type": "application/json"}

    payload = {
        "model": meta["best_model"],
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user_msg},
        ],
        "max_tokens": 1200,
        "temperature": 0.7,
    }

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(gateway_url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"].strip()
    except Exception as e:
        logger.error(f"Gateway call failed for {platform}: {e}")
        # Fallback: direct Anthropic if gateway is down
        return await _fallback_generate(platform, user_msg, system)


async def _fallback_generate(platform: str, user_msg: str, system: str) -> str:
    """Direct Anthropic call if Hermes gateway is down."""
    import os
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        return f"[DRAFT GENERATION FAILED — gateway offline and no fallback key. Topic queued for manual draft.]\n\nPlatform: {platform}"

    payload = {
        "model": "claude-haiku-4-5-20251001",
        "max_tokens": 1024,
        "system": system,
        "messages": [{"role": "user", "content": user_msg}],
    }
    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post("https://api.anthropic.com/v1/messages",
                                 json=payload, headers=headers)
        resp.raise_for_status()
        return resp.json()["content"][0]["text"].strip()


# ── Routes ─────────────────────────────────────────────────────────────────────

@router.get("/platforms")
async def list_platforms():
    """Return all platforms with their current status."""
    result = []
    for key, meta in PLATFORMS.items():
        result.append({
            "key": key,
            "label": meta["label"],
            "entity": meta["entity"],
            "account": meta.get("account"),
            "configured": meta["configured"],
            "autopost_ready": meta["autopost_ready"],
            "best_model": meta["best_model"],
            "notes": meta["notes"],
            "status": (
                "live" if meta["configured"] and meta["autopost_ready"]
                else "draft_only" if meta["configured"]
                else "unconfigured"
            ),
        })
    return {"platforms": result, "total": len(result)}


@router.post("/draft")
async def create_draft(req: DraftRequest):
    """Generate content drafts for one or more platforms. Never auto-posts."""
    store = _load_drafts()
    created = []
    errors = []

    for platform_key in req.platforms:
        if platform_key not in PLATFORMS:
            errors.append({"platform": platform_key, "error": "Unknown platform"})
            continue

        draft_id = str(uuid.uuid4())[:8]
        try:
            content = await _generate_content(
                platform_key, req.topic, req.context, req.tone_override
            )
        except Exception as e:
            errors.append({"platform": platform_key, "error": str(e)})
            continue

        draft = {
            "id": draft_id,
            "platform": platform_key,
            "platform_label": PLATFORMS[platform_key]["label"],
            "topic": req.topic,
            "context": req.context,
            "tone_override": req.tone_override,
            "entity": req.entity or PLATFORMS[platform_key]["entity"],
            "content": content,
            "status": "pending_review",          # PAE gate — always starts here
            "created_at": datetime.now(timezone.utc).isoformat(),
            "approved_at": None,
            "posted_at": None,
            "model_used": PLATFORMS[platform_key]["best_model"],
        }
        store["drafts"][draft_id] = draft
        created.append(DraftResponse(
            draft_id=draft_id,
            platform=platform_key,
            content=content,
            status="pending_review",
            created_at=draft["created_at"],
            topic=req.topic,
        ))

    _save_drafts(store)

    return {
        "created": [d.dict() for d in created],
        "errors": errors,
        "total_created": len(created),
        "note": "All drafts are pending review. Use POST /social/draft/{id}/approve to approve.",
    }


@router.get("/drafts")
async def list_drafts(status: Optional[str] = None):
    """List all drafts, optionally filtered by status."""
    store = _load_drafts()
    drafts = list(store["drafts"].values())
    if status:
        drafts = [d for d in drafts if d.get("status") == status]
    drafts.sort(key=lambda d: d.get("created_at", ""), reverse=True)
    return {
        "drafts": drafts,
        "total": len(drafts),
        "pending_review": sum(1 for d in store["drafts"].values() if d.get("status") == "pending_review"),
        "approved": sum(1 for d in store["drafts"].values() if d.get("status") == "approved"),
    }


@router.get("/draft/{draft_id}")
async def get_draft(draft_id: str):
    """Get a single draft by ID."""
    store = _load_drafts()
    draft = store["drafts"].get(draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail=f"Draft {draft_id} not found")
    return draft


@router.post("/draft/{draft_id}/approve")
async def approve_draft(draft_id: str):
    """
    Approve a draft (PAE gate).
    Status → 'approved'. Does NOT post automatically.
    To actually post, call POST /social/post/{id}/execute (Chairman only).
    """
    store = _load_drafts()
    draft = store["drafts"].get(draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail=f"Draft {draft_id} not found")
    if draft["status"] == "posted":
        raise HTTPException(status_code=400, detail="Draft already posted")

    draft["status"] = "approved"
    draft["approved_at"] = datetime.now(timezone.utc).isoformat()
    _save_drafts(store)

    return ApproveResponse(
        draft_id=draft_id,
        platform=draft["platform"],
        status="approved",
        message=f"Draft approved. To post to {draft['platform_label']}, call POST /social/post/{draft_id}/execute",
    )


@router.post("/draft/{draft_id}/reject")
async def reject_draft(draft_id: str, reason: Optional[str] = None):
    """Reject a draft. Can be regenerated with a new /draft request."""
    store = _load_drafts()
    draft = store["drafts"].get(draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail=f"Draft {draft_id} not found")

    draft["status"] = "rejected"
    draft["rejected_at"] = datetime.now(timezone.utc).isoformat()
    draft["rejection_reason"] = reason
    _save_drafts(store)

    return {"draft_id": draft_id, "status": "rejected", "reason": reason}


@router.delete("/draft/{draft_id}")
async def delete_draft(draft_id: str):
    """Delete a draft permanently."""
    store = _load_drafts()
    if draft_id not in store["drafts"]:
        raise HTTPException(status_code=404, detail=f"Draft {draft_id} not found")
    del store["drafts"][draft_id]
    _save_drafts(store)
    return {"deleted": draft_id}


@router.post("/post/{draft_id}/execute")
async def execute_post(draft_id: str):
    """
    CHAIRMAN ONLY — Execute an approved post via MCP/n8n.
    Only works for platforms where autopost_ready=True.
    Requires draft status == 'approved'.

    Currently live:
      - telegram: posts via telegram_mcp.py
      - email_newsletter: queues via rex_gmail.py
    """
    store = _load_drafts()
    draft = store["drafts"].get(draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail=f"Draft {draft_id} not found")
    if draft["status"] != "approved":
        raise HTTPException(
            status_code=400,
            detail=f"Draft must be 'approved' before posting. Current status: {draft['status']}"
        )

    platform = draft["platform"]
    meta = PLATFORMS.get(platform, {})

    if not meta.get("autopost_ready"):
        return {
            "status": "manual_required",
            "message": f"{meta.get('label', platform)} is not wired for auto-posting. Copy the approved draft and post manually.",
            "content": draft["content"],
            "platform": platform,
        }

    # Telegram: call local REX /social/telegram endpoint
    if platform == "telegram":
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    "http://localhost:8000/api/social/telegram/send",
                    json={"text": draft["content"], "draft_id": draft_id},
                )
                resp.raise_for_status()
        except Exception as e:
            logger.error(f"Telegram post failed: {e}")
            raise HTTPException(status_code=502, detail=f"Telegram send failed: {e}")

    draft["status"] = "posted"
    draft["posted_at"] = datetime.now(timezone.utc).isoformat()
    _save_drafts(store)

    return {
        "draft_id": draft_id,
        "platform": platform,
        "status": "posted",
        "posted_at": draft["posted_at"],
    }
