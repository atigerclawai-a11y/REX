"""
CC_higgsfield.py — Higgsfield AI Router
Full Higgsfield ecosystem via CLI binary backend + web-only tool catalog.
One token, all models — authenticated via `higgsfield auth login`.
"""
import os
import json
import logging
import asyncio
import shlex
from pathlib import Path
from typing import Optional
from datetime import datetime
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

logger = logging.getLogger("rex.higgsfield")

HIGGSFIELD_CLI = "/opt/homebrew/bin/higgsfield"

router = APIRouter(prefix="/higgsfield", tags=["higgsfield"])

# ═══════════════════════════════════════════════════════════
# Models Catalog
# ═══════════════════════════════════════════════════════════

IMAGE_MODELS = {
    "recraft-v4-1":    {"name": "Recraft 4.1",     "type": "image", "notes": "Vectors, 100+ styles, SVG"},
    "soul-v2":         {"name": "Soul V2",         "type": "image", "notes": "Character-consistent generation"},
    "seedream-4":      {"name": "Seedream 4.0",    "type": "image", "notes": "ByteDance photorealism"},
    "wan-2.2":         {"name": "Wan 2.2",         "type": "image", "notes": "Alibaba composition"},
    "nano-banana":     {"name": "Nano Banana",     "type": "image", "notes": "Quick high-quality visuals"},
    "nano-banana-pro": {"name": "Nano Banana Pro", "type": "image", "notes": "Premium high-quality visuals"},
    "flux-kontext":    {"name": "Flux Kontext",    "type": "image", "notes": "Black Forest Labs"},
    "ideogram":        {"name": "Ideogram",        "type": "image", "notes": "Text-in-image specialist"},
    "gpt-image-2":     {"name": "GPT Image 2",     "type": "image", "notes": "OpenAI (web-only, API soon)"},
}

VIDEO_MODELS = {
    "seedance-2":       {"name": "Seedance 2.0 / Pro",  "type": "video", "notes": "Flagship. 30-day unlimited"},
    "kling-2.1-master": {"name": "Kling 2.1 Master",    "type": "video", "notes": "Kuaishou — master quality"},
    "kling-2.5-turbo":  {"name": "Kling 2.5 Turbo",     "type": "video", "notes": "Kuaishou — fast turbo"},
    "kling-3":          {"name": "Kling 3.0 / o1",       "type": "video", "notes": "Kuaishou — latest, stylized"},
    "kling-avatars":    {"name": "Kling Avatars 2.0",    "type": "video", "notes": "LipSync Studio — talking avatars"},
    "minimax-hailuo":   {"name": "MiniMax Hailuo 02",    "type": "video", "notes": "Strong realism"},
    "cinema-studio":    {"name": "Cinema Studio 3.5",    "type": "video", "notes": "Cinematic scene generation"},
    "wan-2.5":          {"name": "Wan 2.5",              "type": "video", "notes": "Alibaba video generation"},
    "sora-2":           {"name": "Sora 2",               "type": "video", "notes": "OpenAI video + platform presets"},
    "google-veo3":      {"name": "Google Veo3",           "type": "video", "notes": "Google's video model"},
}

ALL_MODELS = {**IMAGE_MODELS, **VIDEO_MODELS}

# Map our model IDs to Higgsfield CLI job_set_type names
CLI_MODEL_MAP = {
    "recraft-v4-1":    "recraft_v4_1",
    "soul-v2":         "soul_v3",
    "seedream-4":      "seedream_4",
    "wan-2.2":         "wan_2_2_image",
    "nano-banana":     "nano_banana",
    "nano-banana-pro": "nano_banana_2",
    "flux-kontext":    "flux_kontext",
    "ideogram":        "ideogram_v_3",
    "gpt-image-2":     "gpt_image_2",
    "seedance-2":       "seedance_2_0",
    "kling-2.1-master": "kling2_6",
    "kling-2.5-turbo":  "kling3_0_turbo",
    "kling-3":          "kling3_0",
    "kling-avatars":    "kling_avatars",
    "minimax-hailuo":   "minimax_hailuo",
    "cinema-studio":    "cinematic_studio_3_0",
    "wan-2.5":          "wan2_6",
    "sora-2":           "sora_2",
    "google-veo3":      "veo3",
}

