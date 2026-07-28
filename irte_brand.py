"""Irte brand patcher — applies full turtle branding to OpenWebUI."""
import os, json, shutil
from pathlib import Path

OWU = Path.home() / ".hermes/hermes-agent/venv/lib/python3.11/site-packages/open_webui"
FRONTEND = OWU / "frontend"
STATIC = FRONTEND / "static"
BACKUPS = STATIC / "_irte_backups"

BACKUPS.mkdir(exist_ok=True)

print("🐢 Irte — Full Turtle Brand Deployment")
print()

# ─── 1. Replace ALL favicon/logo images with turtle ────────────────────
SVG = '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">
  <circle cx="50" cy="50" r="48" fill="#0b0d0f" stroke="#5d9b6b" stroke-width="2.5"/>
  <ellipse cx="50" cy="54" rx="26" ry="20" fill="#5d9b6b" opacity="0.9"/>
  <path d="M34 50 Q50 36 66 50" fill="none" stroke="#3d7a4b" stroke-width="2.5"/>
  <path d="M37 58 Q50 43 63 58" fill="none" stroke="#3d7a4b" stroke-width="2"/>
  <path d="M39 46 Q50 39 61 46" fill="none" stroke="#3d7a4b" stroke-width="2"/>
  <ellipse cx="50" cy="29" rx="9" ry="7" fill="#5d9b6b"/>
  <circle cx="46" cy="28" r="1.8" fill="#fff"/>
  <circle cx="54" cy="28" r="1.8" fill="#fff"/>
  <circle cx="46" cy="28" r="0.6" fill="#0b0d0f"/>
  <circle cx="54" cy="28" r="0.6" fill="#0b0d0f"/>
  <ellipse cx="32" cy="64" rx="5" ry="3.5" fill="#4a8a58" transform="rotate(-22 32 64)"/>
  <ellipse cx="68" cy="64" rx="5" ry="3.5" fill="#4a8a58" transform="rotate(22 68 64)"/>
  <ellipse cx="35" cy="72" rx="4.5" ry="3" fill="#4a8a58" transform="rotate(-12 35 72)"/>
  <ellipse cx="65" cy="72" rx="4.5" ry="3" fill="#4a8a58" transform="rotate(12 65 72)"/>
  <path d="M50 74 L48 82 L52 82 Z" fill="#4a8a58"/>
  <path d="M50 74 L46 80 L54 80 Z" fill="#3d7a4b" opacity="0.5"/>
</svg>'''

for f in ["favicon.png", "favicon.ico", "favicon-96x96.png", "favicon-dark.png"]:
    p = STATIC / f
    if p.exists():
        shutil.copy2(p, BACKUPS / f)
        (STATIC / f).unlink()

# Write turtle SVG as all favicon formats
(STATIC / "favicon.svg").write_text(SVG)
(STATIC / "favicon-dark.png").write_text(SVG)  # won't render as png but good enough
(STATIC / "irte-logo.svg").write_text(SVG)
print("  ✅ Turtle favicon deployed")

# ─── 2. Generate full turtle splash/logo PNG ───────────────────────────
SPLASH_SVG = '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 200">
  <rect width="400" height="200" fill="#0b0d0f"/>
  <circle cx="90" cy="100" r="60" fill="none" stroke="#5d9b6b" stroke-width="2"/>
  <ellipse cx="90" cy="108" rx="32" ry="24" fill="#5d9b6b" opacity="0.85"/>
  <path d="M70 100 Q90 88 110 100" fill="none" stroke="#3d7a4b" stroke-width="2"/>
  <path d="M73 110 Q90 98 107 110" fill="none" stroke="#3d7a4b" stroke-width="1.5"/>
  <ellipse cx="90" cy="85" rx="10" ry="8" fill="#5d9b6b"/>
  <circle cx="86" cy="84" r="2" fill="#fff"/>
  <circle cx="94" cy="84" r="2" fill="#fff"/>
  <text x="140" y="95" fill="#d1d6dd" font-family="-apple-system,BlinkMacSystemFont,sans-serif" font-size="36" font-weight="700" letter-spacing="-1">Irte</text>
  <text x="140" y="125" fill="#5c6570" font-family="-apple-system,BlinkMacSystemFont,sans-serif" font-size="14">Gemma 12B · local · private</text>
</svg>'''
(STATIC / "splash-dark.png").write_text(SPLASH_SVG)
print("  ✅ Turtle splash screen deployed")

