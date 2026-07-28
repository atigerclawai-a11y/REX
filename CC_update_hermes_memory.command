#!/usr/bin/env bash
# CC_update_hermes_memory.command — write current AI model facts to Hermes memory
LOG="$HOME/Desktop/REX/logs/cc_update_hermes_memory.log"
mkdir -p "$HOME/Desktop/REX/logs"
exec > >(tee "$LOG") 2>&1

MEMORIES="$HOME/.hermes/profiles/cloud/memories"
MEMORY_FILE="$MEMORIES/MEMORY.md"
YAML="$HOME/.hermes/profiles/cloud/config.yaml"

echo "══════════════════════════════════"
echo "  Hermes Memory Update"
echo "══════════════════════════════════"
echo ""

echo "── Current MEMORY.md ──"
wc -c "$MEMORY_FILE"
echo ""

echo "── Backup ──"
cp "$MEMORY_FILE" "${MEMORY_FILE}.bak_$(date +%Y%m%d_%H%M%S)" && echo "Backed up"

echo ""
echo "── Updating MEMORY.md ──"
python3 - "$MEMORY_FILE" <<'EOF'
import sys, re

path = sys.argv[1]
content = open(path).read()

# Split into entries (§ separator)
entries = [e.strip() for e in content.split('§') if e.strip()]

print(f"Current entries: {len(entries)}")
for i, e in enumerate(entries):
    print(f"  [{i}] {e[:80]}...")

# Remove redundant VITAL entries at the end (already covered by earlier entries)
# These are: "[VITAL] GOJ transition agent must be built..." and "[VITAL] Always address user..."
entries = [e for e in entries if not (
    e.startswith('[VITAL] GOJ transition agent must be built') or
    e.startswith('[VITAL] Always address user as Kato')
)]

# Remove any existing AI model facts entry (to replace it)
entries = [e for e in entries if not e.startswith('AI models') and not e.startswith('Gateway models') and not e.startswith('Model routing')]

print(f"\nAfter cleanup: {len(entries)} entries")

# Add compact AI model facts entry
model_entry = (
    "AI models (May 2026): Gateway primary = DeepSeek V4 Pro (direct, api.deepseek.com). "
    "Fallback 1 = claude-opus-4-7 (Anthropic). Fallback 2 = gemini-3.5-flash (Google). "
    "Latest Anthropic model strings: claude-opus-4-6, claude-sonnet-4-6, claude-haiku-4-5-20251001. "
    "No OpenRouter. Direct subscriptions for DeepSeek/Anthropic/Google."
)
entries.append(model_entry)

new_content = '\n§\n'.join(entries)
char_count = len(new_content)
print(f"New char count: {char_count}")

open(path, 'w').write(new_content)
print("✅ MEMORY.md updated")
EOF

echo ""
echo "── New MEMORY.md ──"
cat "$MEMORY_FILE"
echo ""
echo "Char count: $(wc -c < "$MEMORY_FILE")"

echo ""
echo "── Increase memory_char_limit in config.yaml ──"
python3 - "$YAML" <<'EOF'
import sys, yaml

path = sys.argv[1]
cfg = yaml.safe_load(open(path)) or {}

mem = cfg.get("memory", {})
old_limit = mem.get("memory_char_limit", 2200)
new_limit = 2800
mem["memory_char_limit"] = new_limit
old_user = mem.get("user_char_limit", 1375)
mem["user_char_limit"] = 1600
cfg["memory"] = mem

with open(path, "w") as f:
    yaml.dump(cfg, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

print(f"✅ memory_char_limit: {old_limit} → {new_limit}")
print(f"✅ user_char_limit: {old_user} → 1600")
EOF

echo ""
echo "── Restarting gateway (clean kill) ──"
PLIST="$HOME/Library/LaunchAgents/ai.hermes.gateway-cloud.plist"
launchctl unload "$PLIST" 2>/dev/null && echo "Unloaded"
# Explicitly kill any surviving gateway process so Telegram token fully releases
pkill -f "hermes_cli.main.*gateway" 2>/dev/null && echo "Killed stale gateway processes" || echo "(no stale processes)"
sleep 8
launchctl load "$PLIST" && echo "Loaded"
sleep 8

echo ""
launchctl list | grep "ai.hermes.gateway-cloud"
tail -6 "$HOME/.hermes/profiles/cloud/logs/gateway.log" 2>/dev/null

echo ""
echo "Done. Memory updated with current AI model facts."
sleep 8