VIRAL_PRESETS = {
    "baseball-game":    {"name": "Baseball Game",   "creator": "Buralqy", "category": "sports"},
    "drift-racing":     {"name": "Drift Racing",    "creator": "Buralqy", "category": "racing"},
    "cgi-breakdown":    {"name": "CGI Breakdown",   "creator": "Buralqy", "category": "vfx"},
    "football-invader": {"name": "Football Invader","creator": "Buralqy", "category": "sports"},
    "summer-haze":      {"name": "Summer Haze",     "creator": "Buralqy", "category": "mood"},
    "kung-fu-hit":      {"name": "Kung Fu Hit",     "creator": "Buralqy", "category": "action"},
    "final-serve":      {"name": "Final Serve",     "creator": "Buralqy", "category": "sports"},
    "android-assemble": {"name": "Android Assemble","creator": "Buralqy", "category": "sci-fi"},
    "3d-render":        {"name": "3D Render",       "creator": "Buralqy", "category": "vfx"},
    "storm-giant":      {"name": "Storm Giant",     "creator": "Buralqy", "category": "fantasy"},
    "blue-depth":       {"name": "Blue Depth",      "creator": "Buralqy", "category": "mood"},
    "orbital-presence": {"name": "Orbital Presence","creator": "Buralqy", "category": "sci-fi"},
    "zombie-dance":     {"name": "Zombie Dance",    "creator": "Buralqy", "category": "horror"},
    "golf-major":       {"name": "Golf Major",      "creator": "Buralqy", "category": "sports"},
    "2000s-paparazzi":  {"name": "2000's Paparazzi","creator": "Buralqy", "category": "cinematic"},
    "candid-paparazzi": {"name": "Candid Paparazzi","creator": "Buralqy", "category": "cinematic"},
    "race-track":       {"name": "Race Track",      "creator": "Buralqy", "category": "racing"},
    "drown-in-music":   {"name": "Drown in Music",  "creator": "Buralqy", "category": "music"},
    "nightline":        {"name": "Nightline",       "creator": "Buralqy", "category": "mood"},
    "free-fall":        {"name": "Free Fall",       "creator": "Buralqy", "category": "action"},
    "red-carpet":       {"name": "Red Carpet",      "creator": "Buralqy", "category": "cinematic"},
    "neon-city":        {"name": "Neon City",       "creator": "Buralqy", "category": "sci-fi"},
    "soul-fighter":     {"name": "Soul Fighter",    "creator": "Buralqy", "category": "action"},
    "tuscan-yoga":      {"name": "Tuscan Yoga",     "creator": "Buralqy", "category": "mood"},
    "apex-hunter":      {"name": "Apex Hunter",     "creator": "Buralqy", "category": "action"},
    "in-the-dark":      {"name": "In the Dark",     "creator": "Buralqy", "category": "mood"},
    "red-thread":       {"name": "Red Thread",      "creator": "Buralqy", "category": "fantasy"},
    "exit-the-dream":   {"name": "Exit the Dream",  "creator": "Buralqy", "category": "fantasy"},
    "ending-fairy":     {"name": "Ending Fairy",    "creator": "Buralqy", "category": "fantasy"},
    "dragon-fantasy":   {"name": "Dragon Fantasy",  "creator": "Buralqy", "category": "fantasy"},
    "fan-meeting":      {"name": "Fan Meeting",     "creator": "Buralqy", "category": "cinematic"},
    "night-vision":     {"name": "Night Vision",    "creator": "Buralqy", "category": "mood"},
    "office-cctv":      {"name": "Office CCTV",     "creator": "Buralqy", "category": "cinematic"},
    "race-winner":      {"name": "Race Winner",     "creator": "Buralqy", "category": "racing"},
    "sora-2-presets":   {"name": "Sora 2 Presets",  "creator": "Higgsfield", "category": "video"},
}

