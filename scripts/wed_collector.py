#!/usr/bin/env python3
"""Collect WED column (index 5) from Clients.aspx for the full roster — save raw."""
import json
import re
import sqlite3

# Merge any partial captures into one file
out_path = '/tmp/wed_collected.json'
collected = {}
try:
    collected = json.load(open(out_path))
except Exception:
    pass


def extract_from_current_page():
    import subprocess
    # Called from browser console instead — this is a stub for the collector script.
    return collected


print(f'collector: {len(collected)} entries so far')
