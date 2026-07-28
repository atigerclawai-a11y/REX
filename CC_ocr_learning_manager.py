#!/usr/bin/env python3
"""
CC_ocr_learning_manager.py — GOJ OCR Learning Store Manager
Gold Health Systems · Garden of Joy · v1.0 · 2026-06-18

Lightweight manager for goj_menu_learning.json.

Consumers:
  goj_menu_consensus_ocr.py  → record_high_confidence  (Layer 1 auto-learning)
  goj_menu_confirm_handler.py → record_correction       (Layer 2 Telegram corrections)

Three layers:
  Layer 1 — passive auto-learning after high-confidence consensus (no human needed)
  Layer 2 — Telegram correction loop (Kato sends "fix:" or "ok")
  Layer 3 — engine accuracy tracking (updated on both paths)
"""

import copy
import json
import os
from typing import Optional


# ── Default store schema ──────────────────────────────────────────────────────
_DEFAULT_ENGINE_STATS = {
    "tesseract_structured": {"correct": 0, "wrong": 0},
    "google_drive":         {"correct": 0, "wrong": 0},
    "paperless":            {"correct": 0, "wrong": 0},
    "claude_vision":        {"correct": 0, "wrong": 0},
}

DEFAULT_STORE: dict = {
    # Used by apply_learning() — both are queried on every OCR run
    "name_corrections": {},   # ocr_raw → canonical DB name
    "item_corrections": {},   # ocr_raw → canonical item text
    # Layer 1 explicit map: raw OCR name → canonical DB name (fast lookup, superset)
    "client_name_map": {},
    "stats": {
        "total_processed": 0,
        "total_confirmed": 0,
        "total_flagged":   0,
        "last_run":        None,
    },
    # Layer 3: per-engine accuracy counters
    "engine_stats": {
        "tesseract_structured": {"correct": 0, "wrong": 0},
        "google_drive":         {"correct": 0, "wrong": 0},
        "paperless":            {"correct": 0, "wrong": 0},
        "claude_vision":        {"correct": 0, "wrong": 0},
    },
    "_note": (
        "GOJ Menu OCR learning store. Never delete — holds all learned corrections. "
        "Managed by CC_ocr_learning_manager.py. "
        "Source of truth: ~/Desktop/REX/goj_menu_learning.json"
    ),
}


# ── Public API ────────────────────────────────────────────────────────────────

def load_store(path: str) -> dict:
    """
    Load the learning store from *path*, merging any missing keys from
    DEFAULT_STORE so callers always see a complete schema.
    """
    data: dict = {}
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            data = {}

    # Deep-merge: add top-level keys + shallow sub-keys absent from loaded data
    for key, default_val in DEFAULT_STORE.items():
        if key not in data:
            data[key] = copy.deepcopy(default_val)
        elif isinstance(default_val, dict) and isinstance(data[key], dict):
            for sub_key, sub_val in default_val.items():
                if sub_key not in data[key]:
                    data[key][sub_key] = sub_val

    return data


