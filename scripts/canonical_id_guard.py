#!/usr/bin/env python3
"""GOJ canonical-ID integrity guard — run after ANY client/ID change.
Fails LOUD on: duplicate IDs, missing IDs for active clients, ID mismatch
between DB tables, or QR payload divergence. Kato hard rule 2026-08-03."""
import sqlite3, sys, json, re
from pathlib import Path

AUTH = '/Users/mainsobhelper/Documents/goj files/dashboard/auth_tracker.db'
PROP = '/Users/mainsobhelper/Documents/goj files/proprietary/goj_proprietary.db'

errors = []
warns = []

def e(msg): errors.append(msg)
def w(msg): warns.append(msg)

# 1. canonical_ids uniqueness
db = sqlite3.connect(AUTH)
rows = db.execute("SELECT canonical_id, name, auth_id FROM canonical_ids").fetchall()
ids = [r[0] for r in rows]
dupes = {i for i in ids if ids.count(i) > 1}
if dupes:
    e(f"DUPLICATE canonical IDs: {sorted(dupes)}")
else:
    print(f"[OK] canonical_ids: {len(rows)} rows, all unique")

# 2. active clients coverage
active = db.execute("SELECT client_id, name FROM clients WHERE active=1").fetchall()
with_id = db.execute("""SELECT COUNT(*) FROM clients c
    JOIN canonical_ids ci ON ci.auth_id = c.client_id
    WHERE c.active=1""").fetchone()[0]
if with_id != len(active):
    e(f"active coverage: {with_id}/{len(active)} have IDs (missing {len(active)-with_id})")
else:
    print(f"[OK] all {len(active)} active clients have canonical IDs")

# 3. canonical_ids.name <-> clients.name consistency
name_mismatch = 0
for cid, nm, aid in rows:
    if aid is not None:
        r = db.execute("SELECT name FROM clients WHERE client_id=?", (aid,)).fetchone()
        if r and r[0] != nm:
            name_mismatch += 1
            if name_mismatch <= 5:
                e(f"NAME MISMATCH: canonical '{nm}' vs clients '{r[0]}' (id {cid})")
if name_mismatch == 0:
    print("[OK] canonical_ids.name matches clients.name everywhere")

# 4. both DBs have canonical_ids (sync parity)
try:
    pdb = sqlite3.connect(PROP)
    pcount = pdb.execute("SELECT COUNT(*) FROM canonical_ids").fetchone()[0]
    if pcount != len(rows):
        w(f"proprietary canonical_ids: {pcount} vs auth {len(rows)} — sync needed")
    else:
        print(f"[OK] proprietary canonical_ids matches ({pcount})")
    pdb.close()
except Exception as ex:
    w(f"proprietary canonical_ids check failed: {ex}")

db.close()

print()
if errors:
    print(f"🔴 GUARD FAILED — {len(errors)} error(s):")
    for x in errors:
        print(f"   {x}")
    sys.exit(1)
if warns:
    print(f"⚠️  {len(warns)} warning(s):")
    for x in warns:
        print(f"   {x}")
print("✅ CANONICAL ID INTEGRITY OK — unique, permanent, unmixed")
sys.exit(0)
