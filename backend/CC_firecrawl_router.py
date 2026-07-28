"""CC_firecrawl_router.py — Lightweight scraper router.
Uses Python urllib + html.parser (no Docker dep). Acts as Firecrawl proxy when self-hosted,
or as standalone scraper when Firecrawl isn't running.

Endpoints:
  POST /firecrawl/scrape  {url} -> markdown content
  POST /firecrawl/crawl   {url, max_pages} -> list of page URLs (sitemap)
  GET  /firecrawl/health  -> {status, mode}
"""
import json
import logging
import re
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

logger = logging.getLogger("firecrawl_router")
router = APIRouter(prefix="/firecrawl", tags=["Firecrawl"])

USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
FIRECRAWL_LOCAL = "http://127.0.0.1:3003"
REQUEST_TIMEOUT = 30


class ScrapeRequest(BaseModel):
    url: str
    formats: list = ["markdown"]


class CrawlRequest(BaseModel):
    url: str
    max_pages: int = 10


class MarkdownConverter(HTMLParser):
    """HTML → Markdown converter (basic, no dependencies)."""
    SKIP_TAGS = {"script", "style", "nav", "header", "footer", "aside", "form", "iframe", "noscript"}
    BLOCK_TAGS = {"p", "div", "section", "article", "main", "header", "footer", "li", "tr",
                  "h1", "h2", "h3", "h4", "h5", "h6", "br", "hr", "blockquote"}
    HEADING_TAGS = {"h1": "# ", "h2": "## ", "h3": "### ", "h4": "#### ", "h5": "##### ", "h6": "###### "}

    def __init__(self):
        super().__init__()
        self.parts = []
        self.skip_depth = 0
        self.in_heading = None
        self.link_href = None

    def handle_starttag(self, tag, attrs):
        attrs_d = dict(attrs)
        if tag in self.SKIP_TAGS:
            self.skip_depth += 1
            return
        if tag == "br":
            self.parts.append("\n")
            return
        if tag == "hr":
            self.parts.append("\n---\n")
            return
        if tag in self.HEADING_TAGS:
            self.in_heading = tag
            self.parts.append("\n\n" + self.HEADING_TAGS[tag])
            return
        if tag == "a":
            self.link_href = attrs_d.get("href", "")
        if tag in self.BLOCK_TAGS and self.parts and not self.parts[-1].endswith("\n\n"):
            self.parts.append("\n")
        if tag == "li":
            self.parts.append("\n- ")
        if tag == "strong" or tag == "b":
            self.parts.append("**")

    def handle_endtag(self, tag):
        if tag in self.SKIP_TAGS:
            self.skip_depth = max(0, self.skip_depth - 1)
            return
        if tag in self.HEADING_TAGS:
            self.in_heading = None
            self.parts.append("\n")
            return
        if tag == "a" and self.link_href:
            href = self.link_href
            self.link_href = None
            self.parts.append(f"]({href})")
        if tag == "strong" or tag == "b":
            self.parts.append("**")
        if tag in self.BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data):
        if self.skip_depth > 0:
            return
        text = data.strip()
        if text:
            if self.link_href is not None:
                self.parts.append(f"[{text}")
            else:
                self.parts.append(text + " ")

    def get_markdown(self):
        result = "".join(self.parts)
        # Collapse multiple blank lines
        result = re.sub(r"\n{3,}", "\n\n", result)
        return result.strip()


def fetch_url(url: str, timeout: int = REQUEST_TIMEOUT) -> str:
    """Fetch URL with proper headers."""
    req = urllib.request.Request(url, headers={
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml",
    })
    with urllib.request.urlopen(req, timeout=timeout) as r:
        ct = r.headers.get("content-type", "")
        if "html" not in ct.lower() and "xml" not in ct.lower():
            return r.read().decode("utf-8", errors="replace")
        return r.read().decode("utf-8", errors="replace")