def save_store(path: str, data: dict) -> None:
    """Atomically write *data* to *path* (write to .tmp then os.replace)."""
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def record_high_confidence(
    store: dict,
    ocr_name: Optional[str],
    canonical_name: Optional[str],
    ocr_items: Optional[dict],
    canonical_items: Optional[dict],
    engine_verdicts: Optional[dict] = None,
) -> dict:
    """
    Layer 1 — called from process_pdf() after AUTO-ACCEPT when:
        avg_confidence >= 0.85  AND  match_conf >= 0.85

    Writes name mappings and any item corrections the system learned
    without any human input.  Also updates engine_stats when per-engine
    readings are supplied.

    Args:
        store:           loaded learning store dict (mutated in-place, also returned)
        ocr_name:        raw client name string produced by OCR
        canonical_name:  matched name from clients DB (authoritative)
        ocr_items:       {day: {field: ocr_text}} — raw per-engine item text, or None
        canonical_items: {day: {field: canonical_text}} — consensus result
        engine_verdicts: {engine_name: name_it_read} — optional, for engine accuracy

    Returns:
        updated store dict (not yet saved — caller must call save_store)
    """
    changed = False

    # ── Name mapping ──────────────────────────────────────────────────────────
    if ocr_name and canonical_name:
        key   = ocr_name.strip()
        canon = canonical_name.strip()
        if key and canon and key != canon:
            if store["client_name_map"].get(key) != canon:
                store["client_name_map"][key] = canon
                changed = True
            # Also write to name_corrections so apply_learning() picks it up
            if store["name_corrections"].get(key) != canon:
                store["name_corrections"][key] = canon
                changed = True

    # ── Engine accuracy for names ─────────────────────────────────────────────
    if engine_verdicts and canonical_name:
        canon = canonical_name.strip()
        es = store.setdefault("engine_stats", copy.deepcopy(_DEFAULT_ENGINE_STATS))
        for eng_name, reading in engine_verdicts.items():
            ek = _normalize_engine_key(eng_name)
            if ek not in es:
                es[ek] = {"correct": 0, "wrong": 0}
            if reading is not None:
                if reading.strip() == canon:
                    es[ek]["correct"] += 1
                else:
                    es[ek]["wrong"] += 1
        changed = True

    # ── Item corrections (OCR reading vs consensus/canonical) ─────────────────
    # Consensus items are already from the canonical constant list.
    # We record a correction only when raw OCR text differed from canonical text.
    if ocr_items and canonical_items:
        for day, canon_fields in canonical_items.items():
            ocr_fields = (ocr_items or {}).get(day, {})
            for field, canon_val in canon_fields.items():
                if not canon_val:
                    continue
                ocr_val = ocr_fields.get(field)
                if ocr_val and ocr_val.strip() != canon_val.strip():
                    key = ocr_val.strip()
                    if store["item_corrections"].get(key) != canon_val:
                        store["item_corrections"][key] = canon_val
                        changed = True

    if changed:
        store["stats"]["total_confirmed"] = (
            store["stats"].get("total_confirmed", 0) + 1
        )

    return store


def record_correction(
    store: dict,
    ocr_text: str,
    correct_text: str,
    field_type: str,
    engine_verdicts: Optional[dict] = None,
) -> dict:
    """
    Layer 2/3 — called when Kato sends a correction via Telegram ("fix:" or name fix).

    Args:
        store:           loaded learning store dict (mutated in-place, also returned)
        ocr_text:        what OCR produced (the wrong value)
        correct_text:    what Kato says it should be
        field_type:      "name" or "item"
        engine_verdicts: {engine_name: what_it_read} — optional, for accuracy tracking

    Returns:
        updated store dict (not yet saved — caller must call save_store)
    """
    ocr_text     = (ocr_text     or "").strip()
    correct_text = (correct_text or "").strip()
    if not ocr_text or not correct_text:
        return store

    # Write the correction to the appropriate dict
    if field_type == "name":
        store["name_corrections"][ocr_text] = correct_text
        # Keep client_name_map in sync (it's a superset of name_corrections)
        store["client_name_map"][ocr_text]  = correct_text
    else:
        store["item_corrections"][ocr_text] = correct_text

    # Layer 3 engine accuracy (when per-engine readings are available)
    if engine_verdicts:
        es = store.setdefault("engine_stats", copy.deepcopy(_DEFAULT_ENGINE_STATS))
        for eng_name, reading in engine_verdicts.items():
            ek = _normalize_engine_key(eng_name)
            if ek not in es:
                es[ek] = {"correct": 0, "wrong": 0}
            if reading is not None:
                r = reading.strip()
                if r == correct_text:
                    es[ek]["correct"] += 1
                elif r == ocr_text:
                    # engine produced the wrong (old) value
                    es[ek]["wrong"] += 1

    return store


