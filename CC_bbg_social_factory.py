#!/usr/bin/env python3
"""
CC_bbg_social_factory.py — BBG Social Media Content Factory
AI-powered daily reel pipeline: ideation → script → video + voiceover → publish.

Usage:
  python3 CC_bbg_social_factory.py                    # auto-select content for today
  python3 CC_bbg_social_factory.py --angle happy_hour  # force a content angle
  python3 CC_bbg_social_factory.py --dry-run           # preview without rendering/publishing
  python3 CC_bbg_social_factory.py --skip-video         # script + voice only (no Veo)
"""

import argparse
import json
import os
import random
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

# ── Paths ────────────────────────────────────────────────────────────────────
HERE = Path(__file__).resolve().parent
OM = Path.home() / "Desktop" / "OpenMontage"
OM_VENV_PY = OM / ".venv" / "bin" / "python3"
RENDERER = HERE / "CC_bbg_reel_v2.py"
ARCHIVE = HERE / "bbg_reels" / "archive"
OUT_DIR = HERE / "bbg_reels"
RAW_DIR = HERE / "bbg_reels_raw"
BUSINESS_MEMORY = HERE / "higgsfield_business_memory.json"

for d in [OUT_DIR, RAW_DIR, ARCHIVE]:
    d.mkdir(parents=True, exist_ok=True)

# ── Content Angles ───────────────────────────────────────────────────────────
# Each angle has: template scripts (with {placeholders}) + Veo prompt templates
# The cron agent fills in {placeholders} at runtime for daily variety.

