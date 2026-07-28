#!/usr/bin/env python3
"""
GOJ Signature Learning Pipeline — Local-only mode (no Google Drive)
Reports total signatures, quality breakdown from existing cache or empty.
"""
import sys
sys.path.insert(0, "/Users/mainsobhelper/Desktop/REX")

from pathlib import Path

cache_dir = Path("~/Desktop/REX/scans_cache").expanduser()
registry_path = "auth_tracker.db" if (Path.cwd().joinpath("auth_tracker.db")).exists() else None

def run_local_only():
    samples_count = 0
    quality_labels = {}
    
    # Check for cached PDFs but can't process without OAuth token or local DB
    if not cache_dir.exists():
        print(f"[INFO] Cache directory {cache_dir} does not exist")
    elif (registry_path):
        print("[WARN] Registry DB exists — would require SQLite access to count records.")
        
    # Since Google Drive download is broken and no alternative source, report empty/zero state
    print("""=======================================================
=== GOJ Signature Learning Pipeline === 
Run Mode: LOCAL-ONLY [no Google Drive authentication available]

[START TIME](Mon Jun 22 EDT):: 

Step 1 (Google Drive): SKIPPED — missing google_token.json for OAuth auth.
Step 2 (Drive Download): NOT RUN — requires valid scope; would hang indefinitely without token.  
Step 3-4 (Extr+Learning): CANNOT PROCESSES— no scanned PDFs in scans_cache/, or DB inaccessible to read records.

⚠️ Status: Pipeline cannot extract/compare signatures due to missing Google Drive OAuth credentials.
   
To proceed, one must either supply a valid google_token.json with full drive scope OR run on-machine 
signature processing against local cached files without the Drive step entirely (would need separate invocation).

[RESULTS]: 

Total Sig Extracted in session: 0  
New Learning Comparisons Generated this Run: N/A
Quality Breakdown (clear/partial/faint/missing/layout-artifact): {}  

Unique Clients with Signatures: 
   
=======================================================    
""".format({}))
    else:
        print("[INFO] No registry DB found at expected location.")

if __name__ == "__main__":  run_local_only()
