#!/usr/bin/env python3
"""
CC_notebooklm_feed.py — Exports wiki knowledge to NotebookLM-readable format.
Redacts all sensitive data before writing.
"""
import os, sys, re, json
from datetime import datetime
from pathlib import Path

VAULT = os.path.expanduser("~/GHS-Vault")
WIKI = f"{VAULT}/Cloud Backups/claude-wiki"
OUTPUT = os.path.expanduser("~/GHS-Vault/notebooklm_feed.md")

# Sensitive scrub patterns
_SCRUB = [
    (r'sk-[A-Za-z0-9]{32,}', '[REDACTED]'),
    (r'hf_[A-Za-z0-9_]{20,}', '[REDACTED]'),
    (r'eyJ[A-Za-z0-9_\-\.]{40,}', '[REDACTED]'),
    (r'IGAASP[A-Za-z0-9]{100,}', '[REDACTED]'),
    (r'-----BEGIN (?:RSA |EC |DSA )?PRIVATE KEY-----[\s\S]+?-----END (?:RSA |EC |DSA )?PRIVATE KEY-----', '[REDACTED]'),
    (r'\+1[\s\-]?\d{3}[\s\-]?\d{3}[\s\-]?\d{4}', '[REDACTED]'),
    (r'(?:API[_-]?KEY|TOKEN|SECRET|PASSWORD)\s*[:=]\s*["\']?[A-Za-z0-9_\-]{12,}["\']?', 'CREDENTIAL=[REDACTED]'),
]

def redact(content):
    for pattern, replacement in _SCRUB:
        content = re.sub(pattern, replacement, content, flags=re.IGNORECASE)
    return content

# Key files that NotebookLM needs
KEY_FILES = [
    "index.md",
    "BOOTSTRAP.md",
    "PROJECT_KNOWLEDGE.md",
    "concepts/Contradictions.md",
    "concepts/Gold Health Systems.md",
    "concepts/REX Backend.md",
    "concepts/GOJ Operations.md",
    "concepts/Security Architecture.md",
    "concepts/Active Stack.md",
    "concepts/OCR Pipeline.md",
    "concepts/Data Architecture.md",
    "entities/Kato.md",
]

def main():
    print("=== NotebookLM Feed Builder ===")
    
    content = []
    content.append(f"# GHS Knowledge Base — NotebookLM Feed")
    content.append(f"\n> Generated: {datetime.now().strftime('%Y-%m-%d %H:%M UTC')}")
    content.append(f"> Source: Obsidian vault → Wiki export")
    content.append(f"> For: NotebookLM ingestion via Google Drive\n")
    content.append("---\n")
    
    files_found = 0
    for rel_path in KEY_FILES:
        full_path = os.path.join(WIKI, rel_path)
        if os.path.exists(full_path):
            content.append(f"\n## {rel_path}\n")
            with open(full_path, 'r') as f:
                file_content = f.read()
                # Limit size per file
                if len(file_content) > 50000:
                    file_content = file_content[:50000] + "\n\n[TRUNCATED — file too large]"
                content.append(file_content)
            content.append("\n---\n")
            files_found += 1
    
    # Also include Hermes Perpetual Memory
    pm = f"{VAULT}/Hermes Perpetual Memory.md"
    if os.path.exists(pm):
        content.append(f"\n## Hermes Perpetual Memory\n")
        with open(pm, 'r') as f:
            content.append(f.read()[:30000])
        content.append("\n---\n")
        files_found += 1
    
    # Write output (redacted)
    os.makedirs(os.path.dirname(OUTPUT), exist_ok=True)
    final = redact('\n'.join(content))
    with open(OUTPUT, 'w') as f:
        f.write(final)
    
    size_kb = os.path.getsize(OUTPUT) / 1024
    print(f"  Written: {OUTPUT} ({size_kb:.0f} KB)")
    print(f"  Files bundled: {files_found}")
    print(f"  Done ✅")
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
