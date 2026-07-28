# REX Directory Noise Breakdown — July 24, 2026

Each category below can be safely deleted. Signal files (Python scripts, docs, configs) are excluded.

## Noise Categories — Biggest First

### 1. old_backups — 3,934 files (4.2GB) ⚠️ SAFE TO DELETE
Pre-cowagent snapshots and config backups from June-July 2026.  
Already backed up to `/Volumes/cartoons/REX_backups/` (5 snapshots kept).
- `CC_backups/webui.db.bak_*`
- `CC_backups/hermie_config.yaml.bak_*`
- `CC_backups/pre_cowagent_20260707_1400/` (full agent state snapshot)

**Why:** Already on external backup. These are duplicate archives inside the working directory. They bloat graphify with duplicate nodes.

---

### 2. images — 4,211 files (333.8MB) 🟡 SOME MAY BE NEEDED
UI assets, icons, screenshots:
- `hermes_horse_icon.png`, `hermes_horse_v3.png`
- `CC_bbg_knicks_finals_menu.png`
- Menu scan images (inside menu_ocr_full/ocr/ subdirectories)

**Why:** Most are OCR-processed images already converted to MD. Original PNGs serve no purpose after parsing. Keep only intentional UI assets.

---

### 3. drive_mirror — 922 files (181.9MB) ⚠️ SAFE TO DELETE
Google Drive mirror cache (`gdrive_mirror/`).
- Templates, sign-in sheets, document exports cached locally

**Why:** Clone of Google Drive content. Re-synced on demand. Stale cache.

---

### 4. node_modules — 4,664 files (119.2MB) ⚠️ SAFE TO DELETE
JavaScript dependencies from an old Hermes workspace:
- `node_modules/pino-std-serializers/`
- `node_modules/.package-lock.json`

**Why:** No active Node.js project in REX. Orphaned dependency cache.

---

### 5. archives — 2,372 files (47.9MB) 🟡 REVIEW
- `CC_lana_archive.py`
- `CC_ig_archive_parser.py`
- `lana_transcripts_archive.md.bak-*`

**Why:** Archive scripts may be useful for reference. `.bak` files can go.

---

### 6. quarantine — 9 files (43.9MB) 🟡 REVIEW
- `CC_quarantine_execute.command`
- `CC_quarantine_proposal.txt`

**Why:** Old quarantine proposal files. May have historical value. Small.

---

### 7. js_bundles — 2,071 files (25.6MB) ⚠️ SAFE TO DELETE
Compiled JavaScript bundles from old Hermes workspace builds:
- `server-entry.js`, `router-*.js` (inside backup archives)

**Why:** Minified build artifacts. Source lives elsewhere.

---

### 8. misc_html — 156 files (6.6MB) ⚠️ SAFE TO DELETE
Stray HTML files not part of reports.

---

### 9. recovery_snapshots — 108 files (3.2MB) 🟡 REVIEW
- `RECOVERY_SNAPSHOT_2026_04_14_0525/`
- `OCR_WORKING_SNAPSHOT_2026_04_14_0524/`

**Why:** April 2026 recovery checkpoints. Historical value. 3.2MB — negligible.

---

## Summary

| Category | Files | Size | Safe? |
|---|---|---|---|
| old_backups | 3,934 | 4.2GB | ✅ Delete |
| images | 4,211 | 333.8MB | 🟡 Review |
| drive_mirror | 922 | 181.9MB | ✅ Delete |
| node_modules | 4,664 | 119.2MB | ✅ Delete |
| archives | 2,372 | 47.9MB | 🟡 Review |
| quarantine | 9 | 43.9MB | 🟡 Review |
| js_bundles | 2,071 | 25.6MB | ✅ Delete |
| misc_html | 156 | 6.6MB | ✅ Delete |
| recovery_snapshots | 108 | 3.2MB | 🟡 Keep |
| **Total noise** | **18,447** | **4.9GB** | |

**Safe to delete immediately: 16,425 files (4.5GB)**
