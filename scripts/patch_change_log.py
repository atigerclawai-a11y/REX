#!/usr/bin/env python3
"""Fix CC_goj_change_log.py: SA cannot create/write Drive sheets (quota 0, no write
access). Patch main() to log locally to data/change_log.json AND attempt Drive best-effort.
Local log is the source of truth for WhatsApp changes."""
import re

p = '/Users/mainsobhelper/Desktop/REX/CC_goj_change_log.py'
s = open(p).read()

old = '''    svc = disc.build('drive', 'v3', credentials=get_creds(), cache_discovery=False)
    sheets = disc.build('sheets', 'v4', credentials=get_creds(), cache_discovery=False)
    sid = get_or_create_sheet(svc, sheets)

    # state: last synced message id
    state = {}
    if STATE_PATH.exists():
        state = json.load(open(STATE_PATH))
    last_id = state.get("last_id", 0)

    rows = fetch_messages(days)
    new_rows = []
    for r in rows:
        if r["id"] <= last_id:
            continue
        typ, client, reason = parse_change(r["text"], r["sender"])
        # only log schedule-relevant types
        if typ == "NOTE":
            # keep notes but mark them; keep everything for now
            pass
        group = resolve_group(r["group_name"]) or ""
        new_rows.append([
            r["received_at"][:16], r["sender"], r["text"],
            client, typ, reason, group,
        ])
        last_id = max(last_id, r["id"])

    if not new_rows:
        # silent — nothing to report (no_agent cron delivers only non-empty stdout)
        return

    # append (columns now include Group at G)
    sheets.spreadsheets().values().append(
        spreadsheetId=sid, range='A2:G',
        valueInputOption='RAW', insertDataOption='INSERT_ROWS',
        body={'values': new_rows}).execute()'''

new = '''    # state: last synced message id
    state = {}
    if STATE_PATH.exists():
        state = json.load(open(STATE_PATH))
    last_id = state.get("last_id", 0)

    rows = fetch_messages(days)
    new_rows = []
    for r in rows:
        if r["id"] <= last_id:
            continue
        typ, client, reason = parse_change(r["text"], r["sender"])
        group = resolve_group(r["group_name"]) or ""
        new_rows.append([
            r["received_at"][:16], r["sender"], r["text"],
            client, typ, reason, group,
        ])
        last_id = max(last_id, r["id"])

    if not new_rows:
        # silent — nothing to report (no_agent cron delivers only non-empty stdout)
        return

    # ── LOCAL LOG (source of truth, SA cannot write Drive) ──
    LOCAL_LOG = HOME / "Desktop/REX/data/change_log.json"
    local = []
    if LOCAL_LOG.exists():
        local = json.load(open(LOCAL_LOG))
    existing = {tuple(r[:7]) for r in local}
    added = [r for r in new_rows if tuple(r[:7]) not in existing]
    local.extend(added)
    json.dump(local, open(LOCAL_LOG, "w"), ensure_ascii=False, indent=1)
    state["last_id"] = last_id
    json.dump(state, open(STATE_PATH, "w"))

    # ── DRIVE best-effort (SA quota=0, may fail — local log still authoritative) ──
    try:
        svc = disc.build('drive', 'v3', credentials=get_creds(), cache_discovery=False)
        sheets = disc.build('sheets', 'v4', credentials=get_creds(), cache_discovery=False)
        sid = get_or_create_sheet(svc, sheets)
        sheets.spreadsheets().values().append(
            spreadsheetId=sid, range='A2:G',
            valueInputOption='RAW', insertDataOption='INSERT_ROWS',
            body={'values': added}).execute()
    except Exception as e:
        # Drive write failed (quota/permission) — local log still has the data
        pass

    print(f"📋 {len(added)} change(s) logged locally (Drive write: "
          f"{'OK' if 'sid' in dir() else 'skipped — SA cannot write'})")'''

if old in s:
    s = s.replace(old, new)
    open(p, 'w').write(s)
    print('PATCHED: local-log-first + Drive best-effort')
else:
    print('OLD BLOCK NOT FOUND — showing main() region')
    i = s.find('def main():')
    print(s[i:i+400])
