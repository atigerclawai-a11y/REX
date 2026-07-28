#!/bin/sh
# LOCAL knowledge bridge — FULL vault content (private info intact). For the air-gapped local build.
export KNOWLEDGE_SCOPE=local
exec /opt/homebrew/bin/python3.11 "/Users/mainsobhelper/Desktop/REX/ghs_knowledge_bridge.py"
