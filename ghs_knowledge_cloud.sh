#!/bin/sh
# CLOUD knowledge bridge — REDACTED vault content (secrets/PHI/phones/emails/client-ids stripped;
# PHI-marker lines withheld). Cloud writes are redacted + namespaced under "Cloud Backups/".
export KNOWLEDGE_SCOPE=cloud
exec /opt/homebrew/bin/python3.11 "/Users/mainsobhelper/Desktop/REX/ghs_knowledge_bridge.py"
