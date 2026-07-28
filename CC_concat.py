#!/usr/bin/env python3
"""Concatenate CC_append_large_party.md to bbg_lana_analysis.md"""
from pathlib import Path
main_file = Path("/Users/mainsobhelper/Desktop/REX/bbg_lana_analysis.md")
append_file = Path("/Users/mainsobhelper/Desktop/REX/CC_append_large_party.md")
with main_file.open("a") as f:
    f.write(append_file.read_text())
print(f"Appended. New line count:")
import subprocess
subprocess.run(["wc", "-l", str(main_file)])
