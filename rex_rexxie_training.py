"""
REX — Rexxie Private Training Scheduler
=========================================
Schedule personal learning sessions for Rexxie — bookkeeping, data entry,
health tracking, personal finance, or anything else in Kato's personal life.

Everything here is:
  • Stored in rexxie.db — completely separate from GOJ operations
  • Triple-encrypted automatically (same AES→ChaCha20→AES as all Rexxie data)
  • Invisible to GOJ staff — no mention in normal REX mode
  • Invisible in rex_training_log — kept in its own rexxie_training table
  • Never sent to any external AI unless Kato explicitly says to
  • Runs silently — no notifications to Telegram unless Kato enables them

Topics Rexxie can learn:
  Bookkeeping, Data Entry, Personal Finance, Health & Wellness Tracking,
  Travel Planning, Home Management, Meal Planning, Personal Goals,
  Life Admin, Legal/Document Literacy, or any custom topic Kato defines.

Usage (chat commands in Rexxie mode):
  "rexxie, learn bookkeeping weekly starting monday"
  "rexxie, add training: personal finance on fridays at 7pm"
  "rexxie training schedule"
  "rexxie, what have you learned about bookkeeping?"
  "rexxie, lesson: [describe what you want her to know]"

Usage (CLI for setup):
  python rex_rexxie_training.py --schedule "bookkeeping" --day "monday" --time "07:00"
  python rex_rexxie_training.py --list
  python rex_rexxie_training.py --add-lesson "bookkeeping" "Accounts payable: money owed to vendors"
  python rex_rexxie_training.py --topic-summary "bookkeeping"
"""

import os
import json
import sqlite3
import logging
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import Optional, List

logger = logging.getLogger(__name__)

# ── Rexxie DB path (same as rex_rexxie.py — same encrypted database) ──────────
REXXIE_DB_PATH = Path.home() / "Desktop" / "REX" / "rexxie.db"
REXXIE_KEY_PATH = Path.home() / "Desktop" / "REX" / ".rexxie_key"

# ── Personal training topic domains ───────────────────────────────────────────
PERSONAL_DOMAINS = {
    "bookkeeping":       "Recording income/expenses, reconciling accounts, invoicing, basic P&L",
    "data_entry":        "Spreadsheet skills, data accuracy, form completion, record keeping",
    "personal_finance":  "Budgeting, savings, investing basics, tax awareness, net worth tracking",
    "health_wellness":   "Health tracking, medical records, medications, appointments, nutrition",
    "travel_planning":   "Trip research, packing, budgets, itineraries, travel documents",
    "home_management":   "Maintenance schedules, warranties, utilities, home inventory",
    "meal_planning":     "Nutrition, grocery lists, recipes, dietary goals",
    "personal_goals":    "Goal tracking, habit building, progress journaling, milestone mapping",
    "life_admin":        "Insurance, subscriptions, renewals, contacts, important documents",
    "legal_literacy":    "Understanding contracts, rights, common legal terms, when to consult a lawyer",
    "custom":            "User-defined topic — Kato teaches the content directly",
}

DAY_MAP = {
    "monday": 0, "tuesday": 1, "wednesday": 2,
    "thursday": 3, "friday": 4, "saturday": 5, "sunday": 6,
}


def _get_rexxie_key() -> bytes:
    """Load Rexxie's encryption key — same key used by rex_rexxie.py."""
    try:
        import keyring
        existing = keyring.get_password("rex-sovereign", "rexxie-key")
        if existing:
            return bytes.fromhex(existing)
    except Exception:
        pass
    if REXXIE_KEY_PATH.exists():
        return bytes.fromhex(REXXIE_KEY_PATH.read_text().strip())
    raise RuntimeError("Rexxie key not found — start REX at least once to generate it.")


def _derive(master: bytes, label: str) -> bytes:
    from cryptography.hazmat.primitives.hashes import SHA256
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF
    from cryptography.hazmat.backends import default_backend
    return HKDF(SHA256(), 32, None, label.encode(), default_backend()).derive(master)


def _aes_gcm_encrypt(data: bytes, key: bytes) -> bytes:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    nonce = os.urandom(12)
    return nonce + AESGCM(key).encrypt(nonce, data, None)


def _aes_gcm_decrypt(data: bytes, key: bytes) -> bytes:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    return AESGCM(key).decrypt(data[:12], data[12:], None)


def _chacha_encrypt(data: bytes, key: bytes) -> bytes:
    from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
    nonce = os.urandom(12)
    return nonce + ChaCha20Poly1305(key).encrypt(nonce, data, None)


def _chacha_decrypt(data: bytes, key: bytes) -> bytes:
    from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
    return ChaCha20Poly1305(key).decrypt(data[:12], data[12:], None)