CONTENT_ANGLES = {
    "happy_hour": {
        "label": "🍺 Happy Hour",
        "days": ["monday", "tuesday", "wednesday", "thursday"],
        "scripts": [
            "Buy 2, get 1 free. Because one round is never enough. {time_window} at Boardwalk Beer Garden. See you at the bar. 🍻",
            "Monday doesn't have to hurt. Not when there's buy-2-get-1 on drafts. {time_window}. You know where.",
            "Three beers. Two paid. One free. Zero reasons not to come. Happy hour is on — {time_window}.",
        ],
        "video_prompts": [
            "Vertical 9:16 cinematic video: A bartender pulling three perfect draft beers in a row, golden liquid filling frosted mugs, condensation dripping, neon beer signs glowing, warm amber bar lighting, slow motion, social media reel aesthetic, Brooklyn beer garden atmosphere.",
            "Vertical 9:16 dynamic video: Close-up of three cold beer mugs sliding across a polished wooden bar in slow motion, foam settling, golden light catching the glass, friends' hands reaching for them, laughter in the background, warm and inviting beer garden energy.",
        ],
    },
    "friday_night": {
        "label": "🎉 Friday Night",
        "days": ["friday"],
        "scripts": [
            "Friday hit different when your corner spot has string lights, a DJ, and cold beer. {time_window} tonight. Boardwalk Beer Garden.",
            "The work week is DONE. We've got 14 beers on tap, {screen} screen, and the best boardwalk vibes in Brooklyn. Tonight from {time_window}.",
            "Friday = Ladies Night. $5 cocktails all night. Plus our full dinner menu until 1 AM. Pull up. 🍸",
        ],
        "video_prompts": [
            "Vertical 9:16 high-energy cinematic video: Friday night at a Brooklyn beer garden, DJ deck with colorful lights pulsing, crowd dancing with raised hands, string lights overhead, bartenders shaking cocktails, spilled neon glow on the bar, vibrant party atmosphere, social media reel energy, dynamic camera movement.",
            "Vertical 9:16 cinematic video: A bartender crafting a colorful cocktail with flair, orange and red liquid cascading, garnish placed with precision, bokeh lights behind, Friday night energy, warm and electric atmosphere.",
        ],
    },
    "weekend_vibes": {
        "label": "🌊 Weekend Vibes",
        "days": ["saturday", "sunday"],
        "scripts": [
            "Weekend mode: ON. We open at noon. Cold beer, ocean breeze, and the best boardwalk in Brooklyn. {time_window}.",
            "Beach day → beer garden. The natural progression. We're open from {time_window} with 14 drafts, full menu, and that 150-inch screen.",
            "Saturday afternoon on the boardwalk. Cold drinks. Hot grill. Zero rush. Open {time_window} till 1 AM.",
        ],
        "video_prompts": [
            "Vertical 9:16 cinematic golden-hour video: A Brooklyn boardwalk beer garden on a sunny weekend afternoon, ocean sparkling in the background, people laughing at picnic tables with beer mugs, string lights swaying in the breeze, warm amber light, relaxed joyful atmosphere, social media reel aesthetic.",
            "Vertical 9:16 dynamic video: Beach-to-beer-garden transition — flip flops on the boardwalk, then cut to a frosty beer being poured, condensation dripping, friends clinking glasses, golden afternoon light, pure summer weekend energy.",
        ],
    },
    "food_feature": {
        "label": "🍽️ Food Feature",
        "days": ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"],
        "scripts": [
            "This {dish_name} hits different after a long week. {dish_description}. Served until 1 AM. You're welcome.",
            "People come for the beer. They stay for the {dish_name}. {price} of pure Brooklyn flavor. Open till 1 AM.",
            "The {dish_name} at Boardwalk Beer Garden. {dish_description} Come hungry.",
        ],
        "video_prompts": [
            "Vertical 9:16 cinematic food video: A steaming hot dish being placed on a wooden table at a beer garden, steam rising, golden bokeh lights behind, garnish glistening, fork cutting in slow motion revealing the perfect texture, mouthwatering food cinematography, social media reel aesthetic.",
            "Vertical 9:16 sizzling close-up video: A chef's hands presenting a beautiful plate, meat sizzling, sauce drizzling in slow motion, warm amber lighting, beer garden atmosphere in soft focus background, food-porn style cinematography.",
        ],
    },
    "sports_hype": {
        "label": "🏈 Fight Night / Game Day",
        "days": ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"],
        "scripts": [
            "UFC {event_number} on our 150-inch screen. Sound ON. No cover. 15 TVs. Wings and beer buckets all night. Be here.",
            "Game day = Beer Garden day. Every play on 15 4K screens + our massive 150-inch display. Cold beer. Hot wings. Let's go.",
            "The fight is THIS {day_of_week}. 150-inch screen. Sound CRANKED. 21+ only. Wings, sliders, beer buckets. Don't watch it on your phone.",
        ],
        "video_prompts": [
            "Vertical 9:16 intense cinematic video: A massive 150-inch screen at a sports bar showing electrifying fight highlights, crowd leaping to their feet with raised arms, beer splashing, neon lights flashing, pure adrenaline, cinematic slow motion, sports bar energy at its peak.",
            "Vertical 9:16 dynamic video: 15 TV screens all showing the same game, crowd roaring in unison, beer glasses raised, camera whip-pans across the bar capturing the electric atmosphere, sports bar heaven, cinematic energy.",
        ],
    },
    "atmosphere": {
        "label": "✨ Atmosphere / Vibe",
        "days": ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"],
        "scripts": [
            "Golden hour hits different on the boardwalk. String lights. Cold beer. Ocean breeze. This is your spot.",
            "Brooklyn's backyard. 14 drafts. Ocean views. 150-inch screen. Open {time_window}.",
            "Some places you go to drink. This place you go to feel something. Boardwalk Beer Garden. Brighton Beach.",
        ],
        "video_prompts": [
            "Vertical 9:16 atmospheric cinematic video: Golden hour at a Brooklyn boardwalk beer garden, string lights beginning to glow as the sun sets, ocean sparkling in the distance, couples and friends at picnic tables, warm amber light washing over everything, slow cinematic pan, dreamy and inviting.",
            "Vertical 9:16 magical atmospheric video: A Brooklyn beer garden at twilight, string lights fully illuminated against a purple-orange sky, candles flickering on tables, the 150-inch screen glowing in the background, people laughing warmly, pure magic hour energy.",
        ],
    },
    "promo": {
        "label": "🎯 Special Promo",
        "days": ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"],
        "scripts": [
            "Groups of 10+ get complimentary beer {day_range}. Book a table. Bring the crew. We'll take care of the first round.",
            "Ladies Night every Friday. $5 cocktails. All night. Dine-in only. Tag your girls. 👇",
            "Buy 2 get 1 FREE on drafts. {day_range} from {time_window}. No catch. Just good beer. 🍻",
        ],
        "video_prompts": [
            "Vertical 9:16 cinematic video: A long table of 10+ friends raising beer glasses in a toast, laughter, string lights above, golden liquid splashing, warm Brooklyn beer garden atmosphere, celebration energy, social media reel.",
            "Vertical 9:16 dynamic video: Close-up of three colorful cocktails being prepared simultaneously, bartender flair pouring, garnishes added, women laughing at the bar, Friday night energy, vibrant and fun.",
        ],
    },
}


