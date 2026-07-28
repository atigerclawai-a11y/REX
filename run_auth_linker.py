#!/usr/bin/env python3
"""
GOJ Authorization Document Linker
─────────────────────────────────
Does two things:
1. Scans documents/authorization/<ClientName>/ folders and registers any PDFs
   not yet in auth_documents table.
2. Auto-links unlinked auth_documents to authorization records by client name.

Usage: python3 run_auth_linker.py [--dry-run]
"""

import sqlite3
import os
import sys
from pathlib import Path
from difflib import get_close_matches

# ── Paths ─────────────────────────────────────────────────────────────────────
AUTH_DIR  = Path.home() / "Documents" / "goj files" / "dashboard" / "documents" / "authorization"
DB_PATH   = Path.home() / "Documents" / "goj files" / "dashboard" / "auth_tracker.db"

DRY_RUN = "--dry-run" in sys.argv


def normalize(name: str) -> str:
    return name.replace("_", " ").replace("-", " ").strip().lower()


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


# ── Step 1: Register untracked PDFs ──────────────────────────────────────────

def register_new_pdfs():
    conn = get_db()
    cur  = conn.cursor()

    cur.execute("SELECT stored_filename FROM auth_documents")
    already_in_db = {row[0] for row in cur.fetchall()}

    registered = 0
    skipped    = 0

    for client_folder in sorted(AUTH_DIR.iterdir()):
        if not client_folder.is_dir():
            continue
        client_name = client_folder.name.replace("_", " ")

        for pdf in client_folder.glob("*.pdf"):
            if pdf.name in already_in_db:
                skipped += 1
                continue

            rel_path = f"authorization/{client_folder.name}/{pdf.name}"
            size     = pdf.stat().st_size

            print(f"  REGISTER: {client_name} → {pdf.name}")
            if not DRY_RUN:
                cur.execute("""
                    INSERT INTO auth_documents
                        (client_name, doc_type, original_filename, stored_filename,
                         stored_path_relative, file_size_bytes, uploaded_by)
                    VALUES (?, 'AUTHORIZATION', ?, ?, ?, ?, 'auto_scan')
                """, (client_name, pdf.name, pdf.name, rel_path, size))
            registered += 1

    if not DRY_RUN:
        conn.commit()
    conn.close()

    print(f"\n  PDFs registered: {registered}  |  already tracked: {skipped}")
    return registered


# ── Step 2: Link auth_documents → authorization records ───────────────────────

def link_unlinked_docs():
    conn = get_db()
    cur  = conn.cursor()

    # Get all unlinked auth_documents
    cur.execute("""
        SELECT doc_id, client_name FROM auth_documents
        WHERE auth_id IS NULL
        ORDER BY client_name
    """)
    unlinked = cur.fetchall()

    if not unlinked:
        print("  No unlinked auth_documents found.")
        conn.close()
        return 0

    # Get all authorization records
    cur.execute("""
        SELECT auth_id, client_name, authorization_number,
               service_start_date, service_end_date, status
        FROM authorization
        ORDER BY client_name, service_end_date DESC
    """)
    all_auths = cur.fetchall()

    # Build name → auth list map (most recent first)
    from collections import defaultdict
    auth_map = defaultdict(list)
    for a in all_auths:
        auth_map[normalize(a["client_name"])].append(a)

    # Known client names for fuzzy matching
    all_auth_names = list(auth_map.keys())

    linked  = 0
    no_match = 0
    multi   = 0

    prev_client = None
    for doc in unlinked:
        doc_id      = doc["doc_id"]
        client_name = doc["client_name"]
        norm_name   = normalize(client_name)

        if client_name != prev_client:
            print(f"\n  Client: {client_name}")
            prev_client = client_name

        # Exact match first
        candidates = auth_map.get(norm_name, [])

        # Fuzzy fallback
        if not candidates:
            close = get_close_matches(norm_name, all_auth_names, n=1, cutoff=0.80)
            if close:
                candidates = auth_map[close[0]]
                print(f"    fuzzy match: '{client_name}' → '{close[0]}'")

        if not candidates:
            print(f"    ✗ No authorization record found for doc_id={doc_id}")
            no_match += 1
            continue

        # Prefer ACTIVE auth; otherwise most recent
        active = [a for a in candidates if str(a["status"]).upper() == "ACTIVE"]
        best   = active[0] if active else candidates[0]

        print(f"    ✓ Link doc_id={doc_id} → auth_id={best['auth_id']} "
              f"({best['authorization_number']} | "
              f"{best['service_start_date']}–{best['service_end_date']} | {best['status']})")

        if not DRY_RUN:
            cur.execute(
                "UPDATE auth_documents SET auth_id=? WHERE doc_id=?",
                (best["auth_id"], doc_id)
            )
        linked += 1

    if not DRY_RUN:
        conn.commit()
    conn.close()

    print(f"\n  Linked: {linked}  |  No match found: {no_match}")
    return linked, no_match


# ── Step 3: Summary of UNMATCHED folder ───────────────────────────────────────

def report_unmatched():
    unmatched_dir = AUTH_DIR / "UNMATCHED"
    if not unmatched_dir.exists():
        return
    files = list(unmatched_dir.glob("*.pdf"))
    if files:
        print(f"\n  ⚠️  UNMATCHED folder still has {len(files)} PDFs needing manual client assignment:")
        for f in files:
            print(f"    {f.name}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print(f"\n{'='*70}")
    print("GOJ Authorization Document Linker")
    print(f"Auth dir : {AUTH_DIR}")
    print(f"Database : {DB_PATH}")
    print(f"Dry run  : {DRY_RUN}")
    print(f"{'='*70}\n")

    if not DB_PATH.exists():
        print(f"ERROR: Database not found: {DB_PATH}")
        sys.exit(1)

    if not AUTH_DIR.exists():
        print(f"ERROR: Auth dir not found: {AUTH_DIR}")
        sys.exit(1)

    print("── Step 1: Registering new PDFs from authorization folders ──")
    register_new_pdfs()

    print("\n── Step 2: Linking auth_documents to authorization records ──")
    link_unlinked_docs()

    print("\n── Step 3: UNMATCHED folder status ──")
    report_unmatched()

    print(f"\n{'='*70}")
    print("Done. Refresh the dashboard to see linked documents on client pages.")
    print(f"{'='*70}\n")


if __name__ == "__main__":
    main()