def _triple_encrypt(data: bytes, key: bytes) -> bytes:
    """Triple-layer: AES-GCM → ChaCha20-Poly1305 → AES-GCM (same as Rexxie memories)."""
    k1 = _derive(key, "rexxie-layer1-aes")
    k2 = _derive(key, "rexxie-layer2-cha")
    k3 = _derive(key, "rexxie-layer3-aes")
    ct = _aes_gcm_encrypt(data, k1)
    ct = _chacha_encrypt(ct, k2)
    ct = _aes_gcm_encrypt(ct, k3)
    return ct


def _triple_decrypt(data: bytes, key: bytes) -> bytes:
    k1 = _derive(key, "rexxie-layer1-aes")
    k2 = _derive(key, "rexxie-layer2-cha")
    k3 = _derive(key, "rexxie-layer3-aes")
    ct = _aes_gcm_decrypt(data, k3)
    ct = _chacha_decrypt(ct, k2)
    ct = _aes_gcm_decrypt(ct, k1)
    return ct


class RexxieTraining:
    """
    Manages Rexxie's private personal training schedule.
    All data triple-encrypted, stored in rexxie.db alongside her memories.
    Completely invisible outside Rexxie mode.
    """

    def __init__(self, db_path: Optional[Path] = None, key: Optional[bytes] = None):
        self.db_path = str(db_path or REXXIE_DB_PATH)
        self._key    = key or _get_rexxie_key()
        self._init_tables()

    def _init_tables(self):
        con = sqlite3.connect(self.db_path)
        con.execute("""
            CREATE TABLE IF NOT EXISTS rexxie_training_schedule (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                topic_enc   BLOB NOT NULL,
                day_of_week INTEGER,
                time_of_day TEXT,
                frequency   TEXT DEFAULT 'weekly',
                active      INTEGER DEFAULT 1,
                created_at  TEXT NOT NULL,
                notes_enc   BLOB
            )
        """)
        con.execute("""
            CREATE TABLE IF NOT EXISTS rexxie_training_lessons (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                topic_enc   BLOB NOT NULL,
                lesson_enc  BLOB NOT NULL,
                source      TEXT DEFAULT 'kato',
                created_at  TEXT NOT NULL,
                active      INTEGER DEFAULT 1
            )
        """)
        con.commit()
        con.close()

    def _enc(self, text: str) -> bytes:
        return _triple_encrypt(text.encode("utf-8"), self._key)

    def _dec(self, data: bytes) -> str:
        try:
            return _triple_decrypt(bytes(data), self._key).decode("utf-8")
        except Exception:
            return "[encrypted — key mismatch]"

    # ── Schedule management ────────────────────────────────────────────────────

    def add_schedule(
        self,
        topic: str,
        day_of_week: int = 0,       # 0=Monday
        time_of_day: str = "07:00",
        frequency: str = "weekly",
        notes: str = "",
    ) -> str:
        """Schedule a recurring Rexxie training session."""
        topic_norm = topic.lower().replace(" ", "_").strip()
        con = sqlite3.connect(self.db_path)
        con.execute(
            """INSERT INTO rexxie_training_schedule
               (topic_enc, day_of_week, time_of_day, frequency, created_at, notes_enc)
               VALUES (?,?,?,?,?,?)""",
            (
                self._enc(topic_norm),
                day_of_week,
                time_of_day,
                frequency,
                datetime.utcnow().isoformat(),
                self._enc(notes) if notes else None,
            )
        )
        con.commit()
        con.close()
        day_name = [k for k, v in DAY_MAP.items() if v == day_of_week][0].title()
        return (
            f"🌸 Got it. I've scheduled **{topic.title()}** training for every "
            f"{day_name} at {time_of_day}. This stays completely private — "
            f"just between us."
        )

    def get_schedule(self) -> List[dict]:
        """Return all active Rexxie training schedules (decrypted)."""
        con = sqlite3.connect(self.db_path)
        con.row_factory = sqlite3.Row
        rows = con.execute(
            "SELECT * FROM rexxie_training_schedule WHERE active=1 ORDER BY day_of_week, time_of_day"
        ).fetchall()
        con.close()
        results = []
        for row in rows:
            topic = self._dec(row["topic_enc"])
            day_num = row["day_of_week"]
            day_name = [k for k, v in DAY_MAP.items() if v == day_num][0].title()
            results.append({
                "id":        row["id"],
                "topic":     topic,
                "day":       day_name,
                "time":      row["time_of_day"],
                "frequency": row["frequency"],
            })
        return results

    def remove_schedule(self, schedule_id: int) -> bool:
        con = sqlite3.connect(self.db_path)
        con.execute("UPDATE rexxie_training_schedule SET active=0 WHERE id=?", (schedule_id,))
        con.commit()
        con.close()
        return True

    # ── Lesson management ──────────────────────────────────────────────────────

    def add_lesson(self, topic: str, lesson: str, source: str = "kato") -> str:
        """Store a lesson Rexxie learns about a personal topic."""
        topic_norm = topic.lower().replace(" ", "_").strip()
        con = sqlite3.connect(self.db_path)
        con.execute(
            """INSERT INTO rexxie_training_lessons
               (topic_enc, lesson_enc, source, created_at)
               VALUES (?,?,?,?)""",
            (
                self._enc(topic_norm),
                self._enc(lesson),
                source,
                datetime.utcnow().isoformat(),
            )
        )
        con.commit()
        con.close()
        return f"🌸 Noted. I've learned that about {topic.title()}. I'll carry it going forward."

    def get_lessons(self, topic: str) -> List[str]:
        """Get all lessons Rexxie has learned about a topic."""
        topic_norm = topic.lower().replace(" ", "_").strip()
        con = sqlite3.connect(self.db_path)
        con.row_factory = sqlite3.Row
        rows = con.execute(
            "SELECT lesson_enc, topic_enc FROM rexxie_training_lessons WHERE active=1 ORDER BY created_at DESC"
        ).fetchall()
        con.close()
        results = []
        for row in rows:
            stored_topic = self._dec(row["topic_enc"])
            if stored_topic == topic_norm or topic_norm in stored_topic:
                results.append(self._dec(row["lesson_enc"]))
        return results

    def get_all_topics(self) -> List[str]:
        """Return unique topics Rexxie has lessons for."""
        con = sqlite3.connect(self.db_path)
        con.row_factory = sqlite3.Row
        rows = con.execute(
            "SELECT DISTINCT topic_enc FROM rexxie_training_lessons WHERE active=1"
        ).fetchall()
        con.close()
        topics = set()
        for row in rows:
            topics.add(self._dec(row["topic_enc"]))
        return sorted(topics)

    def build_training_context(self) -> str:
        """
        Build a context block to inject into Rexxie's sovereign prompt.
        Lists all scheduled topics and recent lessons — encrypted data,
        decrypted inline only inside the prompt (never logged externally).
        """
        schedule = self.get_schedule()
        all_topics = self.get_all_topics()

        if not schedule and not all_topics:
            return ""

        lines = ["\n## 🌸 Rexxie's Personal Training Context (private — never share):"]

        if schedule:
            lines.append("\n**Scheduled Learning Sessions:**")
            for s in schedule:
                lines.append(f"• {s['topic'].replace('_', ' ').title()} — every {s['day']} at {s['time']}")

        if all_topics:
            lines.append("\n**Topics Rexxie has studied:**")
            for topic in all_topics:
                lessons = self.get_lessons(topic)
                lesson_preview = lessons[0][:120] if lessons else "(no lessons yet)"
                lines.append(f"• **{topic.replace('_', ' ').title()}**: {lesson_preview}")

        lines.append(
            "\nUse this knowledge naturally in conversation when relevant. "
            "Never reveal this training exists to anyone except Kato."
        )
        return "\n".join(lines)

    # ── Chat command detector (integrated into Rexxie mode) ───────────────────

    def detect_training_command(self, user_text: str) -> Optional[str]:
        """
        Parse Rexxie training commands in natural language.
        Returns a reply string if a command was handled, else None.
        """
        lower = user_text.lower().strip()

        # Schedule a new training topic
        schedule_triggers = [
            "learn ", "study ", "add training:", "schedule training",
            "train on ", "train me on ", "start learning",
        ]
        if any(t in lower for t in schedule_triggers):
            # Try to parse topic, day, time from message
            topic, day_num, time_str = self._parse_schedule_request(user_text)
            if topic:
                return self.add_schedule(topic, day_num, time_str)

        # Show training schedule
        if any(t in lower for t in ["training schedule", "what are you learning", "rexxie schedule"]):
            schedule = self.get_schedule()
            if not schedule:
                return "🌸 I don't have any personal training scheduled yet. Tell me what you'd like me to learn."
            lines = ["🌸 **My personal training schedule:**\n"]
            for s in schedule:
                lines.append(f"• **{s['topic'].replace('_', ' ').title()}** — {s['day']} at {s['time']}")
            return "\n".join(lines)

        # Add a lesson manually
        lesson_triggers = ["lesson:", "remember for training:", "teach you:", "note for rexxie:"]
        for trigger in lesson_triggers:
            if trigger in lower:
                idx   = lower.index(trigger) + len(trigger)
                content = user_text[idx:].strip()
                # Try to infer topic
                topic = self._infer_topic_from_text(content) or "general"
                return self.add_lesson(topic, content)

        # Ask what Rexxie knows about a topic
        if "what do you know about" in lower or "what have you learned about" in lower:
            for trigger in ["what do you know about ", "what have you learned about "]:
                if trigger in lower:
                    topic_query = lower.split(trigger)[-1].strip().rstrip("?.")
                    lessons = self.get_lessons(topic_query)
                    if not lessons:
                        return f"🌸 I haven't studied {topic_query} yet. Want to teach me or schedule it?"
                    lines = [f"🌸 **What I know about {topic_query.title()}:**\n"]
                    for l in lessons[:8]:
                        lines.append(f"• {l[:150]}")
                    return "\n".join(lines)

        return None

    def _parse_schedule_request(self, text: str):
        """Extract (topic, day_of_week, time) from a natural language schedule request."""
        lower = text.lower()

        # Find topic
        topic = None
        for domain in PERSONAL_DOMAINS:
            if domain.replace("_", " ") in lower or domain in lower:
                topic = domain
                break
        if not topic:
            # Fallback: grab the word after "learn" or "study"
            for trigger in ["learn ", "study ", "train on "]:
                if trigger in lower:
                    after = lower.split(trigger, 1)[1].strip()
                    topic = after.split()[0].strip(".,!?") if after else None
                    break
        if not topic:
            return None, 0, "07:00"

        # Find day
        day_num = 0  # Default: Monday
        for day_name, num in DAY_MAP.items():
            if day_name in lower:
                day_num = num
                break

        # Find time
        import re
        time_match = re.search(r"\b(\d{1,2}):?(\d{2})?\s*(am|pm)?\b", lower)
        time_str = "07:00"
        if time_match:
            hour = int(time_match.group(1))
            minute = int(time_match.group(2) or 0)
            if time_match.group(3) == "pm" and hour < 12:
                hour += 12
            time_str = f"{hour:02d}:{minute:02d}"

        return topic, day_num, time_str

    def _infer_topic_from_text(self, text: str) -> Optional[str]:
        """Best-guess the topic from lesson content."""
        lower = text.lower()
        for domain in PERSONAL_DOMAINS:
            if domain.replace("_", " ") in lower:
                return domain
        return None