# ── Content Selection ────────────────────────────────────────────────────────

def get_day_info():
    """Return today's day name, time window string, and content context."""
    now = datetime.now()
    day_name = now.strftime("%A").lower()
    hour = now.hour

    # Map to business hours context
    day_hours = {
        "monday": ("5 PM", "1 AM"),
        "tuesday": ("5 PM", "1 AM"),
        "wednesday": ("5 PM", "1 AM"),
        "thursday": ("5 PM", "1 AM"),
        "friday": ("5 PM", "1 AM"),
        "saturday": ("12 PM", "1 AM"),
        "sunday": ("12 PM", "1 AM"),
    }
    open_time, close_time = day_hours.get(day_name, ("5 PM", "1 AM"))

    # Determine time context
    if 5 <= hour < 12:
        time_context = "morning"
    elif 12 <= hour < 17:
        time_context = "afternoon"
    elif 17 <= hour < 21:
        time_context = "evening"
    else:
        time_context = "night"

    return {
        "day": day_name,
        "date": now.strftime("%Y-%m-%d"),
        "time_context": time_context,
        "hour": hour,
        "open_time": open_time,
        "close_time": close_time,
        "time_window": f"{open_time}–{close_time}",
        "is_weekend": day_name in ("saturday", "sunday"),
        "is_happy_hour_day": day_name in ("monday", "tuesday", "wednesday", "thursday"),
        "is_friday": day_name == "friday",
    }


def select_angle(day_info: dict, force: Optional[str] = None) -> dict:
    """Pick a content angle for today based on day/time/context."""
    if force and force in CONTENT_ANGLES:
        return {"name": force, **CONTENT_ANGLES[force]}

    day = day_info["day"]

    # Priority: special days first, then general
    if day_info["is_friday"]:
        candidates = ["friday_night", "weekend_vibes", "sports_hype", "atmosphere", "promo"]
    elif day_info["is_weekend"]:
        candidates = ["weekend_vibes", "food_feature", "sports_hype", "atmosphere"]
    elif day_info["is_happy_hour_day"]:
        candidates = ["happy_hour", "food_feature", "sports_hype", "atmosphere", "promo"]
    else:
        candidates = ["atmosphere", "food_feature", "promo"]

    # Filter to angles that match today
    matching = [c for c in candidates if day in CONTENT_ANGLES[c]["days"]]
    if not matching:
        matching = ["atmosphere"]

    angle_name = random.choice(matching)
    return {"name": angle_name, **CONTENT_ANGLES[angle_name]}


