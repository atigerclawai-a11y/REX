#!/bin/bash
# CC_cf_add_rex_cname.sh — add rex.goldhealthsys.com + jarvis.goldhealthsys.com via Cloudflare API
# Run with: CF_TOKEN="<token>" bash CC_cf_add_rex_cname.sh
# Token needs scope: Zone:DNS:Edit on goldhealthsys.com
# Generate at: https://dash.cloudflare.com/profile/api-tokens → "Edit zone DNS" template

set -euo pipefail

TOKEN="${CF_TOKEN:?Set CF_TOKEN env var first}"
ZONE_NAME="goldhealthsys.com"
# (name target) pairs to add or update
declare -a RECORDS=(
    "rex|rex-goldhealthsys.netlify.app"
    "jarvis|jarvis-goldhealthsys.netlify.app"
)

CF_API="https://api.cloudflare.com/client/v4"
AUTH="Authorization: Bearer ${TOKEN}"

echo "→ Looking up zone id for ${ZONE_NAME}..."
ZONE_ID=$(curl -s -H "${AUTH}" "${CF_API}/zones?name=${ZONE_NAME}" | python3 -c "
import sys, json
d = json.load(sys.stdin)
if not d.get('success'):
    print(f\"ERR: {d.get('errors')}\", file=sys.stderr); exit(1)
results = d.get('result', [])
if not results:
    print(f\"ERR: zone {sys.argv[1]} not found\", file=sys.stderr); exit(1)
print(results[0]['id'])
" "${ZONE_NAME}")

if [ -z "${ZONE_ID}" ]; then
    echo "❌ Could not resolve zone id"; exit 1
fi
echo "  zone_id: ${ZONE_ID}"

for pair in "${RECORDS[@]}"; do
    RECORD_NAME="${pair%%|*}"
    RECORD_TARGET="${pair##*|}"
    echo
    echo "═══ ${RECORD_NAME}.${ZONE_NAME} → ${RECORD_TARGET} ═══"

    echo "→ Checking existing..."
    EXISTING=$(curl -s -H "${AUTH}" "${CF_API}/zones/${ZONE_ID}/dns_records?name=${RECORD_NAME}.${ZONE_NAME}" | python3 -c "
import sys, json
d = json.load(sys.stdin)
r = d.get('result', [])
for rec in r:
    print(f\"{rec['id']}\\t{rec['type']}\\t{rec['name']}\\t{rec['content']}\\t{rec['proxied']}\")
")
    if [ -n "${EXISTING}" ]; then
        REC_ID=$(echo "${EXISTING}" | head -1 | cut -f1)
        echo "  Found existing — updating ${REC_ID}"
        curl -s -X PUT "${CF_API}/zones/${ZONE_ID}/dns_records/${REC_ID}" \
            -H "${AUTH}" -H "Content-Type: application/json" \
            --data "{\"type\":\"CNAME\",\"name\":\"${RECORD_NAME}\",\"content\":\"${RECORD_TARGET}\",\"ttl\":1,\"proxied\":false}" \
            | python3 -c "import sys,json; d=json.load(sys.stdin); print('  → success=' + str(d.get('success')) + ' · errors=' + str(d.get('errors', [])))"
    else
        echo "  None found — creating new CNAME"
        curl -s -X POST "${CF_API}/zones/${ZONE_ID}/dns_records" \
            -H "${AUTH}" -H "Content-Type: application/json" \
            --data "{\"type\":\"CNAME\",\"name\":\"${RECORD_NAME}\",\"content\":\"${RECORD_TARGET}\",\"ttl\":1,\"proxied\":false}" \
            | python3 -c "import sys,json; d=json.load(sys.stdin); print('  → success=' + str(d.get('success')) + ' · errors=' + str(d.get('errors', [])))"
    fi
done

echo
echo "→ Waiting 45s for Cloudflare to publish + Netlify SSL to provision..."
sleep 45

for pair in "${RECORDS[@]}"; do
    NAME="${pair%%|*}"
    HOST="${NAME}.${ZONE_NAME}"
    echo
    echo "─── ${HOST} ───"
    echo "  CNAME resolves: $(dig +short ${HOST} @1.1.1.1 | head -1)"
    curl -s --max-time 12 -o /dev/null -w "  HTTPS: HTTP %{http_code}\n" "https://${HOST}/"
done
