#!/bin/bash
# Test Paperless connection from home Mac (100.98.90.26) → work Mac (100.99.86.60)
# Double-click this in Finder to run

TOKEN="583e819be1146b96b935007c6ad7f584a3a1b1b7"
URL="http://100.99.86.60:8000"
OUT=~/Desktop/REX/logs/paperless_test_$(date +%H%M%S).log

mkdir -p ~/Desktop/REX/logs

echo "=== Paperless Connection Test $(date) ===" | tee "$OUT"
echo "" | tee -a "$OUT"

echo "→ Testing basic reach (curl, 5s timeout)..." | tee -a "$OUT"
HTTP=$(curl -s -o /tmp/paperless_test_body.txt -w "%{http_code}" \
  -H "Authorization: Token $TOKEN" \
  "$URL/api/documents/?page_size=1" \
  --max-time 5 2>/dev/null || echo "FAILED")
echo "  HTTP status: $HTTP" | tee -a "$OUT"
echo "  Response body:" | tee -a "$OUT"
cat /tmp/paperless_test_body.txt | head -c 300 | tee -a "$OUT"
echo "" | tee -a "$OUT"

if [ "$HTTP" = "200" ]; then
    echo "✅ PAPERLESS ENGINE 3 IS WORKING" | tee -a "$OUT"
elif [ "$HTTP" = "403" ]; then
    echo "⚠️  403 Forbidden — ALLOWED_HOSTS may need updating" | tee -a "$OUT"
    echo "   Fix: add PAPERLESS_ALLOWED_HOSTS=* to docker-compose.yml" | tee -a "$OUT"
elif [ "$HTTP" = "401" ]; then
    echo "⚠️  401 Unauthorized — Token is wrong" | tee -a "$OUT"
elif [ "$HTTP" = "FAILED" ]; then
    echo "❌ Cannot reach Paperless — check Tailscale is connected" | tee -a "$OUT"
fi

echo "" | tee -a "$OUT"
echo "Full log saved: $OUT"
echo ""
read -n 1 -p "Press any key to close..."