def fill_template(template: str, day_info: dict, angle_name: str) -> str:
    """Fill {placeholders} in a script template with real data."""
    # Business data
    dish_options = [
        ("Tomahawk Steak", "38oz of flame-grilled perfection. $86 of pure respect."),
        ("Solyanka", "The Slavic soup that cures everything. Smoky, tangy, loaded. $18."),
        ("Boardwalk Burger", "Double patty, smoked bacon, cheddar. The burger that built Brighton Beach."),
        ("Chicken Wings", "8 wings. Your choice: spicy, BBQ, or breaded. $15 of glory."),
        ("Rib Eye", "30oz with mashed potatoes and vegetables. $55. Come with backup."),
        ("Pulled Pork Sandwich", "Slow-smoked, house slaw, brioche. $23. You'll need extra napkins."),
        ("Pelmeni", "Boiled Siberian dumplings. Butter, dill, sour cream. $16 of comfort."),
        ("Mussels", "Red or white sauce. $17. Ocean-to-table on the boardwalk."),
        ("Shrimp Scampi", "Over fettuccine. Garlic, butter, white wine. $20."),
    ]
    dish = random.choice(dish_options)

    fills = {
        "time_window": day_info["time_window"],
        "day_of_week": day_info["day"].capitalize(),
        "dish_name": dish[0],
        "dish_description": dish[1],
        "price": "$",
        "screen": "150-inch",
        "event_number": str(random.choice([310, 311, 312])),
        "day_range": "Mon–Wed" if day_info["day"] in ("monday", "tuesday", "wednesday") else "Mon–Thu",
    }

    result = template
    for key, val in fills.items():
        result = result.replace("{" + key + "}", str(val))
    return result


# ── Video + Voiceover Pipeline ───────────────────────────────────────────────

def render_reel(script: str, video_prompt: str, name: str, duration: int = 6,
                skip_video: bool = False, voice_id: str = "pNInz6obpgDQGcFmaJgB") -> Optional[Path]:
    """Generate a reel using the existing renderer. Returns path to final MP4."""
    if skip_video:
        print("[SKIP] Video generation disabled (--skip-video)")
        return None

    if not OM_VENV_PY.exists():
        print(f"[ERROR] OpenMontage venv not found at {OM_VENV_PY}")
        print(f"  Install: cd ~/Desktop && git clone https://github.com/calesthio/OpenMontage.git")
        print(f"           cd OpenMontage && python3.14 -m venv .venv && .venv/bin/pip install -r requirements.txt")
        return None

    cmd = [
        str(OM_VENV_PY),
        str(RENDERER),
        "--script", script,
        "--prompt", video_prompt,
        "--duration", str(duration),
        "--name", name,
    ]

    print(f"[RENDER] {' '.join(cmd)}")
    try:
        result = subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=300)
        print(result.stdout)
        if result.stderr:
            print(f"[RENDER STDERR] {result.stderr[:500]}")

        # Extract output path from stdout
        for line in result.stdout.split("\n"):
            if "✅" in line:
                out_path = Path(line.split("✅")[-1].strip())
                if out_path.exists():
                    return out_path

        # Fallback: check expected output
        expected = OUT_DIR / f"{name}.mp4"
        if expected.exists():
            return expected

    except subprocess.CalledProcessError as e:
        print(f"[RENDER ERROR] Exit code {e.returncode}")
        print(f"  stdout: {e.stdout[:1000] if e.stdout else '(none)'}")
        print(f"  stderr: {e.stderr[:1000] if e.stderr else '(none)'}")
        return None
    except subprocess.TimeoutExpired:
        print("[RENDER ERROR] Timed out after 300s")
        return None

    return None


