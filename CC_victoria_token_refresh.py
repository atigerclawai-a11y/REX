#!/usr/bin/env python3
"""Victoria token refresh — pings Google Drive daily at 13:00 to keep OAuth token warm before the 14:00 caller run."""
import sys
from pathlib import Path

REX_DIR = Path.home() / "Desktop" / "REX"
sys.path.insert(0, str(REX_DIR))

try:
    from CC_goj_drive_ingest import get_services
    svc = get_services()
    # Touch the Drive API to refresh any cached tokens
    svc['drive'].files().list(pageSize=1, fields="files(id,name)").execute()
    print("Token refresh OK")
except Exception as e:
    print(f"Token refresh WARNING: {e}")
    sys.exit(0)  # Non-fatal — caller will try again at 14:00
