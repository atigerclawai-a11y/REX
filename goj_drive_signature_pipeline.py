#!/usr/bin/env python3
"""
GOJ Drive Signature Pipeline
Downloads scanned sign-in sheet PDFs from Google Drive, 
extracts signatures, and builds the learning database.

Designed to run on the Mac Mini (where Google Drive credentials live).
Intended paths: ~/Desktop/REX/

Usage:
    python3 goj_drive_signature_pipeline.py --days 7
    python3 goj_drive_signature_pipeline.py --folder-id <drive_folder_id>
    python3 goj_drive_signature_pipeline.py --rebuild-learning
"""

import argparse
import json
import os
import sys
import sqlite3
import hashlib
import shutil
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

# ── Configuration ──────────────────────────────────────────────
REX_DIR = os.path.expanduser("~/Desktop/REX/")
DB_PATH = os.path.join(REX_DIR, "auth_tracker.db")
SIGNATURE_DIR = os.path.join(REX_DIR, "signatures/")
CREDS_PATH = os.path.join(REX_DIR, "google_credentials.json")
TOKEN_PATH = os.path.join(REX_DIR, "google_token.json")
SCANS_CACHE = os.path.join(REX_DIR, "scans_cache/")

# Google Drive folder names to search for sign-in sheets
SIGNIN_FOLDERS = [
    "Sign-in Sheets",
    "Attendance",
    "Daily Sign-in",
    "Scanned Documents",
]

SCOPES = [
    "https://www.googleapis.com/auth/drive.readonly",
    "https://www.googleapis.com/auth/drive.metadata.readonly",
]


