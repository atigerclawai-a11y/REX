#!/usr/bin/env python3
# Skip Drive authentication, process existing scans in ~/Desktop/REX/scans_cache/ only

import sys
import os
sys.path.insert(0, "/Users/mainsobhelper/Desktop/REX")

from goj_drive_signature_pipeline import build_learning_comparisons
from goj_signature_extractor import learning_report

# Build new comparisons from existing scans (if any in cache)
print(f"[START] Running local-only signature processing")
result = build_learning_comparisons()
lr_data = result[0].strip if isinstance(result, list) and len(result) >= 1 else "no output"

import json; print(json.dumps(lr_data[:2000], indent=2))


print(f"[RESULTS] Comparisons done: {result}")
