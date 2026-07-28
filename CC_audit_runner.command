#!/bin/bash
# CC_audit_runner.command
# Gold Health Systems — June 4 2026 System Audit
# Runs on Mac, writes results to CC_audit_raw_results.txt in Desktop/REX

OUT="$HOME/Desktop/REX/CC_audit_raw_results.txt"
exec > >(tee "$OUT") 2>&1

echo "╔══════════════════════════════════════════════════════╗"
echo "  GHS SYSTEM AUDIT — $(date)"
echo "╚══════════════════════════════════════════════════════╝"
echo ""

# ── TASK 1: TAILSCALE ──────────────────────────────────────
echo "═══ TASK 1: TAILSCALE ═══"
echo "--- tailscale status ---"
tailscale status 2>/dev/null || echo "tailscale CLI: not found"
echo "--- launchctl ---"
launchctl list 2>/dev/null | grep -i tailscale || echo "No tailscale in launchctl"
echo "--- pgrep ---"
pgrep -x tailscaled && echo "tailscaled: RUNNING" || echo "tailscaled: NOT running"
pgrep -a -i tailscale | head -5 || echo "No tailscale processes found"
ls /Applications/Tailscale.app 2>/dev/null && echo "Tailscale.app: EXISTS in /Applications" || echo "Tailscale.app: NOT in /Applications"
ls ~/Applications/Tailscale.app 2>/dev/null && echo "Tailscale.app: EXISTS in ~/Applications" || echo "Tailscale.app: NOT in ~/Applications"
which tailscale 2>/dev/null || echo "tailscale: not in PATH"
echo ""

# ── TASK 2: OLLAMA ────────────────────────────────────────
echo "═══ TASK 2: OLLAMA ═══"
echo "--- ollama list ---"
/usr/local/bin/ollama list 2>/dev/null || ollama list 2>/dev/null || echo "ollama: not found at /usr/local/bin or PATH"
echo "--- ollama path ---"
which ollama 2>/dev/null || echo "ollama not in PATH"
ls /usr/local/bin/ollama 2>/dev/null || echo "not at /usr/local/bin/ollama"
ls /opt/homebrew/bin/ollama 2>/dev/null || echo "not at /opt/homebrew/bin/ollama"
echo "--- pgrep ---"
pgrep -x ollama && echo "ollama: RUNNING" || echo "ollama: NOT running"
echo "--- ollama API (11434) ---"
curl -s --max-time 3 http://localhost:11434/api/tags 2>/dev/null | python3 -c "
import sys,json
try:
    d=json.load(sys.stdin)
    models=d.get('models',[])
    if models:
        print(f'  Ollama API: {len(models)} models found:')
        for m in models: print(f'    - {m[\"name\"]}')
    else:
        print('  Ollama API: running but no models')
except: print('  Ollama API: not reachable or bad JSON')
" 2>/dev/null || echo "Ollama API not reachable"
echo "--- LM Studio (1234) ---"
curl -s --max-time 3 http://localhost:1234/v1/models 2>/dev/null | python3 -c "
import sys,json
try:
    d=json.load(sys.stdin)
    models=d.get('data',[])
    if models:
        print(f'  LM Studio API: {len(models)} models:')
        for m in models: print(f'    - {m.get(\"id\",\"?\")}')
    else:
        print('  LM Studio API: running but empty')
except: print('  LM Studio API: not reachable')
" 2>/dev/null || echo "LM Studio API not reachable"
echo ""

# ── TASK 3: KARPATHY AUTORESEARCH ───────────────────────
echo "═══ TASK 3: KARPATHY AUTORESEARCH ═══"
echo "--- find Desktop / Documents ---"
find ~/Desktop ~/Documents ~ -maxdepth 5 \( -iname "*autorese*" -o -iname "*karpathy*" \) 2>/dev/null | head -30
echo "--- autoresearch dir ---"
ls ~/Desktop/autoresearch/ 2>/dev/null && echo "~/Desktop/autoresearch EXISTS" || echo "~/Desktop/autoresearch: NOT found"
ls ~/Desktop/microgpt/ 2>/dev/null && echo "~/Desktop/microgpt EXISTS" || echo "~/Desktop/microgpt: NOT found"
echo "--- launchctl auto ---"
launchctl list 2>/dev/null | grep -i auto | head -10 || echo "No 'auto' services in launchctl"
echo ""

# ── TASK 4: NOUS SKILLS ─────────────────────────────────
echo "═══ TASK 4: NOUS SKILLS ═══"
echo "--- .skill / .skills files ---"
find ~ -maxdepth 8 \( -name "*.skill" -o -name "*.skills" \) 2>/dev/null | head -20
echo "--- ~/.hermes/skills/ ---"
ls ~/.hermes/skills/ 2>/dev/null || echo "no ~/.hermes/skills/"
echo "--- ~/.hermes/profiles/cloud/skills/ ---"
ls ~/.hermes/profiles/cloud/skills/ 2>/dev/null || echo "no ~/.hermes/profiles/cloud/skills/"
echo "--- Hermes config skill references ---"
grep -i "skill" ~/.hermes/profiles/cloud/config.yaml 2>/dev/null || echo "no skill refs in config.yaml"
echo ""

