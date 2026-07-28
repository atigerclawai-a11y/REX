#!/usr/bin/env python3
"""CC_bbg_reel.py — BBG vertical reel renderer.
Uses Elena (ElevenLabs) + FAL FLUX images + FFmpeg.
Output: 1080x1920 vertical MP4, 9-30 seconds, IG/TikTok ready.

Usage:
  python3 CC_bbg_reel.py --script "your hook text" --prompt "image prompt" --duration 12
  python3 CC_bbg_reel.py --preset bbg_welcome
"""
import argparse
import subprocess
import sys
from pathlib import Path

# OpenMontage venv has all deps
OM = Path.home() / "Desktop" / "OpenMontage"
sys.path.insert(0, str(OM))

from tools.graphics.flux_image import FluxImage
from tools.audio.elevenlabs_tts import ElevenLabsTTS

ELENA_VOICE = "pNInz6obpgDQGcFmaJgB"  # Elena
OUT_DIR = Path.home() / "Desktop" / "REX" / "bbg_reels"
OUT_DIR.mkdir(parents=True, exist_ok=True)

PRESETS = {
    "bbg_welcome": {
        "script": "Welcome to Boardwalk Beer Garden. Brooklyn's backyard. Cold beer, hot food, good people. Pull up a chair.",
        "prompt": "vertical 9:16 Brooklyn beer garden exterior golden hour, warm amber lights, wooden boardwalk tables, summer evening, cinematic social media reel vibe, vibrant colors",
        "duration": 9,
    },
    "bbg_cold_beer": {
        "script": "When the beer is this cold and the sun is this warm, you don't check your phone. You just stay.",
        "prompt": "vertical 9:16 extreme close-up of golden beer with thick frost on glass, condensation droplets, sunset orange bokeh, Brooklyn rooftop vibes, IG reel aesthetic",
        "duration": 9,
    },
    "bbg_weekend": {
        "script": "Saturdays at BBG hit different. Live music, the whole block is here, and the grill doesn't stop. You in?",
        "prompt": "vertical 9:16 lively outdoor beer garden Saturday night, string lights overhead, crowd silhouettes, neon signs, energy and motion, Brooklyn party vibe",
        "duration": 10,
    },
    "bbg_russian": {
        "script": "Это не просто бар. Это наш Бруклин. Здесь все свои. Заходи.",
        "prompt": "vertical 9:16 moody Brooklyn beer garden interior, vintage Russian signage detail, warm tungsten lights, intimate cozy atmosphere, nostalgic film grain",
        "duration": 9,
    },
}


def render_voice(text: str, out_path: Path) -> Path:
    tts = ElevenLabsTTS()
    r = tts.execute({"text": text, "voice_id": ELENA_VOICE})
    if not r.success:
        raise RuntimeError(f"ElevenLabs failed: {r.error}")
    src = Path(r.data["output"])
    # Convert to wav if needed (FFmpeg wants consistent format)
    wav_path = out_path.with_suffix(".wav")
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(src), "-ar", "44100", "-ac", "2", str(wav_path)],
        check=True, capture_output=True,
    )
    return wav_path


def render_image(prompt: str, out_path: Path) -> Path:
    img = FluxImage()
    r = img.execute({"prompt": prompt, "aspect_ratio": "portrait_16_9"})
    if not r.success:
        raise RuntimeError(f"FLUX failed: {r.error}")
    src = Path(r.data["output"])
    if src.suffix.lower() not in {".png", ".jpg", ".jpeg"}:
        # OM returned a url or relative path — handle both
        raise RuntimeError(f"Unexpected image output: {src}")
    return src


def get_duration(media_path: Path) -> float:
    out = subprocess.check_output(
        [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(media_path),
        ],
        text=True,
    ).strip()
    return float(out)


def compose_reel(image: Path, voice: Path, duration: float, out_path: Path) -> Path:
    """Ken-Burns-style vertical reel: 1080x1920, image pans slowly while voice plays."""
    # Use slow zoompan for motion
    vf = (
        "scale=2160:3840:force_original_aspect_ratio=increase,"
        "crop=1080:1920,"
        "zoompan=z='min(zoom+0.0008,1.15)':d=1:s=1080x1920:fps=30,"
        "format=yuv420p"
    )
    cmd = [
        "ffmpeg", "-y",
        "-loop", "1", "-i", str(image),
        "-i", str(voice),
        "-vf", vf,
        "-c:v", "libx264", "-preset", "medium", "-crf", "20",
        "-c:a", "aac", "-b:a", "128k",
        "-shortest",
        "-t", str(duration),
        "-movflags", "+faststart",
        str(out_path),
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    return out_path


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--script", help="Narration text (Elena voice)")
    p.add_argument("--prompt", help="FAL FLUX image prompt (9:16 vertical)")
    p.add_argument("--duration", type=float, default=10.0)
    p.add_argument("--preset", choices=list(PRESETS.keys()), help="Use a built-in preset")
    p.add_argument("--name", default=None, help="Output filename (without .mp4)")
    args = p.parse_args()

    if args.preset:
        cfg = PRESETS[args.preset]
        script = cfg["script"]
        prompt = cfg["prompt"]
        duration = float(cfg["duration"])
    else:
        if not args.script or not args.prompt:
            p.error("Provide --script + --prompt, or use --preset")
        script = args.script
        prompt = args.prompt
        duration = args.duration

    name = args.name or (args.preset or "custom_reel")
    out = OUT_DIR / f"{name}.mp4"
    print(f"[BBG Reel] → {out}")
    print(f"  Script: {script[:80]}...")

    print(f"[1/3] Rendering Elena voice...")
    voice = render_voice(script, out)
    actual_dur = get_duration(voice)
    print(f"      → {voice.name} ({actual_dur:.1f}s)")

    print(f"[2/3] Generating FAL FLUX image (9:16)...")
    image = render_image(prompt, out)
    print(f"      → {image}")

    print(f"[3/3] Composing vertical reel (1080x1920, {actual_dur:.1f}s)...")
    final = compose_reel(image, voice, actual_dur, out)
    sz = final.stat().st_size / 1024
    print(f"      → {final.name} ({sz:.0f} KB)")
    print(f"\n✅ {final}")


if __name__ == "__main__":
    main()