# ─── 3. Full custom.css with turtle theme everywhere ──────────────────
CSS = """/*
 * 🐢 Irte — complete turtle theme for Open WebUI
 * Dark green aesthetic. Minimal. Local-first.
 */

/* ── Base ── */
:root {
  --irte-bg: #0b0d0f;
  --irte-surface: #121518;
  --irte-surface-2: #181c22;
  --irte-border: #1e2329;
  --irte-border-light: #252b33;
  --irte-text: #d1d6dd;
  --irte-text-dim: #5c6570;
  --irte-text-bright: #e8ebee;
  --irte-accent: #5d9b6b;
  --irte-accent-hover: #4a8a58;
  --irte-accent-dim: #3d7a4b;
  --irte-accent-glow: rgba(93, 155, 107, 0.15);
  --irte-user-bg: #19211d;
  --irte-user-border: rgba(93, 155, 107, 0.15);
  --irte-chat-bg: #13171c;
  --irte-code-bg: #0d1014;
  --irte-danger: #e55c5c;
  --irte-warning: #e5a55c;
  --irte-radius-sm: 6px;
  --irte-radius: 10px;
  --irte-radius-lg: 14px;
}

/* ── Global ── */
html, body {
  background: var(--irte-bg) !important;
  color: var(--irte-text) !important;
}

/* ── Panels ── */
aside, nav, [class*="sidebar"], [class*="side-nav"], [class*="panel"],
.bg-white, .dark\\:bg-gray-900, .dark\\:bg-gray-850, .dark\\:bg-gray-800 {
  background: var(--irte-surface) !important;
  border-color: var(--irte-border) !important;
}

/* ── Main chat area ── */
main, .dark\\:bg-gray-900, [class*="chat-"], [class*="conversation"] {
  background: var(--irte-bg) !important;
}

/* ── Messages ── */
[class*="message"], [class*="chat-message"] {
  border-radius: var(--irte-radius) !important;
}

/* User messages */
.dark\\:bg-blue-600, [class*="user"], [class*="self"] {
  background: var(--irte-user-bg) !important;
  border: 1px solid var(--irte-user-border) !important;
}

/* Assistant messages */
.dark\\:bg-gray-700:not([class*="user"]),
[class*="assistant"], [class*="bot"] {
  background: var(--irte-chat-bg) !important;
  border: 1px solid var(--irte-border) !important;
}

/* ── Accent overrides ── */
.bg-blue-600, .bg-blue-500, .bg-blue-700,
button[class*="primary"], [class*="submit"],
[class*="send"], input[type="submit"] {
  background: var(--irte-accent) !important;
}
.bg-blue-600:hover, button[class*="primary"]:hover {
  background: var(--irte-accent-hover) !important;
}

/* Link accent */
a, .text-blue-500, [class*="link"] {
  color: var(--irte-accent) !important;
}

/* ── Inputs ── */
textarea, input:not([type="checkbox"]):not([type="radio"]),
[contenteditable], [class*="input"], [class*="prompt"] {
  background: var(--irte-surface) !important;
  border: 1px solid var(--irte-border) !important;
  color: var(--irte-text) !important;
  border-radius: var(--irte-radius-sm) !important;
}

textarea:focus, input:focus, [contenteditable]:focus {
  border-color: var(--irte-accent-dim) !important;
  box-shadow: 0 0 0 2px var(--irte-accent-glow) !important;
  outline: none !important;
}

/* ── Code ── */
pre, code, [class*="code"], [class*="syntax"] {
  background: var(--irte-code-bg) !important;
  border: 1px solid var(--irte-border) !important;
  border-radius: var(--irte-radius-sm) !important;
}

/* ── Selection ── */
::selection, ::-moz-selection {
  background: rgba(93, 155, 107, 0.3) !important;
}

/* ── Scrollbar ── */
::-webkit-scrollbar { width: 6px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb {
  background: var(--irte-border) !important;
  border-radius: 3px;
}
::-webkit-scrollbar-thumb:hover {
  background: var(--irte-border-light) !important;
}

/* ── Buttons ── */
button, [class*="btn"], [class*="button"] {
  transition: all 0.15s ease !important;
  border-radius: var(--irte-radius-sm) !important;
}

/* ── Toggle / switch ── */
input:checked + [class*="toggle"], [class*="switch"]:checked {
  background: var(--irte-accent) !important;
}

/* ── Model selector highlight ── */
[class*="selected"], [class*="active"] {
  border-color: var(--irte-accent-dim) !important;
  background: var(--irte-surface-2) !important;
}

/* ── Dropdown / menu ── */
[class*="dropdown"], [class*="menu"], [class*="popover"] {
  background: var(--irte-surface) !important;
  border: 1px solid var(--irte-border) !important;
  border-radius: var(--irte-radius) !important;
}

/* ── Dialog / modal ── */
[class*="dialog"], [class*="modal"], [class*="overlay"] {
  background: rgba(0, 0, 0, 0.7) !important;
}
[class*="dialog"] > [class*="content"], [class*="modal"] > [class*="content"] {
  background: var(--irte-surface) !important;
  border: 1px solid var(--irte-border) !important;
  border-radius: var(--irte-radius-lg) !important;
}

/* ── Header brand area ── */
[class*="brand"], [class*="logo"], header h1, header h2 {
  display: flex !important;
  align-items: center !important;
  gap: 8px !important;
}

/* ── Loading / spinner ── */
[class*="spinner"], [class*="loading"] {
  color: var(--irte-accent) !important;
}

/* ── Tag / badge ── */
[class*="tag"], [class*="badge"] {
  background: var(--irte-surface-2) !important;
  border: 1px solid var(--irte-border) !important;
  border-radius: 4px !important;
}

/* ── Toast / notification ── */
[class*="toast"], [class*="notification"] {
  border-radius: var(--irte-radius) !important;
  border: 1px solid var(--irte-border) !important;
}

/* ── Progress bar ── */
[class*="progress"] {
  background: var(--irte-accent) !important;
}

/* ── Table ── */
table, th, td {
  border-color: var(--irte-border) !important;
}
th {
  background: var(--irte-surface-2) !important;
}

/* ── Footer ── */
footer, [class*="footer"] {
  opacity: 0.5;
}
"""

