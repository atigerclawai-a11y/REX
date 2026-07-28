#!/usr/bin/env python3
"""Migrate data from CC_lead_connector.db + CC_bbg_contacts.db → CC_rex_review.db.
Dedupe by phone. Preserve original IDs as reference (id_offset by source).
"""
import json
import sqlite3
from pathlib import Path

REX = Path.home() / "Desktop/REX"
ARCHIVE = REX / "_archive"
DST = REX / "CC_rex_review.db"

# Find latest archive files
LC_FILES = sorted(ARCHIVE.glob("CC_lead_connector_*.db"))
BBG_FILES = sorted(ARCHIVE.glob("CC_bbg_contacts_*.db"))
if not LC_FILES or not BBG_FILES:
    raise SystemExit("No archive DBs found")
LC_PATH = LC_FILES[-1]
BBG_PATH = BBG_FILES[-1]

print(f"Sources: {LC_PATH.name}, {BBG_PATH.name}")
print(f"Target: {DST}")

src_lc = sqlite3.connect(str(LC_PATH))
src_lc.row_factory = sqlite3.Row
src_bbg = sqlite3.connect(str(BBG_PATH))
src_bbg.row_factory = sqlite3.Row
dst = sqlite3.connect(str(DST))
dst.row_factory = sqlite3.Row
dst.execute("PRAGMA foreign_keys = ON")

# ── 1. Migrate pipelines (lead_connector) ──
print("\n[1] Pipelines...")
pl_count = 0
for row in src_lc.execute("SELECT * FROM pipelines"):
    dst.execute("""
        INSERT INTO pipelines (id, name, business, stages, created_at)
        VALUES (?, ?, ?, ?, ?)
    """, (row["id"], row["name"], row["business"], row["stages"], row["created_at"]))
    pl_count += 1
dst.commit()
print(f"   ✓ {pl_count} pipelines")

# ── 2. Migrate contacts (lead_connector) ──
print("\n[2] Contacts (lead_connector)...")
lc_count = 0
lc_phone_map = {}  # phone → new dst id
for row in src_lc.execute("SELECT * FROM contacts"):
    name = f"{row['first_name']} {row['last_name']}".strip() or row['first_name']
    cur = dst.execute("""
        INSERT INTO contacts (id, first_name, last_name, name, phone, email, tags, source,
                             business, status, notes, custom_fields, pipeline_id, stage_id,
                             created_at, deleted_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        row["id"], row["first_name"], row["last_name"], name,
        row["phone"], row["email"], row["tags"], row["source"],
        row["business"], row["status"], row["notes"], row["custom_fields"],
        row["pipeline_id"], row["stage_id"],
        row["created_at"], row["deleted_at"]
    ))
    lc_count += 1
    if row["phone"]:
        # Normalize: strip non-digits, last 10 digits
        clean = ''.join(c for c in str(row["phone"]) if c.isdigit())[-10:]
        if clean:
            lc_phone_map[clean] = row["id"]
dst.commit()
print(f"   ✓ {lc_count} contacts (with {len(lc_phone_map)} phones mapped)")

# ── 3. Migrate contacts (bbg_contacts) — dedupe by phone ──
print("\n[3] Contacts (bbg_contacts, dedupe by phone)...")
bbg_new = 0
bbg_dup = 0
bbg_id_map = {}  # bbg old id → dst new id
next_id = dst.execute("SELECT MAX(id) FROM contacts").fetchone()[0] + 1
for row in src_bbg.execute("SELECT * FROM contacts"):
    phone = row["phone"] or ""
    clean = ''.join(c for c in str(phone) if c.isdigit())[-10:] if phone else ""
    if clean and clean in lc_phone_map:
        # Already in lead_connector — map to existing id, skip insert
        bbg_id_map[row["id"]] = lc_phone_map[clean]
        bbg_dup += 1
        continue
    # Insert new contact
    name = row["name"]
    parts = name.split(maxsplit=1)
    first = parts[0] if parts else ""
    last = parts[1] if len(parts) > 1 else ""
    cur = dst.execute("""
        INSERT INTO contacts (id, first_name, last_name, name, phone, email, tags,
                             source, notes, business, status, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        next_id, first, last, name, phone, row["email"],
        json.dumps(row["tags"].split(",") if row["tags"] else []),
        row["source"], row["notes"], "BBG", "lead",
        row["created_at"], row["updated_at"]
    ))
    bbg_id_map[row["id"]] = next_id
    next_id += 1
    bbg_new += 1
dst.commit()
print(f"   ✓ {bbg_new} new + {bbg_dup} duplicates skipped")

# ── 4. Migrate conversations ──
print("\n[4] Conversations...")
conv_count = 0
for row in src_bbg.execute("SELECT * FROM conversations"):
    contact_id = bbg_id_map.get(row["contact_id"], 0) or 0
    if contact_id == 0:
        continue
    dst.execute("""
        INSERT INTO conversations (id, contact_id, channel, direction, body, duration_sec,
                                   recording_url, transcript, metadata, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        row["id"], contact_id, row["channel"], row["direction"],
        row["body"], row["duration_sec"], row["recording_url"],
        row["transcript"], row["metadata"], row["created_at"]
    ))
    conv_count += 1
dst.commit()
print(f"   ✓ {conv_count} conversations")

# ── 5. Reservations from tally ──
print("\n[5] Reservations (from tally)...")
tally_path = REX / "bbg_reservation_tally.json"
res_count = 0
if tally_path.exists():
    tally = json.loads(tally_path.read_text())
    for date_str, data in tally.get("days", {}).items():
        guests = data.get("guests", 2) if isinstance(data, dict) else 2
        dst.execute("""
            INSERT INTO reservations (reservation_date, party_size, status, source)
            VALUES (?, ?, ?, ?)
        """, (date_str, guests, "confirmed", "owner.com"))
        res_count += 1
    dst.commit()
print(f"   ✓ {res_count} reservations")

# ── Final counts ──
print("\n=== MIGRATION COMPLETE ===")
print(f"  Contacts:       {dst.execute('SELECT COUNT(*) FROM contacts').fetchone()[0]}")
print(f"  Pipelines:      {dst.execute('SELECT COUNT(*) FROM pipelines').fetchone()[0]}")
print(f"  Conversations:  {dst.execute('SELECT COUNT(*) FROM conversations').fetchone()[0]}")
print(f"  Reservations:   {dst.execute('SELECT COUNT(*) FROM reservations').fetchone()[0]}")

dst.close()
src_lc.close()
src_bbg.close()
print(f"\n✅ Unified DB ready: {DST}")