def render_reel_higgsfield(script: str, video_prompt: str, name: str, duration: int = 6,
                           voice_id: str = "pNInz6obpgDQGcFmaJgB") -> Optional[Path]:
    """Generate a reel using Higgsfield Seedance 2.0 + Elena voiceover + FFmpeg.
    This is the FALLBACK when FAL Veo is unavailable (balance exhausted)."""
    import urllib.request

    print("[HIGGSFIELD] Generating video via Seedance 2.0...")
    try:
        result = subprocess.run(
            ["higgsfield", "generate", "create", "seedance_2_0",
             "--prompt", video_prompt,
             "--duration", str(duration),
             "--aspect_ratio", "9:16",
             "--wait", "--json"],
            check=True, capture_output=True, text=True, timeout=300
        )
        import json
        jobs = json.loads(result.stdout)
        if not jobs or jobs[0]["status"] != "completed":
            print(f"[HIGGSFIELD ERROR] Job not completed: {result.stdout[:500]}")
            return None

        video_url = jobs[0]["result_url"]
        print(f"  Video URL: {video_url}")

        # Download
        raw_video = RAW_DIR / f"{name}_higgsfield_raw.mp4"
        urllib.request.urlretrieve(video_url, str(raw_video))
        print(f"  Downloaded: {raw_video} ({raw_video.stat().st_size / 1024:.0f} KB)")

        # Voiceover using OpenMontage ElevenLabs tool
        print("[HIGGSFIELD] Generating Elena voiceover...")
        import importlib.util
        import sys as _sys
        if str(OM) not in _sys.path:
            _sys.path.insert(0, str(OM))
        spec = importlib.util.spec_from_file_location("elevenlabs_tts", OM / "tools" / "audio" / "elevenlabs_tts.py")
        el_mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(el_mod)

        t = el_mod.ElevenLabsTTS()
        r = t.execute({"text": script, "voice_id": voice_id})
        if not r.success:
            print(f"  Voice error: {r.error}")
            return None

        voice_src = Path(r.data["output"])
        if not voice_src.is_absolute():
            voice_src = Path.cwd() / voice_src

        voice_wav = RAW_DIR / f"{name}_elena.wav"
        subprocess.run(["ffmpeg", "-y", "-i", str(voice_src), "-ar", "44100", "-ac", "2",
                        str(voice_wav)], check=True, capture_output=True)
        print(f"  Voice: {voice_wav}")

        # FFmpeg assemble
        print("[HIGGSFIELD] Assembling final reel...")
        out_path = OUT_DIR / f"{name}.mp4"
        vf = "scale=1080:1920:flags=lanczos,format=yuv420p"
        fc = (
            f"[0:v]{vf}[v];"
            "[0:a]volume=0.3[bg];"
            "[1:a]volume=1.0[fg];"
            "[bg][fg]amix=inputs=2:duration=first[aout]"
        )
        subprocess.run([
            "ffmpeg", "-y",
            "-i", str(raw_video),
            "-i", str(voice_wav),
            "-filter_complex", fc,
            "-map", "[v]", "-map", "[aout]",
            "-c:v", "libx264", "-preset", "medium", "-crf", "20",
            "-c:a", "aac", "-b:a", "128k",
            "-shortest",
            "-movflags", "+faststart",
            str(out_path),
        ], check=True, capture_output=True)

        dur = float(subprocess.check_output(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(out_path)],
            text=True).strip())
        sz = out_path.stat().st_size / 1024
        print(f"  ✅ {out_path} ({dur:.1f}s, {sz:.0f} KB)")
        return out_path

    except subprocess.CalledProcessError as e:
        print(f"[HIGGSFIELD ERROR] {e.stderr[:500] if e.stderr else str(e)}")
        return None
    except Exception as e:
        print(f"[HIGGSFIELD ERROR] {e}")
        return None


# ── Publishing ───────────────────────────────────────────────────────────────

def publish_instagram(video_path: Path, caption: str) -> bool:
    """Post to Instagram Reels via Meta Graph API. DORMANT — app token dead."""
    print("[IG] DORMANT — Meta app 1283301350582072 needs new token.")
    print(f"  Would post: {video_path.name}")
    print(f"  Caption: {caption[:80]}...")
    return False


def publish_facebook(video_path: Path, caption: str) -> bool:
    """Post to Facebook via Meta Graph API. DORMANT — same dead app."""
    print("[FB] DORMANT — same Meta app as IG. Fix the app first.")
    return False


