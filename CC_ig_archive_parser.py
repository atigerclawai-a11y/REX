#!/usr/bin/env python3
"""CC_ig_archive_parser.py — Parse Instagram data export into reference library.

Usage:
  python3 CC_ig_archive_parser.py <path-to-instagram-zip>
  python3 CC_ig_archive_parser.py --watch   # polls ~/Downloads for new archive
"""
import argparse
import json
import re
import shutil
import sys
import zipfile
from pathlib import Path
from datetime import datetime

REF_DIR = Path.home() / "Desktop" / "REX" / "bbg_ig_reference"
RAW_DIR = REF_DIR / "raw_media"
INDEX_FILE = REF_DIR / "ig_index.json"
REF_DIR.mkdir(parents=True, exist_ok=True)
RAW_DIR.mkdir(parents=True, exist_ok=True)


def extract_archive(zip_path: Path) -> Path:
    """Extract IG archive into REF_DIR/<archive_name>/. Returns extracted root."""
    target = REF_DIR / zip_path.stem
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True)
    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(target)
    return target


def find_content_root(extracted: Path) -> Path | None:
    """IG archive layout: <root>/instagram_<username>_<date>/content/posts_1.json
    Returns the 'content' dir."""
    candidates = list(extracted.rglob("posts_1.json")) + list(extracted.rglob("posts_1.html"))
    if not candidates:
        # Try just 'content' subdir
        content_dirs = list(extracted.rglob("content"))
        if content_dirs:
            return content_dirs[0]
        return None
    return candidates[0].parent


def parse_posts_json(content_root: Path) -> list[dict]:
    """Parse posts_1.json (IG export format)."""
    posts_json = content_root / "posts_1.json"
    if not posts_json.exists():
        return []
    with open(posts_json) as f:
        data = json.load(f)
    posts = []
    for entry in data:
        # IG structure: media[] with media_type, uri, creation_timestamp, title
        media_list = entry.get("media", [])
        if not media_list:
            # Single-media posts sometimes have direct fields
            media_list = [entry]
        for m in media_list:
            uri = m.get("uri", "")
            ts = entry.get("creation_timestamp") or m.get("creation_timestamp")
            caption = entry.get("title", "") or m.get("title", "")
            media_type = m.get("media_type", "PHOTO")  # PHOTO, VIDEO, CAROUSEL
            posts.append({
                "media_type": media_type,
                "uri": uri,
                "timestamp": ts,
                "caption": caption,
                "filename": Path(uri).name if uri else "",
                "permalink": entry.get("permalink"),
                "location": (entry.get("location") or {}).get("name"),
            })
    return posts


def parse_posts_html(content_root: Path) -> list[dict]:
    """Parse posts_1.html (older export format). Extract caption + media paths."""
    posts_html = content_root / "posts_1.html"
    if not posts_html.exists():
        return []
    from html.parser import HTMLParser

    class PostParser(HTMLParser):
        def __init__(self):
            super().__init__()
            self.posts = []
            self.current_caption = []
            self.in_caption = False

        def handle_starttag(self, tag, attrs):
            if tag == "img" or tag == "video":
                # Media file references
                pass

        def handle_data(self, data):
            if data.strip():
                self.current_caption.append(data.strip())

    # Simpler: use BeautifulSoup if available, else regex
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        print("[warn] BeautifulSoup not installed — falling back to regex")
        BeautifulSoup = None

    html = posts_html.read_text(encoding="utf-8")
    if BeautifulSoup:
        soup = BeautifulSoup(html, "html.parser")
        # Posts are usually wrapped in <div class="post"> or similar
        posts = []
        # Generic: each "post" has a media file + caption text
        media_files = re.findall(r'/?(?:photos|videos)/[\w_./-]+\.(?:jpg|mp4)', html)
        captions = re.findall(r'<div class="[^"]*caption[^"]*"[^>]*>(.*?)</div>', html, re.DOTALL)
        for i, mf in enumerate(media_files):
            caption = captions[i] if i < len(captions) else ""
            posts.append({
                "media_type": "VIDEO" if mf.endswith(".mp4") else "PHOTO",
                "filename": Path(mf).name,
                "uri": mf,
                "caption": re.sub(r"<[^>]+>", "", caption).strip(),
            })
        return posts
    return []


