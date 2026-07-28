#!/usr/bin/env bash
# Locate Hermes — start from the actual node process listening on 3001.
set -u
LOG="$HOME/Desktop/REX/logs/_find_hermes_config.log"
mkdir -p "$HOME/Desktop/REX/logs"
: > "$LOG"

{
  echo "── Hermes process inspection — $(date '+%Y-%m-%d %H:%M:%S') ──"
  echo
  echo "── PID listening on :3001 ──"
  PID=$(lsof -nP -iTCP:3001 -sTCP:LISTEN -t 2>/dev/null | head -1)
  echo "PID: $PID"
  if [ -n "$PID" ]; then
    echo
    echo "── cwd / command for that PID ──"
    ps -p "$PID" -o pid,command 2>/dev/null
    CWD=$(lsof -p "$PID" 2>/dev/null | awk '$4=="cwd"{print $9; exit}')
    echo "cwd: $CWD"
    echo
    echo "── files open by Hermes process (top ~30) ──"
    lsof -p "$PID" 2>/dev/null | awk 'NR>1 && $4 ~ /cwd|txt|[0-9]+u?w?r?/' | head -40
    echo
    if [ -n "$CWD" ] && [ -d "$CWD" ]; then
      echo "── env / config files in $CWD ──"
      find "$CWD" -maxdepth 4 \
        \( -name ".env" -o -name "*.env" -o -name "config.json" \
           -o -name "config.yaml" -o -name "config.yml" \
           -o -name "config.toml" -o -name "settings.json" \
           -o -name "settings.yaml" -o -name "settings.yml" \
           -o -name "package.json" \) \
        -not -path "*/node_modules/*" -not -path "*/.git/*" -not -path "*/.venv/*" \
        2>/dev/null

      echo
      echo "── files mentioning openrouter/kimi/moonshot/sk-or-v1/api_key/max_tokens in $CWD ──"
      grep -RIl -E "OPENROUTER|openrouter|MOONSHOT|moonshot|kimi[-_/]?k|sk-or-v1|api[_-]?key|max_tokens|MAX_TOKENS|context_window|context_length|baseURL" "$CWD" \
        --include="*.env" --include="*" \
        --exclude-dir=node_modules --exclude-dir=.git --exclude-dir=.venv --exclude-dir=venv \
        --exclude-dir=dist --exclude-dir=build --exclude="*.lock" --exclude="*.log" \
        2>/dev/null | head -25

      echo
      echo "── snippets from those files ──"
      while IFS= read -r f; do
        [ -z "$f" ] && continue
        echo
        echo "── $f ──"
        grep -nE "OPENROUTER|openrouter|MOONSHOT|moonshot|kimi[-_/]?k|sk-or-v1|api[_-]?key|max_tokens|MAX_TOKENS|context_window|context_length|baseURL|model[\":=]" "$f" 2>/dev/null | head -25
      done < <(grep -RIl -E "OPENROUTER|openrouter|MOONSHOT|moonshot|kimi[-_/]?k|sk-or-v1|api[_-]?key|max_tokens|MAX_TOKENS" "$CWD" \
        --include="*.env" --include="*.json" --include="*.yaml" --include="*.yml" \
        --include="*.toml" --include="*.py" --include="*.ts" --include="*.js" --include="*.mjs" \
        --exclude-dir=node_modules --exclude-dir=.git --exclude-dir=.venv --exclude-dir=venv \
        2>/dev/null)
    fi
  fi

  echo
  echo "── ALSO: anything Hermes-ish in /Applications, ~/Library/Application Support, ~/Documents ──"
  find /Applications "$HOME/Library/Application Support" "$HOME/Documents" -maxdepth 3 -iname "*hermes*" 2>/dev/null | head -15

  echo
  echo "── DONE ──"
} 2>&1 | tee -a "$LOG"

sleep 4
osascript -e 'tell application "Terminal" to close (every window whose name contains "_find_hermes_config")' >/dev/null 2>&1 || true