def publish_tiktok(video_path: Path, caption: str) -> bool:
    """Post to TikTok. DORMANT — no API configured."""
    print("[TikTok] DORMANT — TikTok API not configured. Needs business account + access token.")
    return False


def publish_telegram(video_path: Path, caption: str) -> bool:
    """Deliver via Telegram. Returns MEDIA path for the agent to send."""
    print(f"[TG] Ready for Telegram delivery: MEDIA:{video_path}")
    print(f"  Caption: {caption}")
    return True  # Agent handles the actual send


def visual_qa(video_path: Optional[Path], name: str) -> bool:
    """PixelRAG visual QA — extract a frame from the rendered reel and read it
    with the office-Mac vision model. Catches brand violations (AI logo
    instead of real logo, mermaid lost in wide shot, clutter) BEFORE publish.

    Returns True if the frame passed QA, False on failure/unreadable.
    """
    if not video_path or not video_path.exists():
        print("[QA] No video — skipping visual QA")
        return False
    import base64, json as _json, subprocess as _sp, urllib.request as _ur
    frame = OUT_DIR / f"{name}_qa_frame.jpg"
    try:
        # extract middle frame at ~2s (or 40% in for short clips)
        _sp.run(
            ["ffmpeg", "-y", "-ss", "2", "-i", str(video_path),
             "-frames:v", "1", "-q:v", "3", str(frame)],
            capture_output=True, timeout=30,
        )
        if not frame.exists():
            print("[QA] Frame extraction failed — skipping")
            return False
        b64 = base64.b64encode(frame.read_bytes()).decode()
        payload = _json.dumps({
            "model": "gemma4:e4b",
            "prompt": (
                "This is a frame from a Boardwalk Beer Garden Instagram reel. "
                "Check brand compliance: (1) Is the real BBG logo/emblem visible "
                "(oval gold rope border, vintage BOARDWALK BEER GARDEN text)? "
                "(2) Is the mermaid mascot the dominant focal point? "
                "(3) Is the frame clean (dark background, no busy clutter)? "
                "Answer: PASS or FAIL, then one line why."
            ),
            "images": [b64],
            "stream": False,
            "keep_alive": -1,
        }).encode()
        req = _ur.Request(
            "http://100.99.86.60:11434/api/generate",
            data=payload, headers={"Content-Type": "application/json"},
        )
        with _ur.urlopen(req, timeout=90) as resp:
            verdict = _json.loads(resp.read()).get("response", "")
        print(f"[QA] Visual check: {verdict[:200]}")
        passed = "PASS" in verdict.upper() and "FAIL" not in verdict.upper()
        if passed:
            print("[QA] ✅ Brand-compliant — proceeding to publish")
        else:
            print("[QA] ⚠️  Brand violation flagged — consider re-rendering or manual review")
        return passed
    except Exception as e:
        print(f"[QA] Error ({type(e).__name__}) — skipping QA, proceeding")
        return False