def find_media_files(content_root: Path) -> dict[str, Path]:
    """Map filename -> full path within extracted archive."""
    photos_dir = content_root / "photos"
    videos_dir = content_root / "videos"
    mapping = {}
    for d in [photos_dir, videos_dir]:
        if d.exists():
            for f in d.rglob("*"):
                if f.is_file():
                    mapping[f.name] = f
    return mapping


def copy_media_to_raw(posts: list[dict], media_map: dict[str, Path]) -> list[dict]:
    """Copy media files into RAW_DIR, return enriched posts."""
    enriched = []
    for p in posts:
        fname = p["filename"]
        src = media_map.get(fname)
        if src and src.exists():
            dst = RAW_DIR / fname
            shutil.copy2(src, dst)
            p["local_path"] = str(dst)
            p["size_bytes"] = dst.stat().st_size
        enriched.append(p)
    return enriched


def summarize_for_reel_prompts(posts: list[dict]) -> dict:
    """Build a quick-reference summary for the BBG reel pipeline."""
    by_type = {"PHOTO": 0, "VIDEO": 0, "CAROUSEL": 0}
    captions = []
    for p in posts:
        t = p.get("media_type", "PHOTO")
        by_type[t] = by_type.get(t, 0) + 1
        if p.get("caption"):
            captions.append(p["caption"])
    return {
        "total_posts": len(posts),
        "by_media_type": by_type,
        "sample_captions": captions[:10],
        "all_captions_path": str(REF_DIR / "all_captions.txt"),
    }


def write_captions_file(posts: list[dict]):
    """Dump all captions for vibe/mood/keyword reference."""
    out = REF_DIR / "all_captions.txt"
    with open(out, "w") as f:
        for p in posts:
            ts = p.get("timestamp")
            ts_str = ""
            if ts:
                try:
                    if isinstance(ts, (int, float)):
                        ts_str = datetime.fromtimestamp(ts).isoformat()
                    else:
                        ts_str = str(ts)
                except Exception:
                    ts_str = str(ts)
            f.write(f"[{ts_str}] [{p['media_type']}] {p['caption']}\n\n")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("archive", nargs="?", help="Path to instagram archive .zip")
    p.add_argument("--watch", action="store_true", help="Watch ~/Downloads for new archives")
    args = p.parse_args()

    if args.watch:
        from watchdog.observers import Observer
        from watchdog.events import FileSystemEventHandler

        class ZipHandler(FileSystemEventHandler):
            def on_created(self, event):
                if event.src_path.endswith(".zip") and "instagram" in event.src_path.lower():
                    print(f"Detected: {event.src_path}")
                    process(Path(event.src_path))

        obs = Observer()
        obs.schedule(ZipHandler(), str(Path.home() / "Downloads"), recursive=False)
        obs.start()
        print(f"Watching ~/Downloads for instagram-*.zip ... Ctrl+C to stop.")
        try:
            import time
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            obs.stop()
        obs.join()
    elif args.archive:
        process(Path(args.archive))
    else:
        print("Usage: CC_ig_archive_parser.py <path-to-zip>  OR  --watch")
        sys.exit(1)


def process(zip_path: Path):
    print(f"[1/4] Extracting {zip_path.name}...")
    extracted = extract_archive(zip_path)
    print(f"      → {extracted}")

    print(f"[2/4] Locating content root...")
    content_root = find_content_root(extracted)
    if not content_root:
        print(f"      ✗ No content/posts_1.json or content/photos dir found")
        return
    print(f"      → {content_root}")

    print(f"[3/4] Parsing posts...")
    posts = parse_posts_json(content_root)
    if not posts:
        posts = parse_posts_html(content_root)
    print(f"      → {len(posts)} posts")

    print(f"[4/4] Copying media to {RAW_DIR}...")
    media_map = find_media_files(content_root)
    posts = copy_media_to_raw(posts, media_map)
    print(f"      → {len([p for p in posts if 'local_path' in p])} media files copied")

    summary = summarize_for_reel_prompts(posts)
    index = {
        "archive": zip_path.name,
        "extracted_at": datetime.now().isoformat(),
        "summary": summary,
        "posts": posts,
    }
    INDEX_FILE.write_text(json.dumps(index, indent=2, default=str))
    write_captions_file(posts)

    print(f"\n✅ Done. Index: {INDEX_FILE}")
    print(f"   Captions: {REF_DIR / 'all_captions.txt'}")
    print(f"   Media: {RAW_DIR}")
    print(f"\nSummary: {summary}")


if __name__ == "__main__":
    main()