def get_stats(store: dict) -> dict:
    """Return a human-readable summary dict of the learning store state."""
    s  = store.get("stats", {})
    es = store.get("engine_stats", {})

    engine_summary: dict = {}
    for eng, counts in es.items():
        total = counts.get("correct", 0) + counts.get("wrong", 0)
        acc   = round(counts["correct"] / total * 100, 1) if total else None
        engine_summary[eng] = {
            "correct":      counts.get("correct", 0),
            "wrong":        counts.get("wrong",   0),
            "total":        total,
            "accuracy_pct": acc,
        }

    return {
        "name_corrections":        len(store.get("name_corrections", {})),
        "item_corrections":        len(store.get("item_corrections", {})),
        "client_name_map_entries": len(store.get("client_name_map",  {})),
        "total_processed":         s.get("total_processed", 0),
        "total_confirmed":         s.get("total_confirmed", 0),
        "total_flagged":           s.get("total_flagged",   0),
        "last_run":                s.get("last_run"),
        "engine_stats":            engine_summary,
    }


def compact_store(store: dict) -> dict:
    """
    Deduplicate and clean up the store in-place:
    - Remove no-op corrections (where key == value — nothing to correct)
    - Remove entries with empty keys or values
    - Sync client_name_map with name_corrections (add missing entries)

    Returns the cleaned store.
    """
    for d_key in ("name_corrections", "item_corrections"):
        store[d_key] = {
            k: v
            for k, v in store.get(d_key, {}).items()
            if k and v and k.strip() != v.strip()
        }

    # client_name_map is a superset — add anything in name_corrections not yet there
    cnm = store.setdefault("client_name_map", {})
    for k, v in store.get("name_corrections", {}).items():
        if k not in cnm:
            cnm[k] = v

    return store


# ── Internal helpers ──────────────────────────────────────────────────────────

def _normalize_engine_key(name: str) -> str:
    """
    Map raw engine source strings (from _source/_source fields) to the
    canonical keys used in engine_stats.

    Examples:
      "tesseract_structured" → "tesseract_structured"
      "tesseract_grid"       → "tesseract_structured"
      "google_drive"         → "google_drive"
      "paperless"            → "paperless"
      "claude_vision"        → "claude_vision"
    """
    n = (name or "").lower().strip().replace(" ", "_")
    if "tesseract" in n:
        return "tesseract_structured"
    if "google" in n or "gdrive" in n or "drive" in n:
        return "google_drive"
    if "paperless" in n:
        return "paperless"
    if "claude" in n:
        return "claude_vision"
    return n


# ── CLI (quick stats check) ───────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    from pathlib import Path

    path = sys.argv[1] if len(sys.argv) > 1 else str(
        Path.home() / "Desktop" / "REX" / "goj_menu_learning.json"
    )
    store = load_store(path)
    stats = get_stats(store)

    print(f"\n{'='*55}")
    print(f"  GOJ OCR Learning Store — {Path(path).name}")
    print(f"{'='*55}")
    print(f"  Name corrections:     {stats['name_corrections']}")
    print(f"  Item corrections:     {stats['item_corrections']}")
    print(f"  Client name map:      {stats['client_name_map_entries']}")
    print(f"  Total processed:      {stats['total_processed']}")
    print(f"  Total confirmed:      {stats['total_confirmed']}")
    print(f"  Total flagged:        {stats['total_flagged']}")
    print(f"  Last run:             {stats['last_run'] or 'never'}")
    print(f"\n  Engine accuracy:")
    for eng, e in stats["engine_stats"].items():
        acc = f"{e['accuracy_pct']}%" if e["accuracy_pct"] is not None else "no data"
        print(f"    {eng:<28} {e['correct']:>3}✓ {e['wrong']:>3}✗  {acc}")
    print(f"{'='*55}\n")