SORA_PLATFORMS = {
    "youtube":        {"aspect": "16:9", "resolution": "1920x1080", "max_duration": 60},
    "tiktok":         {"aspect": "9:16", "resolution": "1080x1920", "max_duration": 180},
    "instagram-reel": {"aspect": "9:16", "resolution": "1080x1920", "max_duration": 90},
    "youtube-shorts": {"aspect": "9:16", "resolution": "1080x1920", "max_duration": 60},
}

WEB_ONLY = "This tool is web-only on higgsfield.ai — no CLI or API endpoint exists yet. Visit https://higgsfield.ai to use it."

# ═══════════════════════════════════════════════════════════
# CLI Backend
# ═══════════════════════════════════════════════════════════

async def _run_cli(*args: str, timeout: float = 600.0) -> dict:
    """Run Higgsfield CLI and return parsed JSON output (async)."""
    cmd = [HIGGSFIELD_CLI, "--json", "--no-color"] + list(args)
    cmd_str = ' '.join(shlex.quote(a) for a in cmd)
    logger.info(f"Higgsfield CLI: {cmd_str}")
    
    env = os.environ.copy()
    env["PATH"] = "/opt/homebrew/bin:" + env.get("PATH", "/usr/bin:/bin")
    
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        stdout_text = stdout.decode().strip()
        stderr_text = stderr.decode().strip()
        
        if proc.returncode != 0:
            error_msg = stderr_text or stdout_text or f"exit code {proc.returncode}"
            logger.error(f"CLI error ({cmd_str}): {error_msg}")
            raise HTTPException(status_code=502, detail=f"Higgsfield CLI error: {error_msg[:300]}")
        
        if not stdout_text:
            return {"status": "ok"}
        
        try:
            return json.loads(stdout_text)
        except json.JSONDecodeError:
            return {"status": "ok", "output": stdout_text}
            
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail=f"Higgsfield CLI timed out after {timeout}s")
    except FileNotFoundError:
        raise HTTPException(status_code=500, detail=f"Higgsfield CLI not found at {HIGGSFIELD_CLI}")


def _check_auth() -> dict:
    """Verify CLI is authenticated (sync wrapper — used in sync context)."""
    import subprocess
    cmd = [HIGGSFIELD_CLI, "--json", "--no-color", "auth", "token"]
    env = os.environ.copy()
    env["PATH"] = "/opt/homebrew/bin:" + env.get("PATH", "/usr/bin:/bin")
    
    try:
        result = subprocess.run(cmd, capture_output=True, timeout=10, text=True, env=env)
        token = result.stdout.strip()
        if not token or "not authenticated" in token.lower():
            raise HTTPException(status_code=401, detail="Not authenticated. Run: higgsfield auth login")
        return {"authenticated": True, "token_preview": token[:16] + "..."}
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail="Auth check timed out")
    except FileNotFoundError:
        raise HTTPException(status_code=500, detail=f"Higgsfield CLI not found at {HIGGSFIELD_CLI}")


async def _async_check_auth():
    """Async auth check for use in async endpoints."""
    result = await _run_cli("auth", "token", timeout=10)
    token = result.get("output", "")
    if not token or "not authenticated" in token.lower():
        raise HTTPException(status_code=401, detail="Not authenticated. Run: higgsfield auth login")
    return {"authenticated": True, "token_preview": token[:16] + "..."}


