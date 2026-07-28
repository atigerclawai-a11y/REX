"""
CC_ocr_review_queue.py — OCR Exception Review Queue
=====================================================
Manages low-confidence OCR results that need human review.
Integrates with CC_ocr_telegram_fallback for Telegram delivery.

Usage:
    from CC_ocr_review_queue import ReviewQueue
    q = ReviewQueue()
    q.add(pdf_path, page_num, client_name, field, ocr_value, candidates, confidence)
    q.pending()     # → list of pending reviews
    q.resolve(review_id, chosen_value)  # → resolve with user's choice
    q.report()      # → summary of queue state
"""

import json, hashlib, time
from pathlib import Path
from datetime import datetime

QUEUE_PATH = Path.home() / "Desktop/REX/.ocr_review_queue.json"
ARCHIVE_PATH = Path.home() / "Desktop/REX/logs/ocr_review_archive.json"

class ReviewQueue:
    def __init__(self):
        self.queue = self._load()
    
    def _load(self) -> dict:
        if QUEUE_PATH.exists():
            try:
                data = json.loads(QUEUE_PATH.read_text())
                # Handle old format ({"entries": {...}}) gracefully
                if "entries" in data and "pending" not in data:
                    log_msg = f"Migrating old queue format ({len(data['entries'])} entries)"
                    print(log_msg)
                    # Archive old format, start fresh
                    import shutil
                    shutil.copy(QUEUE_PATH, str(QUEUE_PATH) + ".old")
                    return {"pending": [], "resolved": [], "stats": {"total": 0, "auto_resolved": 0, "manual_resolved": 0}}
                return data
            except Exception:
                pass
        return {"pending": [], "resolved": [], "stats": {"total": 0, "auto_resolved": 0, "manual_resolved": 0}}
    
    def _save(self):
        QUEUE_PATH.parent.mkdir(parents=True, exist_ok=True)
        QUEUE_PATH.write_text(json.dumps(self.queue, indent=2, ensure_ascii=False))
    
    def add(self, pdf_path: str, page_num: int, client_name: str, field: str,
            ocr_value: str, candidates: list[str], confidence: float) -> str:
        """Add a review item. Returns review_id."""
        review_id = hashlib.md5(f"{pdf_path}:{page_num}:{client_name}:{field}:{time.time()}".encode()).hexdigest()[:12]
        
        item = {
            "id": review_id,
            "pdf_path": pdf_path,
            "page": page_num,
            "client": client_name,
            "field": field,
            "ocr_value": ocr_value,
            "candidates": candidates,
            "confidence": round(confidence, 3),
            "status": "awaiting_review",
            "created_at": datetime.now().isoformat(),
            "telegram_msg_id": None,
            "resolved_at": None,
            "chosen_value": None,
        }
        
        self.queue["pending"].append(item)
        self.queue["stats"]["total"] += 1
        self._save()
        return review_id
    
    def pending(self) -> list[dict]:
        return [r for r in self.queue["pending"] if r["status"] == "awaiting_review"]
    
    def resolve(self, review_id: str, chosen_value: str) -> bool:
        """Resolve a review with the user's chosen value."""
        for item in self.queue["pending"]:
            if item["id"] == review_id:
                item["status"] = "resolved"
                item["chosen_value"] = chosen_value
                item["resolved_at"] = datetime.now().isoformat()
                item["resolution_method"] = "manual" if chosen_value != item["ocr_value"] else "auto_accepted"
                
                # Move to resolved
                self.queue["pending"].remove(item)
                self.queue["resolved"].append(item)
                
                if item["resolution_method"] == "manual":
                    self.queue["stats"]["manual_resolved"] += 1
                else:
                    self.queue["stats"]["auto_resolved"] += 1
                
                self._save()
                self._archive()
                return True
        return False
    
    def auto_accept_above(self, threshold: float = 0.85) -> int:
        """Auto-accept pending items with confidence >= threshold."""
        count = 0
        for item in list(self.queue["pending"]):
            if item["status"] == "awaiting_review" and item["confidence"] >= threshold:
                self.resolve(item["id"], item["ocr_value"])
                count += 1
        return count
    
    def _archive(self):
        """Periodically archive old resolved items."""
        if len(self.queue["resolved"]) > 1000:
            existing = []
            if ARCHIVE_PATH.exists():
                try:
                    existing = json.loads(ARCHIVE_PATH.read_text())
                except:
                    pass
            existing.extend(self.queue["resolved"][:500])
            ARCHIVE_PATH.write_text(json.dumps(existing, indent=2))
            self.queue["resolved"] = self.queue["resolved"][500:]
            self._save()
    
    def report(self) -> str:
        """Human-readable queue status."""
        pending_count = len(self.pending())
        return (
            f"OCR Review Queue:\n"
            f"  Pending:  {pending_count}\n"
            f"  Total:    {self.queue['stats']['total']}\n"
            f"  Auto:     {self.queue['stats']['auto_resolved']}\n"
            f"  Manual:   {self.queue['stats']['manual_resolved']}\n"
            f"  Queue:    {QUEUE_PATH}"
        )

# Singleton
_queue_instance = None

def get_queue() -> ReviewQueue:
    global _queue_instance
    if _queue_instance is None:
        _queue_instance = ReviewQueue()
    return _queue_instance
