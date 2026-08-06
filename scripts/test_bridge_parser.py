#!/usr/bin/env python3
"""Test the fixed parser against all 6 existing MinerU outputs."""
import importlib.util
import sys

spec = importlib.util.spec_from_file_location(
    "signin_attendance_bridge",
    "/Users/mainsobhelper/.hermes/profiles/work/scripts/signin_attendance_bridge.py")
bridge = importlib.util.module_from_spec(spec)
# don't run main; just load the module (it has no side effects at import except mkdir)
spec.loader.exec_module(bridge)

import glob

for md in sorted(glob.glob('/Users/mainsobhelper/Desktop/REX/signin_ocr_full/*/ocr/*.md')):
    txt = open(md, errors='ignore').read()
    parsed = bridge.parse_signin_md(txt)
    print(f'{md.split("/")[-2]}: date={parsed["date"]} shift={parsed["shift"]} names={parsed["name_count"]}')
    if parsed['names']:
        print(f'   first 3: {parsed["names"][:3]}')
        print(f'   last 2: {parsed["names"][-2:]}')
