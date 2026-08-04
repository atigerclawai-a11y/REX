#!/usr/bin/env python3
"""Verify: which docs are menus vs sign-in; which 006880 forms already applied."""
import json
import sqlite3
from pathlib import Path

# 1. Which July 29-31 docs have blank_parse dirs at all
BASE = Path('/Users/mainsobhelper/Desktop/REX/blank_parse')
for d in sorted(BASE.iterdir()):
    if d.is_dir() and d.name.startswith('doc'):
        print(d.name)