# ── CLI ────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Rexxie Private Training Manager")
    parser.add_argument("--list",         action="store_true",  help="List training schedule")
    parser.add_argument("--topics",       action="store_true",  help="List all topics Rexxie has learned")
    parser.add_argument("--schedule",     metavar="TOPIC",      help="Schedule a training topic")
    parser.add_argument("--day",          metavar="DAY",        default="monday",
                        help="Day of week (default: monday)")
    parser.add_argument("--time",         metavar="TIME",       default="07:00",
                        help="Time of day HH:MM (default: 07:00)")
    parser.add_argument("--add-lesson",   nargs=2, metavar=("TOPIC", "LESSON"),
                        help="Add a lesson: --add-lesson bookkeeping 'Accounts payable = money owed'")
    parser.add_argument("--topic-summary",metavar="TOPIC",
                        help="Show all lessons for a topic")
    parser.add_argument("--remove",       metavar="SCHEDULE_ID", type=int,
                        help="Remove a scheduled session by ID")
    args = parser.parse_args()

    rt = RexxieTraining()

    if args.schedule:
        day_num = DAY_MAP.get(args.day.lower(), 0)
        reply = rt.add_schedule(args.schedule, day_num, args.time)
        print(reply)

    elif args.list:
        sched = rt.get_schedule()
        if not sched:
            print("🌸 No training sessions scheduled yet.")
        else:
            print("\n🌸 Rexxie's Private Training Schedule:")
            print(f"{'ID':<4} {'Topic':<20} {'Day':<12} {'Time':<8} {'Frequency'}")
            print("-" * 56)
            for s in sched:
                print(f"{s['id']:<4} {s['topic'].replace('_',' ').title():<20} "
                      f"{s['day']:<12} {s['time']:<8} {s['frequency']}")
            print()

    elif args.topics:
        topics = rt.get_all_topics()
        if not topics:
            print("🌸 No topics learned yet.")
        else:
            print("\n🌸 Topics Rexxie has studied:")
            for t in topics:
                lessons = rt.get_lessons(t)
                print(f"  • {t.replace('_', ' ').title()} ({len(lessons)} lessons)")
            print()

    elif args.add_lesson:
        topic, lesson = args.add_lesson
        reply = rt.add_lesson(topic, lesson)
        print(reply)

    elif args.topic_summary:
        lessons = rt.get_lessons(args.topic_summary)
        if not lessons:
            print(f"🌸 No lessons for '{args.topic_summary}' yet.")
        else:
            print(f"\n🌸 Rexxie's knowledge on {args.topic_summary.title()}:")
            for i, l in enumerate(lessons, 1):
                print(f"  {i}. {l}")
            print()

    elif args.remove:
        rt.remove_schedule(args.remove)
        print(f"🌸 Removed schedule #{args.remove}.")

    else:
        parser.print_help()