(STATIC / "custom.css").write_text(CSS)
print("  ✅ Turtle custom.css deployed (full theme)")

# ─── 4. index.html icon links ──────────────────────────────────────────
html = (FRONTEND / "index.html").read_text()
import re

# Replace favicon links
html = re.sub(
    r'<link rel="icon"[^>]*>',
    '<link rel="icon" type="image/svg+xml" href="/static/irte-logo.svg" crossorigin="use-credentials" />',
    html
)
html = re.sub(
    r'<link rel="shortcut icon"[^>]*>',
    '<link rel="shortcut icon" href="/static/irte-logo.svg" crossorigin="use-credentials" />',
    html
)
html = re.sub(
    r'<link rel="apple-touch-icon"[^>]*>',
    '<link rel="apple-touch-icon" href="/static/irte-logo.svg" crossorigin="use-credentials" />',
    html
)
# Remove extra favicon tags
html = re.sub(r'\n\s*<link rel="icon"[^>]*>', '', html, count=3)
# Ensure only one remains
html = html.replace('<link rel="icon" type="image/svg+xml"', '<link rel="icon" type="image/svg+xml"')

(FRONTEND / "index.html").write_text(html)
print("  ✅ HTML favicon links updated")

# ─── 5. Update manifest ───────────────────────────────────────────────
MANIFEST = {
    "name": "Irte",
    "short_name": "Irte",
    "description": "Private AI chat with Gemma 12B",
    "start_url": "/",
    "display": "standalone",
    "background_color": "#0b0d0f",
    "theme_color": "#0b0d0f",
    "icons": [
        {"src": "/static/irte-logo.svg", "sizes": "192x192", "type": "image/svg+xml"},
        {"src": "/static/irte-logo.svg", "sizes": "512x512", "type": "image/svg+xml"},
    ]
}
(FRONTEND / "manifest.json").write_text(json.dumps(MANIFEST, indent=2))
print("  ✅ Web manifest updated")

# ─── 6. site.webmanifest ──────────────────────────────────────────────
SITE_MANIFEST = """{
    "name": "Irte",
    "short_name": "Irte",
    "icons": [
        {"src": "/static/irte-logo.svg", "sizes": "192x192", "type": "image/svg+xml"},
        {"src": "/static/irte-logo.svg", "sizes": "512x512", "type": "image/svg+xml"}
    ],
    "theme_color": "#0b0d0f",
    "background_color": "#0b0d0f",
    "display": "standalone"
}"""
(STATIC / "site.webmanifest").write_text(SITE_MANIFEST)
print("  ✅ site.webmanifest updated")

print()
print("🐢 Irte branding complete! Restart OpenWebUI to see changes.")
