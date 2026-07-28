#!/usr/bin/env python3
"""Intelligence harvest — books, movies, shows, art, literature.
Fetches Wikipedia summaries then distills key insights via Ollama.
Usage: python3 intel.py --book "The Bitcoin Standard"
       python3 intel.py --movie "Blade Runner"
       python3 intel.py --show "Breaking Bad"
       python3 intel.py --art "Guernica Pablo Picasso"
       python3 intel.py "any topic"
"""

import sys, os, json, re, requests

OLLAMA = "http://localhost:11434/api/chat"
MODEL = "mistral-hermie"
VAULT = os.path.expanduser("~/.hermes/rexxie_vault/intel")
WIKI_API = "https://en.wikipedia.org/w/api.php"
os.makedirs(VAULT, exist_ok=True)

HEADERS = {"User-Agent": "RexxieBot/1.0"}

PROMPTS = {
    "book": "Analyze this book. Structure your response as:\n1. **Core Thesis** (2-3 sentences)\n2. **Key Concepts** — use a mermaid mindmap or flowchart\n```mermaid\nmindmap\n  root((The Book))\n    ...\n```\n3. **Comparison Table** — how this book's ideas compare to mainstream views\n4. **Critical Reception**\n5. **3-5 Actionable Takeaways**\nBe visual. Use mermaid diagrams, comparison tables, and structured breakdowns wherever they clarify the analysis.",
    "movie": "Analyze this film. Structure as:\n1. **Synopsis** (2 sentences)\n2. **Thematic Map** — mermaid flowchart of themes and connections\n3. **Cinematography Breakdown** — table of visual techniques and their purpose\n4. **Cultural Impact Timeline** — mermaid timeline\n5. **Key Takeaways**\nBe visual. Diagram the themes and influences.",
    "show": "Analyze this TV show. Structure as:\n1. **Premise** (2 sentences)\n2. **Character Web** — mermaid graph showing relationships\n3. **Season Arc Overview** — timeline or table of major developments\n4. **Cultural Impact** \n5. **Why It Matters**\nBe visual. Map the characters and arcs.",
    "art": "Analyze this artwork. Structure as:\n1. **The Work** (1 sentence)\n2. **Artist Context** — mermaid timeline of the artist's career\n3. **Technique & Symbolism** — breakdown table\n4. **Art Historical Significance** — how it fits into movements, mermaid flowchart\n5. **Legacy & Influence**\nBe visual. Use timelines, technique tables, influence diagrams.",
    "general": "Summarize this topic. Structure as:\n1. **Overview** (2-3 sentences)\n2. **Key Facts** — comparison table if applicable\n3. **Timeline or Process** — mermaid diagram if there's a sequence\n4. **Connections** — how this relates to other concepts, mermaid flowchart\n5. **3-5 Takeaways**\nBe visual. Use mermaid diagrams, tables, and structured breakdowns.",
}

def fetch_wikipedia(title, category=None):
    """Fetch Wikipedia extract for any topic."""
    params = {
        "action": "query",
        "titles": title,
        "prop": "extracts|info",
        "exintro": 0,  # Full article, not just intro
        "explaintext": 1,
        "exchars": 8000,
        "format": "json",
        "inprop": "url",
    }
    try:
        r = requests.get(WIKI_API, params=params, headers=HEADERS, timeout=15)
        r.raise_for_status()
        data = r.json()
        pages = data.get("query", {}).get("pages", {})
        for pid, page in pages.items():
            if pid != "-1":
                return {
                    "title": page["title"],
                    "url": page.get("fullurl", f"https://en.wikipedia.org/wiki/{page['title'].replace(' ', '_')}"),
                    "text": page.get("extract", ""),
                }
        return {"title": title, "url": "", "text": "[Topic not found on Wikipedia]"}
    except Exception as e:
        return {"title": title, "url": "", "text": f"[ERROR: {e}]"}

def search_wikipedia(query):
    """Search Wikipedia for best match."""
    params = {
        "action": "opensearch",
        "search": query,
        "limit": 3,
        "format": "json",
    }
    try:
        r = requests.get(WIKI_API, params=params, headers=HEADERS, timeout=10)
        r.raise_for_status()
        results = r.json()
        if results[1]:
            return results[1][0]  # Best match title
        return query
    except Exception:
        return query

def summarize(text, prompt_type="general"):
    """Summarize via Ollama."""
    system_prompt = PROMPTS.get(prompt_type, PROMPTS["general"])
    
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": text[:12000]}
        ],
        "stream": False,
        "options": {"temperature": 0.4}
    }
    try:
        r = requests.post(OLLAMA, json=payload, timeout=120)
        return r.json()["message"]["content"]
    except Exception as e:
        return f"[Summarization failed: {e}]"

def save_to_vault(url, title, highlights, category):
    """Save to Rexxie intel vault."""
    safe_title = "".join(c for c in title if c.isalnum() or c in " -_")[:80]
    note_path = os.path.join(VAULT, f"{safe_title}.md")
    
    from datetime import datetime
    timestamp = datetime.now().isoformat()
    
    content = f"""---
title: "{title}"
url: {url}
category: {category}
imported: {timestamp}
tags: ["{category}", "summarized"]
---

# {title}

**Source:** [{title}]({url})

## Analysis

{highlights}
"""
    with open(note_path, 'w') as f:
        f.write(content)
    return note_path

if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help"):
        print(__doc__)
        sys.exit(1)
    
    category = "general"
    query = sys.argv[-1]
    
    # Detect type from flag
    type_map = {"--book": "book", "--movie": "movie", "--show": "show", "--art": "art"}
    for flag, cat in type_map.items():
        if flag in sys.argv:
            category = cat
            idx = sys.argv.index(flag)
            query = " ".join(sys.argv[idx+1:]) if idx+1 < len(sys.argv) else sys.argv[-1]
            break
    
    print(f"Category: {category} → {query}")
    
    # Search Wikipedia for best match
    title = search_wikipedia(f"{query} {category}")
    print(f"Wikipedia match: {title}")
    
    # Fetch article
    article = fetch_wikipedia(title)
    text = article["text"]
    
    if text.startswith("[ERROR"):
        print(text)
        sys.exit(1)
    
    if text.startswith("[Topic not found"):
        print(text)
        sys.exit(1)
    
    print(f"Fetched: {len(text)} chars from {title}")
    
    # Summarize
    highlights = summarize(text, category)
    path = save_to_vault(article["url"], title, highlights, category)
    
    print(f"\n{highlights}")
    print(f"\nSaved: {path}")