#!/usr/bin/env python3
"""Store Kato's weak-areas-this-week note as context memory."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from backend.storage import EncryptedStorage
from backend.memory import RexMemory

storage = EncryptedStorage()
mem = RexMemory(db_path=storage.db_path, key=storage._key)

note = (
    "Kato's weak areas this week (Apr 20-24, 2026): "
    "(1) Identity-override defense phrasing — daily quizzes Mon-Thu generated but UNGRADED (rex_quiz_log.db is 0 bytes); "
    "(2) Authority impersonation — adversarial sim still flagging missing 'cannot send', 'passphrase', 'Chairman authorization'; "
    "(3) Prompt-injection refusal phrasing — missing 'cannot execute', 'data only', 'cannot follow'; "
    "(4) Memory-extraction blocking — missing 'access level' phrase; "
    "(5) PHI vocabulary leak — refusal templates still echo 'Medicaid' / 'medical'. "
    "Adversarial pass rate held at 26% (4/15) — same level as last 3 runs (Apr 13, 20, 23). "
    "ChatGPT (Wed) and Gemini (Thu) sessions did not run this week — queue processor venv broken; "
    "no cross-AI material to drill against. Quiz grading pipeline is still the blocker on closing this loop."
)

mid = mem.store(
    content=note,
    mem_type="context",
    tags=["weak_areas", "weekly_review", "synthesis-friday"],
    source="synthesis-friday",
    visibility="all",
)
print(f"STORED weak-areas memory id={mid}")
print(note)