def html_to_markdown(html: str) -> str:
    """Convert HTML to Markdown using our simple parser."""
    parser = MarkdownConverter()
    parser.feed(html)
    return parser.get_markdown()


@router.get("/health")
def health():
    """Check Firecrawl availability."""
    fc_status = "down"
    try:
        req = urllib.request.Request(f"{FIRECRAWL_LOCAL}/health", timeout=2)
        with urllib.request.urlopen(req, timeout=2) as r:
            if r.status == 200:
                fc_status = "up"
    except Exception:
        pass
    return {
        "status": "ok",
        "mode": "firecrawl_proxy" if fc_status == "up" else "standalone",
        "firecrawl_local": fc_status,
    }


@router.post("/scrape")
def scrape(req: ScrapeRequest):
    """Scrape single URL → markdown.
    Tries Firecrawl first if up, falls back to built-in scraper."""
    if not req.url.startswith("http"):
        raise HTTPException(400, "URL must start with http:// or https://")

    # Try Firecrawl local first
    try:
        body = json.dumps({"url": req.url, "formats": req.formats}).encode()
        r = urllib.request.Request(
            f"{FIRECRAWL_LOCAL}/v1/scrape",
            data=body,
            headers={"Content-Type": "application/json", "Authorization": "Bearer fc-local"},
            timeout=REQUEST_TIMEOUT,
        )
        with urllib.request.urlopen(r, timeout=REQUEST_TIMEOUT) as resp:
            data = json.loads(resp.read())
            return {"ok": True, "url": req.url, "mode": "firecrawl", "data": data}
    except Exception as e:
        logger.info(f"Firecrawl local down ({e}), using built-in scraper")

    # Fallback: built-in scraper
    try:
        html = fetch_url(req.url)
    except urllib.error.HTTPError as e:
        raise HTTPException(e.code, f"HTTP {e.code} fetching {req.url}")
    except Exception as e:
        raise HTTPException(502, f"Failed to fetch: {e}")

    md = html_to_markdown(html)
    # Extract title
    title_match = re.search(r"<title>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
    title = title_match.group(1).strip() if title_match else ""
    # Extract meta description
    desc_match = re.search(r'<meta[^>]+name=["\']description["\'][^>]+content=["\'](.*?)["\']',
                            html, re.IGNORECASE)
    description = desc_match.group(1).strip() if desc_match else ""

    return {
        "ok": True,
        "url": req.url,
        "mode": "standalone",
        "markdown": md,
        "metadata": {"title": title, "description": description},
    }


@router.post("/crawl")
def crawl(req: CrawlRequest):
    """Crawl site — find pages and scrape each. Lightweight, single-threaded."""
    if not req.url.startswith("http"):
        raise HTTPException(400, "URL must start with http:// or https://")

    try:
        html = fetch_url(req.url)
    except Exception as e:
        raise HTTPException(502, f"Failed to fetch: {e}")

    # Find internal links
    base_domain = urllib.parse.urlparse(req.url).netloc
    links = set()
    for m in re.finditer(r'<a[^>]+href=["\']([^"\']+)["\']', html, re.IGNORECASE):
        href = m.group(1)
        if href.startswith("#") or href.startswith("javascript:"):
            continue
        # Resolve relative URLs
        full = urllib.parse.urljoin(req.url, href)
        parsed = urllib.parse.urlparse(full)
        if parsed.netloc == base_domain and parsed.scheme in ("http", "https"):
            # Strip fragments
            clean = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
            if parsed.query:
                clean += "?" + parsed.query
            links.add(clean)

    pages = [{"url": req.url, "markdown": html_to_markdown(html)}]
    for link in list(links)[:req.max_pages]:
        try:
            page_html = fetch_url(link)
            pages.append({"url": link, "markdown": html_to_markdown(page_html)})
        except Exception as e:
            pages.append({"url": link, "error": str(e)})

    return {"ok": True, "pages_crawled": len(pages), "pages": pages}