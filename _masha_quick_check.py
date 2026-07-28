#!/usr/bin/env python3
"""Quick check: find new reservation emails since last run."""
import imaplib, ssl, json, os, re
from datetime import datetime, timezone

REX_DIR = "/Users/mainsobhelper/Desktop/REX"
STATE_PATH = os.path.join(REX_DIR, "_masha_state.json")

last_uid = None
if os.path.exists(STATE_PATH):
    with open(STATE_PATH) as f:
        state = json.load(f)
        last_uid = state.get("last_uid")
print(f"LAST_UID={last_uid}")

ctx = ssl.create_default_context()
mail = imaplib.IMAP4_SSL("imap.gmail.com", 993, ssl_context=ctx, timeout=30)
mail.login("atigerclawai@gmail.com", "uxemapqvhkndgmsv")
mail.select("INBOX", readonly=True)

all_new_res = []

if last_uid:
    status, msgs = mail.uid('search', None, f'UID {int(last_uid)+1}:*')
    if msgs[0]:
        new_uids = set(msgs[0].split())
        status, res_msgs = mail.search(None, 'SUBJECT "Reservations"')
        res_uids = set(res_msgs[0].split()) if res_msgs[0] else set()
        new_res = new_uids & res_uids
        all_new_res = sorted(new_res, key=int)
        print(f"NEW_RES_UIDS={[u.decode() for u in all_new_res]}")
else:
    status, res_msgs = mail.search(None, 'SUBJECT "Reservations"')
    all_ids = res_msgs[0].split() if res_msgs[0] else []
    all_new_res = all_ids[-3:]
    print(f"NO_STATE_CHECKING={[u.decode() for u in all_new_res]}")

mail.logout()

if not all_new_res:
    print("NO_NEW_RESERVATIONS")
else:
    max_uid = max(int(u) for u in all_new_res)
    with open(STATE_PATH, "w") as f:
        json.dump({"last_uid": max_uid, "last_run": datetime.now(timezone.utc).isoformat()}, f)
    print(f"HAS_NEW_COUNT={len(all_new_res)}")
    print(f"STATE_SAVED={max_uid}")
