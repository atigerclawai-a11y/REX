#!/bin/bash
# CC_run_security_scan.command — GHS Security Suite
# Double-click to run full antivirus + malware scan on ~/Desktop/REX
LOG="$HOME/Desktop/REX/logs/security_scan.log"
exec > >(tee "$LOG") 2>&1

echo "=== GHS Security Scanner ==="
echo "Time: $(date)"
echo ""

source ~/.rex-venv/bin/activate 2>/dev/null || source ~/debate-chamber/.venv/bin/activate
cd "$HOME/Desktop/REX"

echo "Running FULL scan (antivirus + malware + heuristics)..."
echo ""
python CC_security_scanner.py full --deep

echo ""
echo "Scan complete. Results in: REX/logs/"
echo "Press Enter to close..."
read
