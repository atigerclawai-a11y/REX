#!/usr/bin/env python3
"""Web page + X/Twitter summarizer. Fetch URL → extract text → summarize via Ollama.
Usage: python3 web_summarize.py "https://example.com/article"
       python3 web_summarize.py --x "https://x.com/user/status/123"   (uses nitter.net)
"""

import sys, os, json, re, requests

OLLAMA = "http://localhost:11434/api/chat"
MODEL = "mistral-hermie"
VAULT = os.path.expanduser("~/.hermes/rexxie_vault/web-sources")
os.makedirs(VAULT, exist_ok=True)

def fetch_web(url):
    """Fetch and extract readable content from any web page."""
    headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}
    
    try:
        import trafilatura
        r = requests.get(url, headers=headers, timeout=15)
        r.raise_for_status()
        text = trafilatura.extract(r.text, include_links=False, include_images=False, include_tables=False)
        if text:
            return text[:10000]  # Cap at ~10k chars
        return f"[No readable content extracted from {url}]"
    except Exception as e:
        return f"[ERROR: {e}]"

def fetch_x_tweet(url):
    """Fetch a tweet via nitter.net (privacy-respecting Twitter frontend)."""
    tweet_id = url.split("status/")[-1].split("?")[0]
    nitter_url = f"https://nitter.net/i/status/{tweet_id}"
    headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}
    
    try:
        r = requests.get(nitter_url, headers=headers, timeout=15)
        if r.status_code == 200:
            # Extract tweet text from nitter HTML
            import trafilatura
            text = trafilatura.extract(r.text, include_links=False, include_images=False, include_tables=False)
            if text and len(text) > 50:
                return f"Tweet: {text[:3000]}"
        
        # Fallback: try direct Twitter (often blocked)
        r2 = requests.get(url, headers=headers, timeout=10)
        if r2.status_code == 200:
            match = re.search(r'<meta name="description" content="([^"]+)"', r2.text)
            if match:
                return f"Tweet: {match.group(1)[:2000]}"
        
        return f"[Could not fetch tweet: HTTP {r.status_code}]"
    except Exception as e:
        return f"[ERROR: {e}]"

def summarize(text):
    """Summarize via Ollama."""
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": "Summarize this content into 3-8 bullet points. Extract: key claims, data/evidence cited, surprising facts, and actionable takeaways. Be concise. Skip ads, nav, cookie banners, and boilerplate. Output plain markdown bullets."},
            {"role": "user", "content": text[:15000]}
        ],
        "stream": False,
        "options": {"temperature": 0.3}
    }
    try:
        r = requests.post(OLLAMA, json=payload, timeout=60)
        return r.json()["message"]["content"]
    except Exception as e:
        return f"[Summarization failed: {e}]"

def save_to_vault(url, title, text, highlights):
    """Save to Rexxie vault as markdown."""
    safe_title = "".join(c for c in title if c.isalnum() or c in " -_")[:80] or "untitled"
    note_path = os.path.join(VAULT, f"{safe_title}.md")
    
    from datetime import datetime
    timestamp = datetime.now().isoformat()
    
    content = f"""---
title: "{title}"
url: {url}
imported: {timestamp}
tags: ["web-source", "summarized"]
---

# {title}

**Source:** [{title}]({url})

## Highlights

{highlights}

---

## Full Text

{text}
"""
    with open(note_path, 'w') as f:
        f.write(content)
    return note_path

if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help"):
        print("Usage: web_summarize.py [--x] <URL>")
        sys.exit(1)
    
    is_x = sys.argv[1] == "--x"
    url = sys.argv[2] if is_x else sys.argv[1]
    
    print(f"Fetching: {url[:80]}...")
    
    if is_x or "x.com/" in url or "twitter.com/" in url:
        text = fetch_x_tweet(url)
        title = text.split("\n")[0][:80] if text else url.split("/")[-1]
    else:
        text = fetch_web(url)
        # Try to get title from URL or OG metadata
        title = url.split("/")[-1].split("?")[0][:80] or url[:80]
    
    if text.startswith("[ERROR"):
        print(text)
        sys.exit(1)
    
    print(f"Extracted: {len(text)} chars")
    highlights = summarize(text)
    path = save_to_vault(url, title, text, highlights)
    print(f"Saved: {path}")
    print(f"\n{highlights}")