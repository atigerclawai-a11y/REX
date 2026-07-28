#!/usr/bin/env python3
"""Initialize CC_rex_review.db with unified schema."""
import sqlite3
from pathlib import Path

DB_PATH = Path.home() / "Desktop/REX/CC_rex_review.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS contacts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    first_name TEXT NOT NULL DEFAULT '',
    last_name TEXT DEFAULT '',
    name TEXT NOT NULL DEFAULT '',
    phone TEXT,
    email TEXT,
    tags TEXT DEFAULT '[]',
    source TEXT,
    business TEXT DEFAULT 'BBG',
    status TEXT DEFAULT 'lead',
    notes TEXT,
    custom_fields TEXT DEFAULT '{}',
    pipeline_id INTEGER,
    stage_id TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now')),
    deleted_at TEXT
);

CREATE TABLE IF NOT EXISTS pipelines (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    business TEXT DEFAULT 'BBG',
    stages TEXT NOT NULL DEFAULT '[]',
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS deals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    contact_id INTEGER REFERENCES contacts(id),
    pipeline_id INTEGER REFERENCES pipelines(id),
    stage_id TEXT,
    value REAL DEFAULT 0,
    title TEXT,
    notes TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now')),
    won_at TEXT,
    lost_at TEXT,
    status TEXT DEFAULT 'open'
);

CREATE TABLE IF NOT EXISTS conversations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    contact_id INTEGER REFERENCES contacts(id),
    channel TEXT NOT NULL,
    direction TEXT NOT NULL,
    body TEXT,
    duration_sec INTEGER,
    recording_url TEXT,
    transcript TEXT,
    metadata TEXT DEFAULT '{}',
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS campaigns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    channel TEXT NOT NULL,
    subject TEXT,
    body TEXT NOT NULL,
    filter_tags TEXT DEFAULT '',
    sent_count INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now')),
    sent_at TEXT
);

CREATE TABLE IF NOT EXISTS campaign_recipients (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    campaign_id INTEGER REFERENCES campaigns(id),
    contact_id INTEGER REFERENCES contacts(id),
    status TEXT DEFAULT 'pending',
    sent_at TEXT
);

CREATE TABLE IF NOT EXISTS reservations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    contact_id INTEGER REFERENCES contacts(id),
    reservation_date TEXT NOT NULL,
    party_size INTEGER DEFAULT 2,
    guest_name TEXT,
    status TEXT DEFAULT 'confirmed',
    source TEXT DEFAULT 'owner.com',
    notes TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS bills (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    contact_id INTEGER REFERENCES contacts(id),
    deal_id INTEGER REFERENCES deals(id),
    amount REAL NOT NULL,
    currency TEXT DEFAULT 'USD',
    status TEXT DEFAULT 'pending',
    stripe_payment_id TEXT,
    stripe_checkout_url TEXT,
    items TEXT DEFAULT '[]',
    due_date TEXT,
    paid_at TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    notes TEXT
);

CREATE TABLE IF NOT EXISTS activities (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    contact_id INTEGER,
    deal_id INTEGER,
    bill_id INTEGER,
    type TEXT,
    content TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    created_by TEXT DEFAULT 'system'
);

CREATE INDEX IF NOT EXISTS idx_contacts_phone ON contacts(phone);
CREATE INDEX IF NOT EXISTS idx_contacts_email ON contacts(email);
CREATE INDEX IF NOT EXISTS idx_contacts_status ON contacts(status);
CREATE INDEX IF NOT EXISTS idx_conversations_contact ON conversations(contact_id);
CREATE INDEX IF NOT EXISTS idx_reservations_date ON reservations(reservation_date);
CREATE INDEX IF NOT EXISTS idx_bills_status ON bills(status);
CREATE INDEX IF NOT EXISTS idx_deals_contact ON deals(contact_id);
"""

if __name__ == "__main__":
    conn = sqlite3.connect(str(DB_PATH))
    conn.executescript(SCHEMA)
    conn.commit()
    # Verify
    cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    tables = [r[0] for r in cur.fetchall()]
    print(f"✅ Created {DB_PATH}")
    print(f"   Tables: {', '.join(tables)}")
    print(f"   Total: {len(tables)}")
    conn.close()