async def _cli_generate(model_id: str, prompt: str, **extra) -> dict:
    """Generate via CLI: higgsfield generate create <model> --prompt "..." --wait"""
    await _async_check_auth()
    cli_model = CLI_MODEL_MAP.get(model_id, model_id)
    
    args = ["generate", "create", cli_model, "--prompt", prompt, "--wait"]
    
    for key in ["duration"]:
        value = extra.pop(key, None)
        if value:
            args += ["--" + key, str(value)]
    
    raw = await _run_cli(*args, timeout=900.0)
    
    # CLI returns an array of job results — pick the first one
    if isinstance(raw, list) and raw:
        result = raw[0]
    elif isinstance(raw, dict):
        result = raw
    else:
        result = {"raw_output": str(raw)}
    
    return {
        "model": model_id,
        "cli_model": cli_model,
        "prompt": prompt,
        "job_id": result.get("id"),
        "status": result.get("status"),
        "result_url": result.get("result_url"),
        "display_name": result.get("display_name"),
    }


# ═══════════════════════════════════════════════════════════
# Request Models
# ═══════════════════════════════════════════════════════════

class ImageGenerateRequest(BaseModel):
    prompt: str
    model: str = "recraft-v4-1"
    width: int = Field(default=1024, ge=256, le=2048)
    height: int = Field(default=1024, ge=256, le=2048)
    num_images: int = Field(default=1, ge=1, le=4)

class VideoGenerateRequest(BaseModel):
    prompt: str
    model: str = "seedance-2"
    duration: int = Field(default=5, ge=1, le=30)

class PresetApplyRequest(BaseModel):
    preset: str
    prompt: str
    model: str = "seedance-2"
    duration: int = Field(default=5, ge=1, le=30)

class SoraPresetRequest(BaseModel):
    prompt: str
    platform: str = "tiktok"
    duration: int = Field(default=10, ge=1, le=180)

class CampaignRequest(BaseModel):
    prompt: str
    platforms: list[str] = ["instagram", "tiktok"]
    num_assets: int = Field(default=3, ge=1, le=10)
    include_video: bool = True
    include_image: bool = True


# ═══════════════════════════════════════════════════════════
# Health & Auth
# ═══════════════════════════════════════════════════════════

@router.get("/health")
async def health():
    """Full health check: auth status + models available."""
    status = {
        "router": "higgsfield",
        "backend": "CLI",
        "cli_path": HIGGSFIELD_CLI,
        "models_available": len(ALL_MODELS),
        "image_models": len(IMAGE_MODELS),
        "video_models": len(VIDEO_MODELS),
    }
    
    try:
        auth = _check_auth()
        status["auth"] = "ok"
        status["token"] = auth["token_preview"]
    except HTTPException as e:
        status["auth"] = "not_authenticated"
        status["detail"] = str(e.detail)
    except Exception as e:
        status["auth"] = "error"
        status["detail"] = str(e)[:200]
    
    return status


# ═══════════════════════════════════════════════════════════
# Models Catalog
# ═══════════════════════════════════════════════════════════

@router.get("/models")
async def list_models():
    return {
        "image_models": {k: {"name": v["name"], "notes": v["notes"]} for k, v in IMAGE_MODELS.items()},
        "video_models": {k: {"name": v["name"], "notes": v["notes"]} for k, v in VIDEO_MODELS.items()},
        "total": len(ALL_MODELS),
    }

@router.get("/models/{model_id}")
async def model_info(model_id: str):
    if model_id in ALL_MODELS:
        return {"id": model_id, **ALL_MODELS[model_id]}
    raise HTTPException(status_code=404, detail=f"Unknown model: {model_id}")


# ═══════════════════════════════════════════════════════════
# Image & Video Generation (CLI-backed)
# ═══════════════════════════════════════════════════════════

@router.post("/generate/image")
async def generate_image(req: ImageGenerateRequest):
    """Generate images using any Higgsfield-bundled image model (CLI-backed)."""
    if req.model not in IMAGE_MODELS:
        raise HTTPException(status_code=400, detail=f"Unknown image model: {req.model}")
    
    result = await _cli_generate(req.model, req.prompt,
                          width=req.width, height=req.height, count=req.num_images)
    result["model_name"] = IMAGE_MODELS[req.model]["name"]
    return result


