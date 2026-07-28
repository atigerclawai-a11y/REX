#!/usr/bin/env python3
"""CC_bbg_reel_v2.py — Real-video BBG reels (not slideshows).
Uses Veo 3.1 (FAL) for AI-generated vertical video + Elena voice.
Output: 1080x1920 vertical MP4, IG/TikTok ready.

Usage:
  python3 CC_bbg_reel_v2.py --preset bbg_welcome
  python3 CC_bbg_reel_v2.py --prompt "..." --script "..." --name my_reel
"""
import argparse
import shutil
import subprocess
import sys
from pathlib import Path

OM = Path.home() / "Desktop" / "OpenMontage"
sys.path.insert(0, str(OM))

from tools.video.veo_video import VeoVideo
from tools.audio.elevenlabs_tts import ElevenLabsTTS

ELENA_VOICE = "pNInz6obpgDQGcFmaJgB"
OUT_DIR = Path.home() / "Desktop" / "REX" / "bbg_reels"
OUT_DIR.mkdir(parents=True, exist_ok=True)
RAW_DIR = Path.home() / "Desktop" / "REX" / "bbg_reels_raw"
RAW_DIR.mkdir(parents=True, exist_ok=True)

PRESETS = {
    "bbg_welcome": {
        "script": "Welcome to Boardwalk Beer Garden. Brooklyn's backyard. Pull up a chair.",
        "video_prompt": "Cinematic vertical 9:16 video: A golden-hour Brooklyn beer garden entrance. String lights flicker on. Two friends walk through a wooden gate laughing. The camera pushes in slowly. Warm amber light, summer evening, golden hour. Social media reel vibe. People smiling, clinking beers.",
        "duration": 6,
    },
    "bbg_cheers": {
        "script": "Cold beer. Hot night. Zero phones. You in?",
        "video_prompt": "Vertical 9:16 extreme close-up slow-motion video: Two cold beer mugs clink together, golden liquid splashing in slow motion, sunset orange bokeh background, condensation dripping down the glass, cinematic social media aesthetic, dynamic motion, vibrant colors.",
        "duration": 6,
    },
    "bbg_grill": {
        "script": "The grill doesn't stop. Neither do we. Come hungry.",
        "video_prompt": "Vertical 9:16 dynamic video: A sizzling grill at a beer garden, chef flipping burgers with flames rising, smoke and sparks, camera pulls back to reveal the whole bustling outdoor kitchen, golden hour, vibrant energetic social media reel.",
        "duration": 6,
    },
    "bbg_band": {
        "script": "Live band. Cold drinks. Saturday's calling.",
        "video_prompt": "Vertical 9:16 high-energy video: A live band playing on a small beer garden stage, crowd dancing with raised hands, neon stage lights, fog machine haze, dynamic camera movement following the drummer's cymbal hits, vibrant party atmosphere, social media reel energy.",
        "duration": 7,
    },
    "bbg_friends": {
        "script": "Your group chat has been saying Tuesday for three weeks. Just come. We're here.",
        "video_prompt": "Vertical 9:16 dynamic video: A group of friends laughing at a long picnic table, raising beer glasses toward the camera, bright golden hour, warm smiles, casual summer clothes, energetic and joyful, social media reel aesthetic, Brooklyn beer garden vibes.",
        "duration": 6,
    },
    "bbg_pour": {
        "script": "When the bartender pours it right, you don't talk. You just nod.",
        "video_prompt": "Vertical 9:16 cinematic video: A perfect beer pour close-up, golden liquid cascading into a frosty mug, foam rising over the top, bartender hands steady, neon signs reflecting in the glass, satisfying slow motion, social media reel vibe.",
        "duration": 6,
    },
    "bbg_friday": {
        "script": "Friday hit different when your corner spot has string lights, a DJ, and a rooftop. See you tonight.",
        "video_prompt": "Vertical 9:16 cinematic video: Friday night at a rooftop beer garden, DJ deck in foreground with colorful lights, crowd dancing in the background, string lights overhead, city skyline silhouette, vibrant social media reel energy, dynamic camera movement.",
        "duration": 6,
    },
}


