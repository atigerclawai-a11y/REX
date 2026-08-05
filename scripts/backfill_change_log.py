#!/usr/bin/env python3
"""Force backfill: log ALL change messages (last 14 days) to local change_log.json."""
import json
import os
import sys
sys.path.insert(0, '/Users/mainsobhelper/Desktop/REX')
import CC_goj_change_log as ccl

rows = ccl.fetch_messages(14)
print(f'fetch_messages(14): {len(rows)} rows')

# classify each
LOCAL_LOG = ccl.HOME / "Desktop/REX/data/change_log.json"
local = []
if LOCAL_LOG.exists():
    local = json.load(open(LOCAL_LOG))
existing = {tuple(r[:7]) for r in local}

added = 0
for r in rows:
    typ, client, reason = ccl.parse_change(r["text"], r["sender"])
    group = ccl.resolve_group(r["group_name"]) or ""
    entry = [r["received_at"][:16], r["sender"], r["text"], client, typ, reason, group]
    if tuple(entry[:7]) not in existing:
        local.append(entry)
        existing.add(tuple(entry[:7]))
        added += 1

json.dump(local, open(LOCAL_LOG, "w"), ensure_ascii=False, indent=1)
print(f'local log now: {len(local)} entries ({added} new)')
# print the recent ones
print('\n=== RECENT CHANGES (last 8) ===')
for e in local[-8:]:
    print(f'  [{e[0]}] {e[1][:12]} | {e[3][:20]} | {e[4]} | {e[5][:50]}')
