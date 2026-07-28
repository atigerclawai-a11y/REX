#!/usr/bin/env python3
"""YouTube → Vault pipeline. Pulls transcripts, creates searchable Obsidian notes.
Usage: python3 yt_vault.py URL1 URL2 URL3...
      python3 yt_vault.py --channel @ChannelName --max 20
      python3 yt_vault.py --file urls.txt
"""

import sys, os, re, json, subprocess
from datetime import datetime

VAULT = os.path.expanduser("~/.hermes/rexxie_vault/youtube")
os.makedirs(VAULT, exist_ok=True)

def get_transcript(url):
    """Pull transcript via youtube-transcript-api."""
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
        video_id = url.split("v=")[-1].split("&")[0] if "v=" in url else url.split("/")[-1]
        api = YouTubeTranscriptApi()
        t = api.fetch(video_id)
        segments = t.to_raw_data()
        return "\n".join(f"[{s['start']:.0f}s] {s['text']}" for s in segments if s.get('text'))
    except Exception as e:
        return f"[ERROR: {e}]"

def get_video_info(url):
    """Get title, channel, duration via yt-dlp (if installed) or fallback."""
    # Try yt-dlp first
    try:
        result = subprocess.run(
            ["yt-dlp", "--print", "%(title)s|||%(channel)s|||%(duration_string)s", "--skip-download", url],
            capture_output=True, text=True, timeout=20
        )
        if result.returncode == 0:
            parts = result.stdout.strip().split("|||")
            return {"title": parts[0], "channel": parts[1] if len(parts) > 1 else "Unknown", "duration": parts[2] if len(parts) > 2 else "Unknown"}
    except Exception:
        pass
    
    # Fallback: use the URL as title
    video_id = url.split("v=")[-1].split("&")[0] if "v=" in url else url.split("/")[-1]
    return {"title": video_id, "channel": "Unknown", "duration": "Unknown"}

def summarize(text, model="mistral-hermie"):
    """Summarize transcript via local Ollama — extract key points."""
    import requests
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "Extract the 5-10 most important points from this transcript. Format as bullet points with timestamps. Use mermaid diagrams for any processes, frameworks, or comparisons discussed. Include comparison tables for competing claims. Be concise — one sentence per point. Skip intros, sponsor reads, and outro. Output in markdown with visual elements where they add clarity."},
            {"role": "user", "content": text[:15000]}  # First ~1h of content
        ],
        "stream": False,
        "options": {"temperature": 0.3}
    }
    try:
        r = requests.post("http://localhost:11434/api/chat", json=payload, timeout=120)
        return r.json()["message"]["content"]
    except Exception as e:
        return f"[Summarization failed: {e}]"

def create_note(url, info, transcript, highlights=None):
    """Create a markdown note with frontmatter, highlights, and full transcript."""
    safe_title = re.sub(r'[<>:"/\\|?*]', '', info["title"])[:100]
    note_path = os.path.join(VAULT, f"{safe_title}.md")
    
    timestamp = datetime.now().isoformat()
    tags = ["youtube", info["channel"].lower().replace(" ", "-")]
    if highlights:
        tags.append("summarized")
    
    content = f"""---
title: "{info['title']}"
url: {url}
channel: {info['channel']}
duration: {info.get('duration', 'Unknown')}
imported: {timestamp}
tags: {json.dumps(tags)}
---

# {info['title']}

**Channel:** {info['channel']} | **Duration:** {info.get('duration', 'Unknown')}
**Source:** [{info['title']}]({url})

"""
    if highlights:
        content += f"## Highlights\n\n{highlights}\n\n---\n\n## Full Transcript\n\n{transcript}"
    else:
        content += f"## Transcript\n\n{transcript}"
    
    with open(note_path, 'w') as f:
        f.write(content)
    return note_path

def process_channel(channel_url, max_videos=20):
    """Pull all video URLs from a channel."""
    try:
        result = subprocess.run(
            ["yt-dlp", "--flat-playlist", "--print", "url", "--max-downloads", str(max_videos), channel_url],
            capture_output=True, text=True, timeout=30
        )
        urls = [u.strip() for u in result.stdout.split("\n") if u.startswith("http")]
        return urls
    except Exception as e:
        print(f"Channel scan failed: {e}")
        return []

if __name__ == "__main__":
    urls = []
    args = sys.argv[1:]
    
    if not args:
        print("Usage: yt_vault.py [URLs] OR --channel @Name OR --file urls.txt")
        sys.exit(1)
    
    i = 0
    summarize_flag = False
    while i < len(args):
        if args[i] == "--summarize":
            summarize_flag = True
            i += 1
        elif args[i] == "--channel" and i + 1 < len(args):
            limit = int(args[i+2]) if i+2 < len(args) and args[i+2].isdigit() else 20
            urls += process_channel(args[i+1], limit)
            i += 2 if not (i+2 < len(args) and args[i+2].isdigit()) else 3
        elif args[i] == "--file" and i + 1 < len(args):
            with open(os.path.expanduser(args[i+1])) as f:
                urls += [l.strip() for l in f if l.strip() and not l.startswith("#")]
            i += 2
        else:
            urls.append(args[i])
            i += 1
    
    processed = 0
    for url in urls:
        if not url.startswith("http"):
            continue
        print(f"Processing: {url[:80]}...")
        info = get_video_info(url)
        transcript = get_transcript(url)
        if transcript and not transcript.startswith("[ERROR"):
            highlights = summarize(transcript) if summarize_flag else None
            path = create_note(url, info, transcript, highlights)
            summary_tag = " (with highlights)" if highlights else ""
            print(f"  ✅ {len(transcript)} chars{summary_tag} → {path}")
            processed += 1
        else:
            print(f"  ❌ {transcript}")
    
    print(f"\nDone. {processed}/{len(urls)} videos imported to {VAULT}")