def get_drive_service():
    """Authenticate and return Google Drive service."""
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build

    creds = None
    if os.path.exists(TOKEN_PATH):
        creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(CREDS_PATH, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(TOKEN_PATH, "w") as token:
            token.write(creds.to_json())

    return build("drive", "v3", credentials=creds)


def find_signin_pdfs(service, days_back: int = 7, folder_id: str = None) -> list[dict]:
    """Find sign-in sheet PDFs in Google Drive."""
    from googleapiclient.errors import HttpError

    if folder_id:
        query = f"'{folder_id}' in parents and mimeType='application/pdf'"
    else:
        # Search by date and name pattern
        cutoff = (datetime.now() - timedelta(days=days_back)).isoformat() + "Z"
        name_patterns = " or ".join([
            "name contains 'sign-in'",
            "name contains 'signin'",
            "name contains 'sign_in'",
            "name contains 'attendance'",
        ])
        query = f"({name_patterns}) and mimeType='application/pdf' and modifiedTime > '{cutoff}'"

    results = []
    page_token = None
    while True:
        response = service.files().list(
            q=query,
            spaces="drive",
            fields="nextPageToken, files(id, name, createdTime, modifiedTime, parents)",
            pageToken=page_token,
            pageSize=100,
        ).execute()

        for f in response.get("files", []):
            # Filter: only files that look like sign-in sheets (not templates)
            name_lower = f["name"].lower()
            if any(kw in name_lower for kw in ["sign-in", "signin", "sign_in", "attendance"]):
                if "template" not in name_lower:
                    results.append(f)

        page_token = response.get("nextPageToken")
        if not page_token:
            break

    return results


def download_pdf(service, file_id: str, dest_dir: str) -> str:
    """Download a PDF from Google Drive."""
    import io
    from googleapiclient.http import MediaIoBaseDownload

    request = service.files().get_media(fileId=file_id)
    fh = io.BytesIO()
    downloader = MediaIoBaseDownload(fh, request)

    done = False
    while not done:
        _, done = downloader.next_chunk()

    fh.seek(0)
    dest_path = os.path.join(dest_dir, f"{file_id}.pdf")
    with open(dest_path, "wb") as f:
        f.write(fh.read())

    return dest_path


def run_signature_pipeline(days_back: int = 7, folder_id: str = None, rebuild_learning: bool = False):
    """
    Full pipeline:
    1. Find scanned sign-in PDFs on Google Drive
    2. Download them
    3. Extract signatures
    4. Build learning comparisons
    """
    print("=" * 60)
    print("GOJ Signature Pipeline — Batch Extraction")
    print(f"  Time: {datetime.now().isoformat()}")
    print(f"  Lookback: {days_back} days")
    print("=" * 60)

    # Setup
    Path(SCANS_CACHE).mkdir(parents=True, exist_ok=True)
    Path(SIGNATURE_DIR, "samples").mkdir(parents=True, exist_ok=True)
    Path(SIGNATURE_DIR, "learning").mkdir(parents=True, exist_ok=True)

    # Init DB tables
    from goj_signature_extractor import ensure_db
    ensure_db()

    # Auth
    print("\n🔐 Authenticating with Google Drive...")
    service = get_drive_service()
    print("   ✓ Authenticated")

    # Find PDFs
    print(f"\n🔍 Searching for sign-in PDFs (last {days_back} days)...")
    pdfs = find_signin_pdfs(service, days_back, folder_id)
    print(f"   Found {len(pdfs)} PDFs")

    if not pdfs:
        print("   No sign-in PDFs found. Nothing to extract.")
        return

    # Download and extract
    total_signatures = 0
    for i, pdf_meta in enumerate(pdfs):
        print(f"\n📄 [{i+1}/{len(pdfs)}] {pdf_meta['name']}")

        # Determine date from filename or metadata
        created = pdf_meta.get("createdTime", "")[:10]
        date_str = created

        # Try to parse date from filename
        import re
        date_match = re.search(r"(\d{4}[-_]\d{2}[-_]\d{2})", pdf_meta["name"])
        if date_match:
            date_str = date_match.group(1).replace("_", "-")

        # Download
        local_path = download_pdf(service, pdf_meta["id"], SCANS_CACHE)
        print(f"   Downloaded → {local_path}")

        # Extract signatures
        from goj_signature_extractor import extract_from_pdf
        result = extract_from_pdf(local_path, date_str)
        sigs = result["signatures_found"]
        total_signatures += sigs
        print(f"   Extracted {sigs} signatures")

        # Clean up downloaded PDF (keep cache size bounded)
        os.remove(local_path)

    print(f"\n✅ Pipeline complete — {total_signatures} total signatures extracted")

    # Build learning comparisons
    if rebuild_learning or total_signatures > 0:
        print("\n🧠 Building learning comparisons...")
        build_learning_comparisons()

    # Print report
    from goj_signature_extractor import learning_report
    report = learning_report()
    print("\n📊 Signature Learning Report:")
    print(f"   Total samples: {report['total_samples']}")
    print(f"   Unique clients: {report['unique_clients']}")
    print(f"   Learning records: {report['learning_records']}")
    print(f"   Quality breakdown: {report['quality_counts']}")


def build_learning_comparisons():
    """
    Compare new signatures against known samples for the same client.
    Populates signature_review_learning with similarity scores.
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Get all clients with multiple signature samples
    cursor.execute("""
        SELECT client_id, client_name, COUNT(*) as cnt
        FROM signature_sample_registry
        WHERE quality_label != 'missing'
        GROUP BY client_id
        HAVING cnt >= 2
    """)
    multi_sample_clients = cursor.fetchall()

    learning_count = 0
    for client_id, client_name, cnt in multi_sample_clients:
        # Get all samples for this client, ordered by date
        cursor.execute("""
            SELECT id, image_crop_path, dark_pixels, quality_label, source_date
            FROM signature_sample_registry
            WHERE client_id = ? AND quality_label != 'missing'
            ORDER BY source_date DESC
        """, (client_id,))

        samples = cursor.fetchall()

        # Compare each pair
        for i in range(len(samples)):
            for j in range(i + 1, len(samples)):
                sample_a = samples[i]
                sample_b = samples[j]

                # Calculate similarity
                similarity = compare_signature_images(sample_a[1], sample_b[1])

                # Record learning entry for the newer sample compared to the older
                newer_sample = sample_a if sample_a[4] >= sample_b[4] else sample_b
                older_sample = sample_b if sample_a[4] >= sample_b[4] else sample_a

                cursor.execute("""
                    INSERT OR IGNORE INTO signature_review_learning
                    (client_id, client_name, signature_crop_path, signature_quality_score,
                     signature_similarity_score, compared_to_signature_id, learning_status)
                    VALUES (?, ?, ?, ?, ?, ?, 'auto_compared')
                """, (
                    client_id, client_name,
                    newer_sample[1],
                    _quality_to_score(newer_sample[3]),
                    similarity,
                    older_sample[0]
                ))
                learning_count += 1

    conn.commit()
    conn.close()
    print(f"   Generated {learning_count} learning comparisons")


def compare_signature_images(path_a: str, path_b: str) -> float:
    """
    Compare two signature images and return a similarity score (0-1).
    Uses simple pixel-based comparison with alignment tolerance.
    """
    try:
        from PIL import Image
        import numpy as np

        img_a = Image.open(path_a).convert("L")
        img_b = Image.open(path_b).convert("L")

        # Resize to common dimensions
        target_size = (200, 60)
        img_a = img_a.resize(target_size, Image.LANCZOS)
        img_b = img_b.resize(target_size, Image.LANCZOS)

        # Binarize
        arr_a = np.array(img_a) < 128
        arr_b = np.array(img_b) < 128

        # Calculate overlap
        intersection = np.sum(arr_a & arr_b)
        union = np.sum(arr_a | arr_b)

        if union == 0:
            return 0.0

        jaccard = intersection / union

        # Also compare dark pixel density ratio
        density_a = np.sum(arr_a) / arr_a.size
        density_b = np.sum(arr_b) / arr_b.size
        density_ratio = min(density_a, density_b) / max(density_a, density_b) if max(density_a, density_b) > 0 else 0

        # Combined score (weighted)
        score = (jaccard * 0.6) + (density_ratio * 0.4)
        return round(min(1.0, max(0.0, score)), 4)

    except Exception as e:
        return 0.0


def _quality_to_score(quality: str) -> float:
    """Convert quality label to numeric score."""
    return {"clear": 0.9, "partial": 0.5, "faint": 0.3, "missing": 0.0}.get(quality, 0.5)


def main():
    parser = argparse.ArgumentParser(description="GOJ Drive Signature Pipeline")
    parser.add_argument("--days", type=int, default=7,
                        help="Days back to search for sign-in PDFs (default: 7)")
    parser.add_argument("--folder-id", help="Specific Google Drive folder ID")
    parser.add_argument("--rebuild-learning", action="store_true",
                        help="Rebuild all learning comparisons")
    parser.add_argument("--dry-run", action="store_true",
                        help="List files without downloading")
    args = parser.parse_args()

    if args.dry_run:
        service = get_drive_service()
        pdfs = find_signin_pdfs(service, args.days, args.folder_id)
        print(f"Found {len(pdfs)} sign-in PDFs:")
        for f in pdfs:
            print(f"  {f['name']} ({f['id']}) — {f.get('createdTime', '?')[:10]}")
        return

    run_signature_pipeline(
        days_back=args.days,
        folder_id=args.folder_id,
        rebuild_learning=args.rebuild_learning,
    )


if __name__ == "__main__":
    main()