# ── TASK 5: OBSIDIAN VAULT ──────────────────────────────
echo "═══ TASK 5: OBSIDIAN VAULT ═══"
echo "--- find .obsidian dirs ---"
find ~ -maxdepth 8 -name ".obsidian" -type d 2>/dev/null | head -15
echo "--- iCloud Obsidian ---"
ls ~/Library/Mobile\ Documents/iCloud\~md\~obsidian/ 2>/dev/null && echo "iCloud Obsidian path EXISTS" || echo "iCloud Obsidian: not found"
ls ~/Library/Mobile\ Documents/iCloud\~md\~obsidian/Documents/ 2>/dev/null | head -20 || true
echo "--- ~/Documents/Obsidian ---"
ls ~/Documents/Obsidian/ 2>/dev/null | head -20 || echo "~/Documents/Obsidian not found"
echo "--- Obsidian app support ---"
ls ~/Library/Application\ Support/obsidian/ 2>/dev/null | head -20 || echo "No Obsidian app support dir"
echo ""

# ── TASK 6: BACKUP INVENTORY ────────────────────────────
echo "═══ TASK 6: BACKUP TARGETS STATUS ═══"
echo "--- ~/.hermes/profiles/cloud/ ---"
ls ~/.hermes/profiles/cloud/ 2>/dev/null || echo "~/.hermes/profiles/cloud/ not accessible"
echo "--- ~/.hermes/state-snapshots/ ---"
ls ~/.hermes/state-snapshots/ 2>/dev/null || echo "~/.hermes/state-snapshots/ not found"
echo "--- ~/.hermes/config.yaml ---"
ls -la ~/.hermes/config.yaml 2>/dev/null || echo "~/.hermes/config.yaml not found"
ls -la ~/.hermes/config.yaml.bak.* 2>/dev/null || echo "No ~/.hermes/config.yaml.bak.* files"
echo "--- LaunchAgent plists ---"
ls -la ~/Library/LaunchAgents/ai.hermes.gateway-cloud.plist 2>/dev/null || echo "ai.hermes.gateway-cloud.plist not found"
ls -la ~/Library/LaunchAgents/com.ghs.dock-fix.plist 2>/dev/null || echo "com.ghs.dock-fix.plist not found"
echo "--- Desktop/REX backend ---"
ls ~/Desktop/REX/backend/ 2>/dev/null | wc -l | xargs echo "REX backend files:"
echo ""

# ── TASK 7: HERMES DESKTOP APP ──────────────────────────
echo "═══ TASK 7: HERMES DESKTOP APP ═══"
echo "--- hermes-workspace in Applications ---"
ls ~/Applications/ 2>/dev/null | grep -i hermes || echo "Nothing hermes in ~/Applications/"
ls /Applications/ 2>/dev/null | grep -i hermes || echo "Nothing hermes in /Applications/"
echo "--- find hermes-workspace / Hermes.app / hermes-desktop ---"
find ~/Applications /Applications ~/Desktop ~/Documents ~/Library -maxdepth 6 \
  \( -name "hermes-workspace*" -o -name "Hermes.app" -o -name "hermes-desktop*" \) 2>/dev/null \
  | grep -v "\.hermes/hermes-agent" | head -30
echo "--- Library/Application Support hermes ---"
ls ~/Library/Application\ Support/ 2>/dev/null | grep -i hermes | head -20
echo "--- Library/Logs hermes-workspace ---"
find ~/Library/Logs ~/Library/Caches -maxdepth 5 \
  \( -name "*hermes*workspace*" -o -name "*hermes*desktop*" \) 2>/dev/null | head -20
echo "--- hermes-workspace plist ---"
ls ~/Library/LaunchAgents/ 2>/dev/null | grep -i "workspace\|hermes-desk" || echo "No workspace/hermes-desk plists"
echo "--- ~/.config hermes ---"
ls ~/.config/ 2>/dev/null | grep -i hermes | head -10 || echo "No hermes in ~/.config/"
echo "--- hermes-workspace app bundle ---"
find ~ /Applications /usr -name "hermes-workspace" -type d 2>/dev/null | head -10
echo ""

# ── SERVICE HEALTH CHECK ────────────────────────────────
echo "═══ SERVICE HEALTH ═══"
curl -s --max-time 3 http://localhost:8080/health 2>/dev/null && echo " ← :8080 GOJ Dashboard" || echo ":8080 GOJ Dashboard: NOT responding"
curl -s --max-time 3 http://localhost:8000/health 2>/dev/null && echo " ← :8000 REX FastAPI" || echo ":8000 REX FastAPI: NOT responding"
curl -s --max-time 3 http://localhost:3002/health 2>/dev/null && echo " ← :3002 Hermes Cloud GW" || echo ":3002 Hermes Cloud GW: NOT responding"
echo "--- config.yaml modified time ---"
ls -la ~/.hermes/profiles/cloud/config.yaml 2>/dev/null
echo "--- config.yaml.bak files ---"
ls -la ~/.hermes/profiles/cloud/config.yaml.bak* 2>/dev/null || echo "No .bak files in cloud profile"
echo ""

echo "╔══════════════════════════════════════════════════════╗"
echo "  AUDIT COMPLETE — $(date)"
echo "  Results written to: $OUT"
echo "╚══════════════════════════════════════════════════════╝"
