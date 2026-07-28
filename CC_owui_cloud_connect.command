#!/usr/bin/env bash
# CC_owui_cloud_connect.command
# Inspect open-webui container and reconnect it to hermes-cloud

LOG="$HOME/Desktop/REX/logs/cc_owui_cloud_connect.log"
mkdir -p "$HOME/Desktop/REX/logs"
exec > >(tee "$LOG") 2>&1

echo "══════════════════════════════════════════════════"
echo "  Open WebUI Cloud Reconnect — $(date '+%Y-%m-%d %H:%M:%S')"
echo "══════════════════════════════════════════════════"

echo ""
echo "── open-webui inspect (Cmd, Networks, Env) ──"
docker inspect open-webui 2>/dev/null | python3 -c "
import sys, json
d = json.load(sys.stdin)[0]
cfg = d['Config']
hcfg = d['HostConfig']
net = d['NetworkSettings']
print('Image:', cfg.get('Image',''))
print()
print('Env:')
for e in cfg.get('Env',[]): print(' ',e)
print()
print('Networks:', list(net['Networks'].keys()))
print()
print('Labels (relevant):')
for k,v in cfg.get('Labels',{}).items():
    if any(x in k.lower() for x in ['compose','project','service']): print(f'  {k}={v}')
print()
print('Mounts:')
for m in d.get('Mounts',[]): print(' ',m.get('Source',''),'->',m.get('Destination',''))
print()
print('Cmd:', cfg.get('Cmd'))
print('Entrypoint:', cfg.get('Entrypoint'))
"

echo ""
echo "── hermes-cloud inspect (Networks, relevant env) ──"
docker inspect hermes-cloud 2>/dev/null | python3 -c "
import sys, json
d = json.load(sys.stdin)[0]
cfg = d['Config']
net = d['NetworkSettings']
print('Networks:', list(net['Networks'].keys()))
print('Ports:', d['NetworkSettings']['Ports'])
print()
print('Relevant env:')
safe = ['GATEWAY','PORT','HOST','MODEL','OPENAI','API_URL','BASE_URL','HERMES']
for e in cfg.get('Env',[]):
    k = e.split('=')[0]
    if any(x in k.upper() for x in safe): print(' ',e)
"

echo ""
echo "── Check if containers share a Docker network ──"
docker network ls 2>/dev/null | head -10

echo ""
echo "── hermes-cloud accessible from host? ──"
# Try different paths
for PATH_TRY in "/" "/health" "/v1/models" "/api/v1/models"; do
  STATUS=$(curl -s --max-time 3 -o /dev/null -w "%{http_code}" "http://localhost:8643${PATH_TRY}" 2>/dev/null)
  echo "  localhost:8643${PATH_TRY}: HTTP $STATUS"
done

echo ""
echo "── hermes-cloud on 9120 (dashboard) ──"
STATUS=$(curl -s --max-time 3 -o /dev/null -w "%{http_code}" "http://localhost:9120/" 2>/dev/null)
BODY=$(curl -s --max-time 3 "http://localhost:9120/" | head -c 200)
echo "  HTTP $STATUS"
echo "  $BODY"

echo ""
echo "── Check open-webui docker-compose file ──"
# Check all possible compose files
for F in \
  "$HOME/hermes-cloud-workspace/docker-compose.yml" \
  "$HOME/hermes-workspace/docker-compose.yml" \
  "$HOME/hermes-webui/docker-compose.yml" \
  "$HOME/docker/open-webui/docker-compose.yml" \
  "$HOME/open-webui/docker-compose.yml"; do
  if [ -f "$F" ]; then
    echo "  Found: $F"
    grep -A 30 "open.webui\|openwebui\|open_webui" "$F" | head -40
  fi
done

echo ""
echo "── Fix: use Open WebUI API to add hermes-cloud connection ──"
# Try with empty API key (some setups don't require it)
MODELS_NO_KEY=$(curl -s --max-time 5 "http://localhost:8643/v1/models" 2>/dev/null | head -c 200)
if echo "$MODELS_NO_KEY" | grep -q "model\|data\|id"; then
  echo "  ✓ hermes-cloud accepts requests without key: $MODELS_NO_KEY"
  API_KEY_VAL=""
else
  echo "  hermes-cloud no-key response: $MODELS_NO_KEY"
  # Try with API_SERVER_KEY
  API_KEY_VAL=$(python3 -c "
from pathlib import Path
p = Path.home()/'.hermes'/'.env'
if p.exists():
  for raw in p.read_text().splitlines():
    line = raw.strip()
    if line.startswith('API_SERVER_KEY='):
      print(line.split('=',1)[1])
      break
" 2>/dev/null)
fi

echo ""
echo "── Shared network between containers? ──"
# See if open-webui can reach hermes-cloud via network alias
OWUI_NETWORK=$(docker inspect open-webui 2>/dev/null | python3 -c "import sys,json; d=json.load(sys.stdin)[0]; print(list(d['NetworkSettings']['Networks'].keys())[0] if d['NetworkSettings']['Networks'] else 'none')")
CLOUD_NETWORK=$(docker inspect hermes-cloud 2>/dev/null | python3 -c "import sys,json; d=json.load(sys.stdin)[0]; print(list(d['NetworkSettings']['Networks'].keys())[0] if d['NetworkSettings']['Networks'] else 'none')")
echo "  open-webui network: $OWUI_NETWORK"
echo "  hermes-cloud network: $CLOUD_NETWORK"

if [ "$OWUI_NETWORK" = "$CLOUD_NETWORK" ] && [ "$OWUI_NETWORK" != "none" ]; then
  echo "  ✓ Same network! Open WebUI can reach hermes-cloud by container name"
  echo "    Use: http://hermes-cloud:8643/v1 in Open WebUI settings"
else
  echo "  Different networks. Open WebUI should use: http://host.docker.internal:8643/v1"
fi

echo ""
echo "══ COMPLETE ══"
echo "Log: $LOG"
echo ""
sleep 4
