#!/bin/bash
# REX Backend launcher — avoids macOS TCC/sandbox venv detection issues
export VIRTUAL_ENV="/Users/mainsobhelper/Desktop/REX/.venv"
export PATH="$VIRTUAL_ENV/bin:$PATH"
unset PYTHONHOME
cd /Users/mainsobhelper/Desktop/REX
exec "$VIRTUAL_ENV/bin/python3.11" -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
