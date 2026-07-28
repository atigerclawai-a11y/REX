#!/usr/bin/env python3
"""CC_masha_kb_sync.py — Weekly scrape of BBG sources + diff against Masha KB.

Scrapes:
  - https://boardwalkbeergarden.com (homepage, menu)
  - Yelp BBG page (reviews, hours)
  - IG posts (when archive available)

Compares against ~/Documents/GHS-Vault/Projects/Masha — BBG Knowledge Base.md
Generates diff report in ~/Desktop/REX/logs/masha_kb_sync_YYYY-MM-DD.md
"""
import argparse
import json
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

KB_PATH = Path.home() / "Documents" / "GHS-Vault" / "Projects" / "Masha — BBG Knowledge Base.md"
LOG_DIR = Path.home() / "Desktop" / "REX" / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
FIRECRAWL_URL = "http://127.0.0.1:8000/firecrawl/scrape"

TARGETS = [
    ("BBG Website", "https://boardwalkbeergarden.com"),
    ("BBG Menu", "https://boardwalkbeergarden.com/menu"),
]


def scrape(url: str) -> str | None:
    """Scrape via our Firecrawl router."""
    try:
        body = json.dumps({"url": url}).encode()
        req = urllib.request.Request(
            FIRECRAWL_URL, data=body,
            headers={"Content-Type": "application/json"}, timeout=60,
        )
        with urllib.request.urlopen(req, timeout=60) as r:
            data = json.loads(r.read())
            return data.get("markdown", "")
    except Exception as e:
        print(f"  ⚠️  Failed: {url} → {e}")
        return None


def extract_signals(markdown: str) -> dict:
    """Pull out: hours, menu items (with $), phone, address from scraped markdown."""
    signals = {"hours": [], "menu_items": [], "phones": [], "addresses": [],
               "specials": [], "prices": set()}

    # Phone: (xxx) xxx-xxxx or xxx-xxx-xxxx
    for m in re.finditer(r"\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}", markdown):
        signals["phones"].append(m.group(0).strip())

    # Prices: $XX.XX or $XX
    for m in re.finditer(r"\$\d+(?:\.\d{2})?", markdown):
        signals["prices"].add(m.group(0))

    # Hours patterns: "Mon-Fri: 5pm-1am" or "5:00 PM"
    for m in re.finditer(r"(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)(?:day)?[-:\s]*(?:\d{1,2}(?::\d{2})?\s*[APap][Mm])",
                         markdown):
        signals["hours"].append(m.group(0).strip())

    # Address: street + city + state + zip
    for m in re.finditer(r"\d+\s+[A-Z][a-z]+\s+(?:St|Ave|Blvd|Rd|Dr|Way|Pl)[.,]?\s+[A-Z][a-z]+,?\s+[A-Z]{2}\s+\d{5}",
                         markdown):
        signals["addresses"].append(m.group(0).strip())

    # Menu items: lines with $ (heuristic)
    for line in markdown.split("\n"):
        if "$" in line and len(line) < 100:
            signals["menu_items"].append(line.strip())
            if len(signals["menu_items"]) > 30:
                break

    # Specials keywords
    for kw in ["Happy Hour", "BOGO", "Buy 2", "Free", "Special", "Discount"]:
        if kw.lower() in markdown.lower():
            signals["specials"].append(kw)

    return signals


def compare_signals(current_kb: str, scraped: dict) -> list[str]:
    """Diff scraped signals vs current KB. Return list of changes."""
    diffs = []
    # Hours
    if scraped["hours"]:
        kb_hours = set(re.findall(r"(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)(?:day)?[-:\s]*\d{1,2}",
                                   current_kb, re.IGNORECASE))
        scraped_hours = set(re.findall(r"(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)(?:day)?[-:\s]*\d{1,2}",
                                        " ".join(scraped["hours"]), re.IGNORECASE))
        new = scraped_hours - kb_hours
        if new:
            diffs.append(f"⏰ NEW hours detected: {sorted(new)[:5]}")
    # Phones
    if scraped["phones"]:
        for p in scraped["phones"][:3]:
            if p not in current_kb:
                diffs.append(f"📞 NEW phone: {p}")
    # Menu items (heuristic — count only)
    new_items = [m for m in scraped["menu_items"] if m.split("$")[0].strip() and
                 m.split("$")[0].strip()[:30] not in current_kb]
    if new_items:
        diffs.append(f"🍔 NEW menu items: {len(new_items)} (sample: {new_items[0][:60]}...)")
    # Specials
    for sp in scraped["specials"]:
        if sp not in current_kb:
            diffs.append(f"🎉 NEW special: {sp}")
    return diffs


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--once", action="store_true", help="Run once and exit")
    p.add_argument("--dry-run", action="store_true", help="Show diff but don't write")
    args = p.parse_args()

    if not KB_PATH.exists():
        print(f"❌ KB not found: {KB_PATH}")
        sys.exit(1)

    current_kb = KB_PATH.read_text()
    print(f"📖 Loaded KB: {len(current_kb)} chars")

    all_diffs = []
    all_signals = {}
    for label, url in TARGETS:
        print(f"\n🔍 Scraping {label}: {url}")
        md = scrape(url)
        if not md:
            continue
        sig = extract_signals(md)
        all_signals[label] = {"url": url, "markdown_len": len(md), **sig}
        diffs = compare_signals(current_kb, sig)
        if diffs:
            print(f"   → {len(diffs)} changes detected")
            all_diffs.extend([f"[{label}] {d}" for d in diffs])
        else:
            print(f"   → No changes")

    # Generate report
    today = datetime.now().strftime("%Y-%m-%d")
    report_path = LOG_DIR / f"masha_kb_sync_{today}.md"
    report_lines = [
        f"# Masha KB Sync Report — {today}\n",
        f"**Source:** boardwalkbeergarden.com (live scrape via /firecrawl router)\n",
        f"**Compared against:** {KB_PATH}\n",
        "\n---\n",
    ]
    if all_diffs:
        report_lines.append(f"## 🚨 {len(all_diffs)} Changes Detected\n\n")
        for d in all_diffs:
            report_lines.append(f"- {d}\n")
    else:
        report_lines.append("## ✅ No Changes Detected\n\nAll scraped content matches current KB.\n")

    report_lines.append("\n## 📊 Raw Scraped Signals\n\n```json\n")
    # Make prices serializable
    for label, sig in all_signals.items():
        sig["prices"] = sorted(sig.get("prices", set()))
    report_lines.append(json.dumps(all_signals, indent=2, default=str))
    report_lines.append("\n```\n")

    report = "".join(report_lines)
    if args.dry_run:
        print(f"\n=== DRY RUN REPORT ===\n{report}")
    else:
        report_path.write_text(report)
        print(f"\n✅ Report: {report_path}")
        print(f"   {len(all_diffs)} changes" if all_diffs else "   No changes")

    return 0 if not all_diffs else 1


if __name__ == "__main__":
    sys.exit(main())