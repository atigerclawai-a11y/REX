"""
Rexxie Memory Cleanup
=====================
Removes "Kato said: hey rexxie" spam entries from rexxie.db
that were caused by _activate_rexxie_if_needed firing on every message.

Run once:
  cd ~/Desktop/REX && .venv/bin/python cleanup_rexxie_memory.py
"""

import sqlite3
from pathlib import Path

DB_PATH = Path.home() / "Desktop" / "REX" / "rexxie.db"

if not DB_PATH.exists():
    print(f"rexxie.db not found at {DB_PATH}")
    exit(1)

con = sqlite3.connect(str(DB_PATH))

# Count spam entries first
spam_patterns = [
    "%hey rexxie%",
    "%Kato said: hey rexxie%",
]

total_spam = 0
for pattern in spam_patterns:
    count = con.execute(
        "SELECT COUNT(*) FROM rexxie_memory WHERE content_enc LIKE ?", (pattern,)
    ).fetchone()[0]
    print(f"  Pattern '{pattern}': {count} entries")
    total_spam += count

# Note: content is encrypted, so LIKE won't match encrypted content.
# Instead we look for entries where the decrypted content would be "hey rexxie".
# Since content is triple-encrypted, we can't filter by content directly.
# Instead, show total memory count and ask for selective wipe if needed.

total = con.execute("SELECT COUNT(*) FROM rexxie_memory WHERE active=1").fetchone()[0]
print(f"\nTotal active memories in rexxie.db: {total}")
print("\nNote: Memories are triple-encrypted — cannot filter by content directly.")
print("To purge ALL conversation-type memories (safest for removing spam):")
print()

# Count conversation memories vs personal/identity memories
conv_count = con.execute(
    "SELECT COUNT(*) FROM rexxie_memory WHERE mem_type='conversation' AND active=1"
).fetchone()[0]
identity_count = con.execute(
    "SELECT COUNT(*) FROM rexxie_memory WHERE mem_type != 'conversation' AND active=1"
).fetchone()[0]

print(f"  Conversation memories (likely contains spam): {conv_count}")
print(f"  Identity/personal memories (safe to keep):    {identity_count}")
print()

if conv_count > 0:
    confirm = input(f"Delete all {conv_count} conversation memories? (yes/no): ").strip().lower()
    if confirm == "yes":
        con.execute("UPDATE rexxie_memory SET active=0 WHERE mem_type='conversation'")
        con.commit()
        print(f"  ✅ Cleared {conv_count} conversation memories.")
        print(f"  {identity_count} identity/personal memories preserved.")
    else:
        print("  Skipped — no changes made.")
else:
    print("No conversation memories to clear.")

con.close()
print("\nDone. Restart Rexxie for changes to take effect.")
