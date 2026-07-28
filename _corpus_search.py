#!/usr/bin/env python3
"""Quick search of the GOJ knowledge corpus."""
import json, sys, os

CORPUS = os.path.expanduser("~/Desktop/REX/knowledge/corpus.jsonl")
term = sys.argv[1].lower() if len(sys.argv) > 1 else "apc_fail"
hits = 0

with open(CORPUS) as f:
    for line in f:
        if term in line.lower():
            hits += 1
            rec = json.loads(line)
            idx = rec["text"].lower().find(term)
            snippet = rec["text"][max(0, idx-80):idx+200].replace("\n", " ")
            print(f"\n### {rec['path']}")
            print(f"…{snippet}…")
            if hits >= 5:
                break

print(f"\n--- {hits} matches for '{term}' (showing first 5) ---")
