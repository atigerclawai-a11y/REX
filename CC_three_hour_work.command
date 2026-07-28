#!/bin/bash
# CC_three_hour_work.command
# Gold Health Systems — June 4 2026 3-Hour Work Session
# Tasks: full diagnostic, config diff, hermie→gemma4, obsidian log, GOJ working doc update
# PAE compliant — all changes are incremental and reversible

OUTDIR="$HOME/Desktop/REX"
LOG="$OUTDIR/logs/cc_threehour_$(date +%Y%m%d_%H%M%S).log"
mkdir -p "$OUTDIR/logs"
exec > >(tee "$LOG") 2>&1

echo "╔══════════════════════════════════════════════════════╗"
echo "  GHS 3-HOUR WORK SESSION — $(date)"
echo "╚══════════════════════════════════════════════════════╝"

# ═══════════════════════════════════════════════════════════
# TASK 10: FULL SYSTEM DIAGNOSTIC
# ═══════════════════════════════════════════════════════════
echo ""
echo "══ TASK 10: FULL SYSTEM DIAGNOSTIC ══════════════════"

echo "--- Service Health ---"
for port_label in "8080:GOJ_Dashboard" "8000:REX_FastAPI" "3002:Hermes_Cloud_GW" "11434:Ollama" "1234:LM_Studio" "27226:TigerClaw_API" "3000:OpenWebUI" "3080:LibreChat" "65001:Hermes_Local_GW"; do
  port="${port_label%%:*}"
  label="${port_label##*:}"
  result=$(curl -s --max-time 3 "http://localhost:$port/health" -o /dev/null -w "%{http_code}" 2>/dev/null)
  if [ "$result" = "200" ]; then
    echo "  ✅ :$port $label — HTTP $result"
  elif [ "$result" = "404" ]; then
    # Try root
    result2=$(curl -s --max-time 3 "http://localhost:$port/" -o /dev/null -w "%{http_code}" 2>/dev/null)
    echo "  ⚠️  :$port $label — /health 404, / returns $result2"
  elif [ -z "$result" ] || [ "$result" = "000" ]; then
    echo "  ❌ :$port $label — not responding"
  else
    echo "  ⚠️  :$port $label — HTTP $result"
  fi
done

echo ""
echo "--- launchctl GHS services ---"
launchctl list 2>/dev/null | grep -E "hermes|rex|goj|tiger|watchman|n8n|dock" | while read line; do
  pid=$(echo "$line" | awk '{print $1}')
  label=$(echo "$line" | awk '{print $3}')
  if [ "$pid" != "-" ] && [ "$pid" != "0" ]; then
    echo "  ✅ $label (PID $pid)"
  else
    code=$(echo "$line" | awk '{print $2}')
    if [ "$code" = "0" ]; then
      echo "  ⚪ $label (loaded, not running)"
    else
      echo "  ❌ $label (exit code $code)"
    fi
  fi
done

echo ""
echo "--- Hermes gateway log (last 20 lines) ---"
tail -20 ~/.hermes/profiles/cloud/logs/gateway.log 2>/dev/null || echo "  Cannot read gateway log"

echo ""
echo "--- REX FastAPI full health ---"
curl -s --max-time 5 http://localhost:8000/health 2>/dev/null | python3 -m json.tool 2>/dev/null || echo "REX health not reachable"

echo ""
echo "--- auth_tracker.db status ---"
DB="$HOME/Documents/goj files/dashboard/auth_tracker.db"
if [ -f "$DB" ]; then
  echo "  DB exists: $(ls -lh "$DB" | awk '{print $5, $6, $7, $8}')"
  echo "  Tables: $(sqlite3 "$DB" ".tables" 2>/dev/null)"
  echo "  Clients: $(sqlite3 "$DB" "SELECT COUNT(*) FROM clients;" 2>/dev/null)"
  echo "  Active auths: $(sqlite3 "$DB" "SELECT COUNT(*) FROM authorization WHERE status='ACTIVE';" 2>/dev/null)"
  echo "  Expired auths: $(sqlite3 "$DB" "SELECT COUNT(*) FROM authorization WHERE status='EXPIRED';" 2>/dev/null)"
  echo "  Client menus: $(sqlite3 "$DB" "SELECT COUNT(*) FROM client_menus;" 2>/dev/null)"
else
  echo "  ⚠️  auth_tracker.db not found at expected path"
fi