@router.post("/generate/video")
async def generate_video(req: VideoGenerateRequest):
    """Generate videos using any Higgsfield-bundled video model (CLI-backed)."""
    if req.model not in VIDEO_MODELS:
        raise HTTPException(status_code=400, detail=f"Unknown video model: {req.model}")
    
    result = await _cli_generate(req.model, req.prompt, duration=req.duration)
    result["model_name"] = VIDEO_MODELS[req.model]["name"]
    return result


@router.post("/seed")
async def seed_video(prompt: str, duration: int = 5):
    """Quick video seed — shortcut to Seedance 2.0."""
    return await _cli_generate("seedance-2", prompt, duration=duration)


# ═══════════════════════════════════════════════════════════
# Viral Presets
# ═══════════════════════════════════════════════════════════

@router.get("/presets")
async def list_presets(category: Optional[str] = None):
    """35+ Viral Presets. Filter by category."""
    if category:
        filtered = {k: v for k, v in VIRAL_PRESETS.items() if v["category"] == category}
        return {"presets": filtered, "count": len(filtered), "total": len(VIRAL_PRESETS)}
    
    by_category = {}
    for k, v in VIRAL_PRESETS.items():
        by_category.setdefault(v["category"], []).append({"id": k, **v})
    
    return {"presets": VIRAL_PRESETS, "by_category": by_category, "count": len(VIRAL_PRESETS)}


@router.post("/presets/apply")
async def apply_preset(req: PresetApplyRequest):
    """Apply a Viral Preset to video generation. Uses CLI with preset name in prompt."""
    if req.preset not in VIRAL_PRESETS:
        closest = [k for k in VIRAL_PRESETS if req.preset[:4] in k][:5]
        hint = f" Similar: {', '.join(closest)}" if closest else ""
        raise HTTPException(status_code=400, detail=f"Unknown preset: {req.preset}.{hint}")
    
    if req.model not in VIDEO_MODELS:
        raise HTTPException(status_code=400, detail=f"Unknown model: {req.model}")
    
    preset_info = VIRAL_PRESETS[req.preset]
    enhanced_prompt = f"[{preset_info['name']} style] {req.prompt}"
    
    result = await _cli_generate(req.model, enhanced_prompt, duration=req.duration)
    result["preset"] = req.preset
    result["preset_name"] = preset_info["name"]
    return result


# ═══════════════════════════════════════════════════════════
# Marketing Studio (CLI-backed)
# ═══════════════════════════════════════════════════════════

@router.post("/marketing/campaign")
async def create_campaign(req: CampaignRequest):
    """Launch a marketing campaign via Higgsfield Marketing Studio CLI."""
    await _async_check_auth()
    
    args = [
        "marketing-studio", "create",
        "--prompt", req.prompt,
        "--platforms", ",".join(req.platforms),
        "--count", str(req.num_assets),
        "--wait",
    ]
    
    result = await _run_cli(*args, timeout=600.0)
    return {"platforms": req.platforms, "assets_requested": req.num_assets, **result}


# ═══════════════════════════════════════════════════════════
# Sora 2 Platform Presets
# ═══════════════════════════════════════════════════════════

@router.get("/sora/platforms")
async def sora_platforms():
    return {"model": "Sora 2", "platforms": SORA_PLATFORMS}

@router.post("/sora/generate")
async def sora_generate(req: SoraPresetRequest):
    """Generate Sora 2 video optimized for a specific platform."""
    if req.platform not in SORA_PLATFORMS:
        raise HTTPException(status_code=400, detail=f"Unknown platform: {req.platform}")
    
    preset = SORA_PLATFORMS[req.platform]
    platform_hint = f"[{req.platform} format]"
    
    result = await _cli_generate("sora-2", f"{platform_hint} {req.prompt}",
                          duration=min(req.duration, preset["max_duration"]))
    result["platform"] = req.platform
    result["optimized_for"] = preset
    return result