def save_metadata(name: str, script: str, prompt: str, angle: str,
                  video_path: Optional[Path], day_info: dict):
    """Save production metadata for archive."""
    meta = {
        "name": name,
        "date": day_info["date"],
        "day": day_info["day"],
        "angle": angle,
        "script": script,
        "video_prompt": prompt,
        "video_path": str(video_path) if video_path else None,
        "rendered_at": datetime.now().isoformat(),
    }
    meta_path = ARCHIVE / f"{name}.json"
    meta_path.write_text(json.dumps(meta, indent=2))
    print(f"[ARCHIVE] Metadata saved → {meta_path}")


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    p = argparse.ArgumentParser(description="BBG Social Media Content Factory")
    p.add_argument("--angle", choices=list(CONTENT_ANGLES.keys()),
                   help="Force a specific content angle")
    p.add_argument("--dry-run", action="store_true",
                   help="Preview content without rendering or publishing")
    p.add_argument("--skip-video", action="store_true",
                   help="Skip Veo video generation (script + voice only)")
    p.add_argument("--duration", type=int, default=6,
                   help="Video duration in seconds (default: 6)")
    p.add_argument("--name", default=None,
                   help="Custom output name (default: auto-generated)")
    p.add_argument("--skip-qa", action="store_true",
                   help="Skip PixelRAG visual QA before publishing")
    p.add_argument("--force-publish", action="store_true",
                   help="Publish even if visual QA fails")
    args = p.parse_args()

    # 1. Content Ideation
    day_info = get_day_info()
    angle = select_angle(day_info, args.angle)

    script_template = random.choice(angle["scripts"])
    script = fill_template(script_template, day_info, angle["name"])
    video_prompt = random.choice(angle["video_prompts"])
    name = args.name or f"bbg_{angle['name']}_{day_info['date']}"

    print("=" * 60)
    print(f"  🎬 BBG SOCIAL CONTENT FACTORY")
    print(f"  📅 {day_info['date']} ({day_info['day'].capitalize()})")
    print(f"  🏷️  Angle: {angle['label']}")
    print(f"  📝 Script: {script}")
    print(f"  🎥 Prompt: {video_prompt[:100]}...")
    print(f"  📁 Output: {name}.mp4")
    print("=" * 60)

    if args.dry_run:
        print("\n[Dry run — stopping here. Use without --dry-run to render.]")
        return

    # 2. Generate Video + Voiceover
    video_path = render_reel(
        script=script,
        video_prompt=video_prompt,
        name=name,
        duration=args.duration,
        skip_video=args.skip_video,
    )

    # Fallback: try Higgsfield if Veo failed (FAL balance exhausted)
    if video_path is None and not args.skip_video:
        print("\n[FALLBACK] Veo failed — trying Higgsfield Seedance 2.0...")
        video_path = render_reel_higgsfield(
            script=script,
            video_prompt=video_prompt,
            name=name,
            duration=args.duration,
        )

    # 2b. PixelRAG visual QA — catch brand violations before they hit IG
    qa_passed = True
    if video_path and not args.skip_qa:
        print("\n── Visual QA (PixelRAG frame check) ──")
        qa_passed = visual_qa(video_path, name)
        if not qa_passed and not args.force_publish:
            print("[QA] ❌ FAIL — skipping publish. Re-run with --force-publish to override.")
            save_metadata(name, script, video_prompt, angle["name"], video_path, day_info)
            return

    # 3. Publish
    print("\n── Publishing ──")
    caption = f"{script}\n\n📍 3152 Brighton 6th St, Brooklyn\n🍺 #BoardwalkBeerGarden #BrooklynEats"

    if video_path:
        ig_ok = publish_instagram(video_path, caption)
        fb_ok = publish_facebook(video_path, caption)
        tt_ok = publish_tiktok(video_path, caption)
        tg_ok = publish_telegram(video_path, caption)
    else:
        print("[PUBLISH] No video rendered — skipping all publishing")
        ig_ok = fb_ok = tt_ok = tg_ok = False

    # 4. Archive
    save_metadata(name, script, video_prompt, angle["name"], video_path, day_info)

    # Summary
    print(f"\n── Factory Run Complete ──")
    print(f"  Content: {angle['label']}")
    print(f"  Script:  {script}")
    print(f"  Video:   {video_path.name if video_path else 'N/A'}")
    print(f"  IG:      {'🟢' if ig_ok else '🔴 DORMANT'}")
    print(f"  FB:      {'🟢' if fb_ok else '🔴 DORMANT'}")
    print(f"  TikTok:  {'🟢' if tt_ok else '🔴 DORMANT'}")
    print(f"  Telegram:{'🟢' if tg_ok else '🔴'}")

    # If video exists, print MEDIA path for agent delivery
    if video_path and video_path.exists():
        print(f"\n📹 MEDIA:{video_path}")

    return video_path


if __name__ == "__main__":
    main()