echo ""
echo "--- rex_memory.db status ---"
for db in ~/.rex/rex_memory.db ~/.rex/rex_user_model.db; do
  if [ -f "$db" ]; then
    size=$(ls -lh "$db" | awk '{print $5}')
    echo "  $db — $size"
  else
    echo "  $db — NOT FOUND"
  fi
done

echo ""
echo "--- Ollama model list ---"
ollama list 2>/dev/null || echo "ollama not reachable"

echo ""
echo "--- Disk usage key paths ---"
du -sh ~/.hermes/ 2>/dev/null | head -1
du -sh ~/.hermes-cloud/ 2>/dev/null | head -1
du -sh ~/Desktop/REX/ 2>/dev/null | head -1
du -sh ~/Documents/goj\ files/ 2>/dev/null | head -1

echo ""
echo "--- config.yaml last-modified times ---"
ls -la ~/.hermes/config.yaml 2>/dev/null
ls -la ~/.hermes/profiles/cloud/config.yaml 2>/dev/null

# ═══════════════════════════════════════════════════════════
# TASK 13: CONFIG DIFF — current vs pre-incident
# ═══════════════════════════════════════════════════════════
echo ""
echo "══ TASK 13: CONFIG DIFF ══════════════════════════════"
PRE="$HOME/.hermes/config.yaml.bak.20260604_124719"
CURR="$HOME/.hermes/config.yaml"
DIFF_OUT="$OUTDIR/CC_config_diff_june4.txt"

echo "Pre-incident: $PRE"
echo "Current:      $CURR"
echo ""
if [ -f "$PRE" ] && [ -f "$CURR" ]; then
  diff "$PRE" "$CURR" > "$DIFF_OUT" 2>&1
  lines=$(wc -l < "$DIFF_OUT")
  echo "Diff written to: $DIFF_OUT ($lines lines)"
  echo ""
  echo "--- Diff summary ---"
  diff "$PRE" "$CURR" | head -80
else
  echo "⚠️  One or both files missing"
fi

# Also copy both files to REX for inspection
cp "$PRE" "$OUTDIR/CC_config_pre_incident.yaml" 2>/dev/null && echo "Pre-incident config copied to REX"
cp "$CURR" "$OUTDIR/CC_config_current.yaml" 2>/dev/null && echo "Current config copied to REX"

# Profile-level config
cp ~/.hermes/profiles/cloud/config.yaml "$OUTDIR/CC_profile_config_current.yaml" 2>/dev/null && echo "Profile config copied to REX"

# ═══════════════════════════════════════════════════════════
# TASK 11: SWITCH HERMIE-LOCAL TO GEMMA4:26B
# ═══════════════════════════════════════════════════════════
echo ""
echo "══ TASK 11: HERMIE-LOCAL → GEMMA4:26B ════════════════"

# First read the profile config to understand current hermie-local setup
PROFILE_CONFIG="$HOME/.hermes/profiles/cloud/config.yaml"
echo "--- Current hermie-local config section ---"
grep -A 20 "hermie\|hermie-local\|hermie_local\|local.*hermie" "$PROFILE_CONFIG" 2>/dev/null | head -40 || echo "No hermie-local section found in profile config"
grep -A 20 "hermie\|hermie-local\|hermie_local\|local.*hermie" ~/.hermes/config.yaml 2>/dev/null | head -40 || echo "No hermie-local section found in root config"

# Copy profile config to REX so we can inspect and edit it
cp "$PROFILE_CONFIG" "$OUTDIR/CC_profile_config_before_gemma4.yaml" 2>/dev/null && echo "Profile config backed up before gemma4 switch"

echo ""
echo "--- Checking what model hermie-local currently uses ---"
grep -A5 -B2 "mistral-hermie\|hermie" "$PROFILE_CONFIG" 2>/dev/null | head -30

# ═══════════════════════════════════════════════════════════
# TASK 16: INVENTORY ~/hermes-workspace/
# ═══════════════════════════════════════════════════════════
echo ""
echo "══ TASK 16: INVENTORY ~/hermes-workspace/ ════════════"
HW="$HOME/Desktop/REX/CC_hermes_desktop_quarantine_20260604/hermes-workspace-home"
echo "Checking quarantine at: $HW"
if [ -d "$HW" ]; then
  echo "--- Contents (depth 3) ---"
  find "$HW" -maxdepth 3 -type f 2>/dev/null | head -40
  echo ""
  echo "--- Checking AUTORESEARCH.md ---"
  find "$HW" -name "AUTORESEARCH.md" 2>/dev/null | while read f; do
    echo "Found: $f"
    head -30 "$f"
  done