# ═══════════════════════════════════════════════════════════
# Product Photoshoot (CLI-backed — Banana Placement equivalent)
# ═══════════════════════════════════════════════════════════

class PhotoshootRequest(BaseModel):
    prompt: str
    mode: str = "lifestyle_scene"
    """lifestyle_scene | studio_lighting | flat_lay | product_hero"""
    image_url: Optional[str] = None
    count: int = Field(default=1, ge=1, le=5)


@router.post("/product-photoshoot")
async def product_photoshoot(req: PhotoshootRequest):
    """Brand-quality product photoshoot via CLI. Banana Placement equivalent."""
    await _async_check_auth()
    
    args = [
        "product-photoshoot", "create",
        "--mode", req.mode,
        "--prompt", req.prompt,
        "--count", str(req.count),
        "--wait",
    ]
    if req.image_url:
        args += ["--image", req.image_url]
    
    raw = await _run_cli(*args, timeout=600.0)
    result = raw[0] if isinstance(raw, list) and raw else raw
    return {
        "mode": req.mode,
        "job_id": result.get("id"),
        "status": result.get("status"),
        "result_url": result.get("result_url"),
    }


# ═══════════════════════════════════════════════════════════
# Soul ID — Character Training (CLI-backed — Photodump / Multi-Reference)
# ═══════════════════════════════════════════════════════════

class SoulCreateRequest(BaseModel):
    name: str
    image_ids: list[str]
    """2-5 upload IDs for character reference images"""


@router.post("/soul-id/create")
async def soul_create(req: SoulCreateRequest):
    """Train a custom Soul character reference from images (Photodump backend)."""
    await _async_check_auth()
    
    args = ["soul-id", "create", "--name", req.name, "--soul-2"]
    for img_id in req.image_ids:
        args += ["--image", img_id]
    
    raw = await _run_cli(*args, timeout=300.0)
    return {"soul_name": req.name, **raw}


@router.get("/soul-ids")
async def soul_list():
    """List trained Soul character references."""
    await _async_check_auth()
    return await _run_cli("soul-id", "list", timeout=30)


@router.get("/soul-ids/{soul_id}")
async def soul_get(soul_id: str):
    """Get a specific Soul character reference."""
    await _async_check_auth()
    return await _run_cli("soul-id", "get", soul_id, timeout=30)


@router.post("/soul-ids/{soul_id}/wait")
async def soul_wait(soul_id: str):
    """Wait for Soul training to complete."""
    await _async_check_auth()
    return await _run_cli("soul-id", "wait", soul_id, timeout=600)


# ═══════════════════════════════════════════════════════════
# Marketplace Cards (CLI-backed)
# ═══════════════════════════════════════════════════════════

class MarketplaceCardRequest(BaseModel):
    prompt: str
    scope: str = "product-images"
    """product-images | secondary-images | a-plus-modules"""
    image_url: Optional[str] = None


@router.post("/marketplace-cards")
async def marketplace_cards(req: MarketplaceCardRequest):
    """Create marketplace product cards via CLI."""
    await _async_check_auth()
    
    args = [
        "marketplace-cards", "create",
        "--scope", req.scope,
        "--prompt", req.prompt,
        "--wait",
    ]
    if req.image_url:
        args += ["--image", req.image_url]
    
    raw = await _run_cli(*args, timeout=600.0)
    result = raw[0] if isinstance(raw, list) and raw else raw
    return {
        "scope": req.scope,
        "job_id": result.get("id"),
        "status": result.get("status"),
        "result_url": result.get("result_url"),
    }


# ═══════════════════════════════════════════════════════════
# Game Deploy (CLI-backed)
# ═══════════════════════════════════════════════════════════