def render_video(prompt: str, duration: int, name: str) -> Path:
    """Veo 3.1 returns real AI video at 720x1280 with audio."""
    v = VeoVideo()
    r = v.execute({"prompt": prompt, "duration_seconds": duration, "aspect_ratio": "9:16"})
    if not r.success:
        raise RuntimeError(f"Veo failed: {r.error}")
    src = Path(r.data["output"])
    if not src.is_absolute():
        src = Path.cwd() / src
    if not src.exists():
        raise RuntimeError(f"Veo output not found: {src}")
    dst = RAW_DIR / f"{name}_veo_raw.mp4"
    shutil.move(str(src), str(dst))
    return dst


def render_voice(text: str, name: str) -> Path:
    """Elena voice narration."""
    t = ElevenLabsTTS()
    r = t.execute({"text": text, "voice_id": ELENA_VOICE})
    if not r.success:
        raise RuntimeError(f"ElevenLabs failed: {r.error}")
    src = Path(r.data["output"])
    if not src.is_absolute():
        src = Path.cwd() / src
    wav = RAW_DIR / f"{name}_elena.wav"
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(src), "-ar", "44100", "-ac", "2", str(wav)],
        check=True, capture_output=True,
    )
    return wav


def finalize(veo_video: Path, voice: Path, name: str, mix_voice: bool = True) -> Path:
    """Scale Veo 720x1280 -> 1080x1920, replace or mix audio, output IG-ready MP4."""
    out = OUT_DIR / f"{name}.mp4"
    vf = "scale=1080:1920:flags=lanczos,format=yuv420p"

    if mix_voice:
        # Mix Elena voice over Veo ambient audio, voice at 100%, ambient at 30%
        fc = (
            f"[0:v]{vf}[v];"
            "[0:a]volume=0.3[bg];"
            "[1:a]volume=1.0[fg];"
            "[bg][fg]amix=inputs=2:duration=first[aout]"
        )
        cmd = [
            "ffmpeg", "-y",
            "-i", str(veo_video),
            "-i", str(voice),
            "-filter_complex", fc,
            "-map", "[v]", "-map", "[aout]",
            "-c:v", "libx264", "-preset", "medium", "-crf", "20",
            "-c:a", "aac", "-b:a", "128k",
            "-shortest",
            "-movflags", "+faststart",
            str(out),
        ]
    else:
        # Replace audio entirely with Elena
        cmd = [
            "ffmpeg", "-y",
            "-i", str(veo_video),
            "-i", str(voice),
            "-vf", vf,
            "-map", "0:v", "-map", "1:a",
            "-c:v", "libx264", "-preset", "medium", "-crf", "20",
            "-c:a", "aac", "-b:a", "128k",
            "-shortest",
            "-movflags", "+faststart",
            str(out),
        ]
    subprocess.run(cmd, check=True, capture_output=True)
    return out


def get_dur(p: Path) -> float:
    out = subprocess.check_output(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(p)],
        text=True,
    ).strip()
    return float(out)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--script", help="Narration text (Elena)")
    p.add_argument("--prompt", help="Veo video prompt")
    p.add_argument("--duration", type=int, default=6)
    p.add_argument("--preset", choices=list(PRESETS.keys()))
    p.add_argument("--name", default=None)
    p.add_argument("--no-mix", action="store_true", help="Replace audio instead of mix")
    args = p.parse_args()

    if args.preset:
        cfg = PRESETS[args.preset]
        script = cfg["script"]
        prompt = cfg["video_prompt"]
        duration = int(cfg["duration"])
    else:
        if not args.script or not args.prompt:
            p.error("Provide --script + --prompt, or use --preset")
        script, prompt, duration = args.script, args.prompt, args.duration

    name = args.name or (args.preset or "custom_reel")
    out_path = OUT_DIR / f"{name}.mp4"
    print(f"[BBG Reel v2] → {out_path}")
    print(f"  Script: {script}")
    print(f"  Prompt: {prompt[:80]}...")

    print(f"[1/3] Generating Veo 3.1 video ({duration}s, 9:16)...")
    veo = render_video(prompt, duration, name)
    vd = get_dur(veo)
    print(f"      → {veo.name} ({vd:.1f}s)")

    print(f"[2/3] Rendering Elena narration...")
    voice = render_voice(script, name)
    print(f"      → {voice.name}")

    print(f"[3/3] Finalizing: 720x1280 → 1080x1920, mixing audio...")
    final = finalize(veo, voice, name, mix_voice=not args.no_mix)
    sz = final.stat().st_size / 1024
    fd = get_dur(final)
    print(f"      → {final.name} ({sz:.0f} KB, {fd:.1f}s)")
    print(f"\n✅ {final}")


if __name__ == "__main__":
    main()