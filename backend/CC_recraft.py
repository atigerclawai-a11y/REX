"""
CC_recraft.py — Recraft 4.1 API Router
Image & vector generation, editing, style application.
Routes through Higgsfield API (your existing account) or direct Recraft API.
"""
import os
import json
import logging
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
import httpx

logger = logging.getLogger("rex.recraft")

# ── Auth sources ────────────────────────────────────────

# Option A: Higgsfield token (Recraft is on Higgsfield — use your existing account)
HIGGSFIELD_TOKEN_PATH = Path(os.getenv("HOME", os.path.expanduser("~"))) / ".hermes" / "higgsfield_token.json"

# Option B: Direct Recraft API key (fallback)
RECRAFT_API_KEY = os.getenv("RECRAFT_API_KEY", "")

# Higgsfield API base (Recraft is accessible as a model on Higgsfield)
HIGGSFIELD_BASE = "https://cloud.higgsfield.ai/api"

router = APIRouter(prefix="/recraft", tags=["recraft"])

# ── Auth helpers ────────────────────────────────────────

def _get_higgsfield_token() -> Optional[str]:
    """Load Higgsfield Bearer token if available."""
    if not HIGGSFIELD_TOKEN_PATH.exists():
        return None
    try:
        data = json.loads(HIGGSFIELD_TOKEN_PATH.read_text())
        return data.get("access_token")
    except (json.JSONDecodeError, KeyError):
        return None


def _get_active_auth() -> tuple[str, str]:
    """
    Returns (auth_method, token_or_key).
    Prefers Higgsfield token over direct Recraft key.
    """
    hf_token = _get_higgsfield_token()
    if hf_token:
        return ("higgsfield", hf_token)
    if RECRAFT_API_KEY:
        return ("recraft_direct", RECRAFT_API_KEY)
    raise HTTPException(
        status_code=500,
        detail="No auth configured. Save Higgsfield token to ~/.hermes/higgsfield_token.json "
               "or set RECRAFT_API_KEY in ~/Desktop/REX/.env",
    )


async def _generate_via_higgsfield(prompt: str, style: str, width: int, height: int, num_images: int) -> dict:
    """Use Higgsfield's API to call Recraft 4.1 model."""
    _, token = _get_active_auth()
    payload = {
        "model": "recraft-v4-1",
        "prompt": prompt,
        "style": style,
        "width": width,
        "height": height,
        "n": num_images,
    }
    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.post(
            f"{HIGGSFIELD_BASE}/generate/image",
            json=payload,
            headers={"Authorization": f"Bearer {token}"},
        )
        if resp.status_code == 401:
            raise HTTPException(status_code=401, detail="Higgsfield token expired. Re-authenticate.")
        if resp.status_code != 200:
            logger.error(f"Higgsfield API error {resp.status_code}: {resp.text}")
            raise HTTPException(status_code=502, detail=f"Higgsfield error: {resp.text[:300]}")
        return resp.json()


async def _generate_via_recraft(prompt: str, style: str, width: int, height: int, num_images: int) -> dict:
    """Use Recraft API directly."""
    payload = {
        "style": style,
        "prompt": prompt,
        "n": num_images,
        "size": f"{width}x{height}",
    }
    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.post(
            "https://api.recraft.ai/v1/images/generations",
            json=payload,
            headers={"Authorization": f"Bearer {RECRAFT_API_KEY}"},
        )
        if resp.status_code != 200:
            raise HTTPException(status_code=502, detail=f"Recraft error: {resp.text[:300]}")
        return resp.json()


# ── Models ──────────────────────────────────────────────

class GenerateRequest(BaseModel):
    prompt: str
    style: str = "digital_illustration"
    width: int = 1024
    height: int = 1024
    num_images: int = Field(default=1, ge=1, le=4)

class EditRequest(BaseModel):
    image_url: str
    prompt: str
    mask: Optional[str] = None

# ── Endpoints ───────────────────────────────────────────