class GameDeployRequest(BaseModel):
    title: str
    description: str = ""
    zip_path: str = ""
    """Local path to game ZIP archive"""


@router.post("/game/deploy")
async def game_deploy(req: GameDeployRequest):
    """Deploy a browser game to Higgsfield marketplace."""
    await _async_check_auth()
    
    args = ["game", "deploy", req.zip_path, "--title", req.title]
    if req.description:
        args += ["--description", req.description]
    
    return await _run_cli(*args, timeout=300.0)


# ═══════════════════════════════════════════════════════════
# Workflows (CLI-backed)
# ═══════════════════════════════════════════════════════════

@router.get("/workflows")
async def workflow_list():
    """List all Higgsfield workflows."""
    await _async_check_auth()
    return await _run_cli("workflow", "list", timeout=30)


@router.get("/workflows/{name}")
async def workflow_get(name: str):
    """Get workflow parameters."""
    await _async_check_auth()
    return await _run_cli("workflow", "get", name, timeout=30)


# ═══════════════════════════════════════════════════════════
# Upload (CLI-backed — media input)
# ═══════════════════════════════════════════════════════════

@router.get("/uploads")
async def upload_list(media_type: str = "image"):
    """List uploaded media IDs."""
    await _async_check_auth()
    return await _run_cli("upload", "list", f"--{media_type}", timeout=30)


# ═══════════════════════════════════════════════════════════
# Account (CLI-backed)
# ═══════════════════════════════════════════════════════════

@router.get("/account")
async def account_status():
    """Account balance, plan, credits."""
    await _async_check_auth()
    return await _run_cli("account", "status", timeout=15)


@router.get("/account/transactions")
async def account_transactions(size: int = 20):
    """Recent credit transactions."""
    await _async_check_auth()
    return await _run_cli("account", "transactions", "--size", str(size), timeout=15)


# ═══════════════════════════════════════════════════════════
# Web-Only Tools (no CLI/API)
# ═══════════════════════════════════════════════════════════

@router.get("/predict")
async def predict_info():
    return {
        "tool": "Virality Predictor",
        "status": "web_only",
        "desc": "Upload clip → hook score, attention curve, viral potential",
        "url": "https://higgsfield.ai",
    }

@router.post("/predict")
async def predict_virality():
    raise HTTPException(status_code=501, detail="Virality Predictor is web-only. " + WEB_ONLY)

@router.post("/predict/upload")
async def predict_upload():
    raise HTTPException(status_code=501, detail=WEB_ONLY)

@router.post("/supercomputer/task")
async def supercomputer_task():
    raise HTTPException(status_code=501, detail="Supercomputer is web-only. " + WEB_ONLY)

@router.post("/supercomputer/clip")
async def personal_clipper():
    raise HTTPException(status_code=501, detail="Personal Clipper is web-only. " + WEB_ONLY)

@router.post("/avatars/lipsync")
async def lipsync_avatar():
    raise HTTPException(status_code=501, detail="Kling LipSync Studio is web-only. " + WEB_ONLY)

@router.post("/edit/inpaint")
async def edit_inpaint():
    raise HTTPException(status_code=501, detail="Edit Image / Inpaint is web-only. " + WEB_ONLY)

@router.post("/edit/upscale")
async def upscale_image():
    raise HTTPException(status_code=501, detail="Upscale (Topaz) is web-only. " + WEB_ONLY)


# ═══════════════════════════════════════════════════════════
# Camera Controls & Action Movements (informational)
# ═══════════════════════════════════════════════════════════