else
  # Maybe quarantine not done yet - check original path
  echo "Quarantine path not found. Checking ~/hermes-workspace/ directly..."
  if [ -d "$HOME/hermes-workspace" ]; then
    find "$HOME/hermes-workspace" -maxdepth 3 -type f 2>/dev/null | head -40
  else
    echo "~/hermes-workspace/ also not found (already quarantined successfully)"
  fi
fi

echo ""
echo "--- ~/Documents/autoresearch ---"
if [ -d "$HOME/Documents/autoresearch" ]; then
  ls "$HOME/Documents/autoresearch/" | head -20
  echo "README:" && head -20 "$HOME/Documents/autoresearch/README.md" 2>/dev/null || head -20 "$HOME/Documents/autoresearch/README" 2>/dev/null || echo "(no readme)"
fi

# ═══════════════════════════════════════════════════════════
# TASK 14: READ GOJ WORKING DOC
# ═══════════════════════════════════════════════════════════
echo ""
echo "══ TASK 14: GOJ WORKING DOC ══════════════════════════"
WD="$HOME/Documents/goj files/GOJ_WORKING_DOC.md"
if [ -f "$WD" ]; then
  echo "Working doc found: $(ls -lh "$WD" | awk '{print $5, $6, $7, $8}')"
  echo "--- Contents ---"
  cat "$WD"
  # Copy to REX for editing
  cp "$WD" "$OUTDIR/CC_GOJ_WORKING_DOC_current.md" && echo "Working doc copied to REX for editing"
else
  echo "Working doc not found at: $WD"
  find "$HOME/Documents" -name "GOJ_WORKING_DOC*" 2>/dev/null | head -5
fi

# ═══════════════════════════════════════════════════════════
# TASK 15: CHECK :8080 /health 404
# ═══════════════════════════════════════════════════════════
echo ""
echo "══ TASK 15: :8080 HEALTH ENDPOINT ═══════════════════"
echo "--- What :8080 exposes ---"
for route in "/" "/health" "/api/health" "/status" "/api/status" "/ping"; do
  code=$(curl -s --max-time 3 "http://localhost:8080$route" -o /dev/null -w "%{http_code}" 2>/dev/null)
  echo "  $route → HTTP $code"
done
echo ""
echo "--- Copy datarex app.py for inspection ---"
DATAREX="$HOME/.hermes-cloud/home/goj-pipeline/datarex/app.py"
if [ -f "$DATAREX" ]; then
  cp "$DATAREX" "$OUTDIR/CC_datarex_app_current.py" && echo "Copied datarex app.py to REX"
  echo "app.py routes:"
  grep -E "@app\.route|def.*route|blueprint" "$DATAREX" 2>/dev/null | head -30
else
  echo "datarex app.py not found at: $DATAREX"
fi

# ═══════════════════════════════════════════════════════════
# QUARANTINE VERIFICATION
# ═══════════════════════════════════════════════════════════
echo ""
echo "══ QUARANTINE VERIFICATION ══════════════════════════"
QDIR="$HOME/Desktop/REX/CC_hermes_desktop_quarantine_20260604"
echo "Quarantine dir contents:"
ls -la "$QDIR/" 2>/dev/null || echo "Quarantine dir not found"
echo ""
echo "Verifying hermes-workspace.app is GONE from /Applications:"
ls /Applications/hermes-workspace.app 2>/dev/null && echo "⚠️  STILL PRESENT" || echo "✅ Confirmed removed from /Applications"
echo "Verifying LaunchAgents are GONE:"
ls ~/Library/LaunchAgents/com.hermes.cloud-workspace.plist 2>/dev/null && echo "⚠️  STILL PRESENT" || echo "✅ Confirmed removed"
ls ~/Library/LaunchAgents/com.hermes.workspace.plist 2>/dev/null && echo "⚠️  STILL PRESENT" || echo "✅ Confirmed removed"

echo ""
echo "╔══════════════════════════════════════════════════════╗"
echo "  WORK SESSION PHASE 1 COMPLETE — $(date)"
echo "  Outputs written to: $OUTDIR"
echo "╚══════════════════════════════════════════════════════╝"