@router.get("/styles")
async def list_styles():
    """Available Recraft styles (all accessible via your Higgsfield account)."""
    styles = [
        {"id": "digital_illustration", "name": "Digital Illustration", "category": "illustration"},
        {"id": "realistic_image", "name": "Realistic Image", "category": "photography"},
        {"id": "vector_illustration", "name": "Vector Illustration", "category": "vector"},
        {"id": "pixel_art", "name": "Pixel Art", "category": "retro"},
        {"id": "icon", "name": "Icon", "category": "vector"},
        {"id": "logo", "name": "Logo", "category": "branding"},
        {"id": "3d_render", "name": "3D Render", "category": "3d"},
        {"id": "anime", "name": "Anime", "category": "illustration"},
        {"id": "oil_painting", "name": "Oil Painting", "category": "fine_art"},
        {"id": "watercolor", "name": "Watercolor", "category": "fine_art"},
        {"id": "pop_art", "name": "Pop Art", "category": "fine_art"},
        {"id": "line_art", "name": "Line Art", "category": "illustration"},
        {"id": "isometric", "name": "Isometric", "category": "3d"},
        {"id": "claymation", "name": "Claymation", "category": "3d"},
        {"id": "cinematic", "name": "Cinematic", "category": "photography"},
        {"id": "product_photography", "name": "Product Photography", "category": "photography"},
        {"id": "fantasy_art", "name": "Fantasy Art", "category": "illustration"},
        {"id": "comic_book", "name": "Comic Book", "category": "illustration"},
        {"id": "hand_drawn", "name": "Hand Drawn", "category": "illustration"},
        {"id": "neon_punk", "name": "Neon Punk", "category": "illustration"},
    ]
    return {"styles": styles, "count": len(styles)}


@router.post("/generate")
async def generate_image(req: GenerateRequest):
    """
    Generate images using Recraft 4.1 (routed through your Higgsfield account).
    Returns image URLs — feed directly into the Instagram pipeline.
    """
    method, _ = _get_active_auth()

    if method == "higgsfield":
        result = await _generate_via_higgsfield(
            req.prompt, req.style, req.width, req.height, req.num_images
        )
    else:
        result = await _generate_via_recraft(
            req.prompt, req.style, req.width, req.height, req.num_images
        )

    return {"auth_source": method, **result}


@router.post("/edit")
async def edit_image(req: EditRequest):
    """Edit an existing image — inpainting, outpainting, or prompt-based edits."""
    method, token = _get_active_auth()

    payload = {"image": req.image_url, "prompt": req.prompt}
    if req.mask:
        payload["mask"] = req.mask

    if method == "higgsfield":
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(
                f"{HIGGSFIELD_BASE}/edit/image",
                json=payload,
                headers={"Authorization": f"Bearer {token}"},
            )
            if resp.status_code != 200:
                raise HTTPException(status_code=502, detail=resp.text[:300])
            return {"auth_source": method, **resp.json()}
    else:
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(
                "https://api.recraft.ai/v1/images/edits",
                json=payload,
                headers={"Authorization": f"Bearer {token}"},
            )
            if resp.status_code != 200:
                raise HTTPException(status_code=502, detail=resp.text[:300])
            return {"auth_source": method, **resp.json()}


@router.get("/health")
async def health():
    """Check auth status and connectivity."""
    hf_token = _get_higgsfield_token()
    has_recraft_key = bool(RECRAFT_API_KEY)

    status = {
        "higgsfield_token": bool(hf_token),
        "recraft_direct_key": has_recraft_key,
    }

    if not hf_token and not has_recraft_key:
        status["status"] = "not_configured"
        status["detail"] = "Save Higgsfield token or set RECRAFT_API_KEY"
        return status

    # Test connectivity with whatever auth we have
    auth_method, token = "higgsfield" if hf_token else "recraft_direct", hf_token or RECRAFT_API_KEY
    base = HIGGSFIELD_BASE if hf_token else "https://api.recraft.ai/v1"

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{base}/models" if not hf_token else f"{base}/me",
                headers={"Authorization": f"Bearer {token}"},
            )
            status["status"] = "ok" if resp.status_code == 200 else "auth_error"
            status["auth_method"] = auth_method
    except Exception as e:
        status["status"] = "unreachable"
        status["error"] = str(e)

    return status
