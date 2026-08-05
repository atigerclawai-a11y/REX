#!/usr/bin/env python3
"""
CC_pixel_report.py — Light visual report tool.
Renders web pages / PDFs to screenshot tiles with pixelshot (light, no torch),
then reads the tiles with a vision model (office Mac Ollama) and writes a
concise markdown report.

Usage:
  python3 CC_pixel_report.py <url-or-pdf> [more inputs...] [-o out.md]
  python3 CC_pixel_report.py https://example.com https://example.org/page2
  python3 CC_pixel_report.py ~/Documents/scan.pdf

Output: ./pixel_report.md (or -o path) + tiles kept in ./pixel_tiles/
"""
import argparse, base64, json, os, subprocess, sys, tempfile, urllib.request

PIXELSHOT = "/tmp/pixelrag-eval/.venv/bin/pixelshot"
VISION_URL = "http://100.99.86.60:11434/api/generate"
VISION_MODEL = "gemma4:e4b"   # light vision model on office Mac (golden rule: inference there)
TILE_DIR = os.path.expanduser("~/Desktop/pixel_tiles")
REPORT = "pixel_report.md"

def render(inputs, outdir):
    """Render each input to screenshot tiles via pixelshot (CDP backend)."""
    # fresh tiles per run — never reuse stale captures from earlier renders
    if os.path.isdir(outdir):
        subprocess.run(["rm", "-rf", outdir], check=False)
    os.makedirs(outdir, exist_ok=True)
    # tile-height 1024 keeps text readable for the vision model (full-page
    # screenshots compress into unreadable soup)
    cmd = [PIXELSHOT, "--tile-height", "1024"] + inputs + ["--output", outdir, "--cdp-url", "http://127.0.0.1:9333"]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    if r.returncode != 0:
        print("⚠️  pixelshot failed:", r.stderr[-400:])
        return {}
    # map input → list of tile paths
    result = {}
    for root, _, files in os.walk(outdir):
        tiles = sorted(f for f in files if f.endswith(".jpg"))
        if tiles:
            result[os.path.basename(root)] = [os.path.join(root, t) for t in tiles]
    return result

def ask_vision(tiles, input_label):
    """Send tiles to the vision model; return its summary text."""
    parts = []
    for t in tiles:
        with open(t, "rb") as f:
            b64 = base64.b64encode(f.read()).decode()
        parts.append({"type": "image", "image": b64})
    prompt = (
        f"This is a screenshot tile of: {input_label}\n"
        "Describe the key content in detail — headings, tables, numbers, layout, "
        "anything notable. Be thorough but factual. Then note anything unusual."
    )
    payload = json.dumps({
        "model": VISION_MODEL,
        "prompt": prompt,
        "images": [p["image"] for p in parts],
        "stream": False,
        "keep_alive": -1,
    }).encode()
    req = urllib.request.Request(VISION_URL, data=payload, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=180) as resp:
        return json.loads(resp.read()).get("response", "")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("inputs", nargs="+", help="URLs or PDF/file paths to render")
    ap.add_argument("-o", "--output", default=REPORT)
    args = ap.parse_args()

    rendered = render(args.inputs, TILE_DIR)
    if not rendered:
        print("❌ No tiles produced.")
        return 1

    sections = []
    for label, tiles in rendered.items():
        print(f"🔍 Reading {label} ({len(tiles)} tile(s))…")
        summary = ask_vision(tiles, label)
        sections.append(f"## {label}\n\n{summary}\n")

    with open(args.output, "w") as f:
        f.write(f"# Pixel Report — {len(rendered)} source(s)\n\n")
        f.write("\n".join(sections))
        f.write(f"\n---\n_Tiles: {TILE_DIR}_\n")
    print(f"\n✅ Report written: {args.output}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