@router.get("/controls")
async def camera_controls():
    return {
        "camera_controls": [
            "dolly-zoom", "tracking-shot", "aerial-drone", "handheld",
            "static-tripod", "crane-shot", "steadicam", "dutch-angle",
        ],
        "action_movements": [
            "slow-motion", "speed-ramp", "time-lapse", "freeze-frame",
            "whip-pan", "crash-zoom", "bullet-time", "match-cut",
        ],
        "commercial_styles": [
            "product-hero", "lifestyle", "testimonial", "tutorial",
            "behind-the-scenes", "comparison", "unboxing", "social-proof",
        ],
        "usage": "Use these in the prompt or style field of /generate/video",
    }


# ═══════════════════════════════════════════════════════════
# Content & Extensions
# ═══════════════════════════════════════════════════════════

@router.get("/originals")
async def original_series():
    return {
        "platform": "Higgsfield Original Series",
        "shows": [{"title": "Zephyr", "type": "series", "status": "streaming",
                    "episodes": [{"title": "Arena Zero"}]}],
        "url": "https://higgsfield.ai/original-series",
    }

@router.get("/games")
async def games():
    return {
        "platforms": [
            {"name": "Higgsfield Games", "type": "browser"},
            {"name": "Claude MCP", "type": "mcp"},
        ],
        "mods": [{"name": "Minecraft Mod", "type": "mod"}],
        "url": "https://higgsfield.ai",
    }

@router.get("/community")
async def community():
    return {
        "communities": [
            "Marketing Studio", "Seedance 2.0", "GPT Image 2",
            "Higgsfield Soul Cinema", "Soul 2.0", "Mixed Media",
            "Soul Presets", "Visual Effects",
        ],
        "collections": ["Soul Presets Collection", "Visual Effects Collection", "Sora 2 Presets"],
    }

@router.get("/canvas")
async def canvas_info():
    return {
        "name": "Higgsfield Canvas",
        "url": "https://higgsfield.ai/canvas",
        "features": ["Moodboard", "Chain workflows", "Team sharing", "One surface"],
        "status": "New",
    }

@router.get("/assists")
async def assists():
    return {"name": "Assists", "type": "chat", "url": "https://higgsfield.ai"}


@router.get("/extensions")
async def list_extensions():
    """Complete Higgsfield inventory."""
    return {
        "auth": "CLI token (higgsfield auth login)",
        "models": {"image": len(IMAGE_MODELS), "video": len(VIDEO_MODELS), "total": len(ALL_MODELS)},
        "cli_backed": {
            "generation": [
                "POST /generate/image       — 9 image models",
                "POST /generate/video       — 10 video models",
                "POST /seed                  — quick Seedance",
                "POST /presets/apply         — 35 Viral Presets → video",
                "POST /sora/generate         — Sora 2 platform presets",
            ],
            "tools": [
                "POST /marketing/campaign    — Marketing Studio",
                "POST /product-photoshoot    — Product Photoshoot (Banana Placement)",
                "POST /marketplace-cards      — Marketplace product cards",
                "POST /soul-id/create         — Train Soul character (Photodump)",
                "GET  /soul-ids               — List Soul references",
                "GET  /soul-ids/{id}          — Get Soul reference",
                "POST /soul-ids/{id}/wait     — Wait for Soul training",
                "POST /game/deploy            — Deploy browser game",
            ],
            "info": [
                "GET  /workflows              — List workflows",
                "GET  /workflows/{name}       — Get workflow params",
                "GET  /uploads                — List uploaded media",
                "GET  /account                — Balance + plan",
                "GET  /account/transactions   — Credit history",
            ],
        },
        "web_only": [
            "Virality Predictor, Supercomputer, Personal Clipper",
            "Kling LipSync Studio, Edit Image/Inpaint",
            "Upscale (Topaz)",
        ],
        "plugins": ["Photoshop", "DaVinci Resolve", "Premiere Pro", "After Effects"],
        "integrations": ["Claude MCP", "CLI: /opt/homebrew/bin/higgsfield", "Minecraft Mod"],
        "content": ["Original Series (Zephyr)", "Games (browser + MCP)", "Canvas", "Community"],
        "total_endpoints": 36,
    }
