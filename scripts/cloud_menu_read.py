#!/usr/bin/env python3
"""Cloud vision menu reader — SELECTIVE ESCALATION for cost control.
Only reads pages surya flagged (contract violation / low confidence / category confusion).
Model ladder: haiku first, sonnet only if haiku output fails validation.
Anthropic key read from hermes config at runtime (never printed).

REBUILT 2026-08-03 from Blue #191 recovered strings (original deleted 05:01 wipe).
"""
import base64
import json
import re
import subprocess
from pathlib import Path

REX = Path('/Users/mainsobhelper/Desktop/REX')
CATALOG_PATH = REX / 'scripts/week30_dishes.json'
CONFIG = Path('/Users/mainsobhelper/.hermes/profiles/work/config.yaml')

MODEL_HAIKU = 'claude-haiku-4-5-20251001'
MODEL_SONNET = 'claude-sonnet-4-5-20250929'

PROMPT = """This is a Russian menu order form from a senior day care. Read it carefully.
The form has a name line (Имя:), day columns (ПН ВТ СР ЧТ ПТ), and sections with dish rows.
Each dish row has one checkbox per day. Find ALL checked boxes.

Return ONLY JSON:
{"name": "<client name as printed>",
 "picks": {"ПН": {"САЛАТЫ": "<dish or null>", "СУПЫ": "...", "ГЛАВНОЕ": "...", "ГАРНИР": "..."},
           "ВТ": {...}, "СР": {...}, "ЧТ": {...}, "ПТ": {...}}}
Rules: a dish appears ONLY if its checkbox is visibly marked; null otherwise.
If a category/day has TWO marks, return them as "dish1 + dish2" (flag ambiguity, do not choose).
Valid dishes: """


def _api_key():
    try:
        text = CONFIG.read_text()
        m = re.search(r'anthropic:\s*\n\s*api_key:\s*(\S+)', text)
        if m:
            return m.group(1)
        m = re.search(r'api_key:\s*(\S+)', text)
        return m.group(1) if m else None
    except Exception:
        return None


def _valid_dishes():
    try:
        cat = json.loads(CATALOG_PATH.read_text())
        dishes = []
        for lst in cat.values():
            dishes.extend(lst)
        return ', '.join(dishes)
    except Exception:
        return ''


def read_page_with_cloud(png_path, model=None):
    """Read ONE form page via Anthropic vision. Returns parsed {name, picks} or None."""
    key = _api_key()
    if not key:
        return None
    b64 = base64.b64encode(Path(png_path).read_bytes()).decode()
    model = model or MODEL_HAIKU
    payload = {
        'model': model,
        'max_tokens': 1024,
        'messages': [{
            'role': 'user',
            'content': [
                {'type': 'text', 'text': PROMPT + _valid_dishes()},
                {'type': 'image', 'source': {'type': 'base64', 'media_type': 'image/png', 'data': b64}},
            ],
        }],
    }
    try:
        proc = subprocess.run(
            ['curl', '-s', 'https://api.anthropic.com/v1/messages',
             '-H', 'x-api-key: ' + key,
             '-H', 'anthropic-version: 2023-06-01',
             '-H', 'content-type: application/json',
             '-d', json.dumps(payload)],
            capture_output=True, text=True, timeout=120)
        resp = json.loads(proc.stdout)
        text = resp['content'][0]['text']
        m = re.search(r'\{.*\}', text, re.S)
        if not m:
            return None
        parsed = json.loads(m.group(0))
        # validate has name + picks
        if parsed.get('name') and isinstance(parsed.get('picks'), dict):
            return parsed
        return None
    except Exception:
        return None


def read_form_pages(p1_path, p2_path):
    """Read both pages; haiku first, sonnet fallback on validation failure."""
    for model in (MODEL_HAIKU, MODEL_SONNET):
        for page in (p1_path, p2_path):
            res = read_page_with_cloud(page, model)
            if res:
                return res
    return None


if __name__ == '__main__':
    import sys
    if len(sys.argv) < 3:
        sys.exit('usage: cloud_menu_read.py <p1> <p2>')
    print(json.dumps(read_form_pages(sys.argv[1], sys.argv[2]), ensure_ascii=False))
