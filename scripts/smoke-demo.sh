#!/usr/bin/env bash
# Demo smoke test: verify token -> repo access -> POST /scan (deterministic, no LLM).
# /scan is async: returns 202 immediately, work happens in background.
# Usage: scripts/smoke-demo.sh owner/repo [base_url]
set -euo pipefail
cd "$(dirname "$0")/.."
set -a; source .env; set +a
REPO="${1:?usage: smoke-demo.sh owner/repo}"
BASE="${2:-http://localhost:8000}"
LOG="${APP_LOG:-/tmp/scrum-app.log}"

echo "== token identity =="
curl -sS -H "Authorization: Bearer $GITHUB_TOKEN" https://api.github.com/user |
  python3 -c "import json,sys; d=json.load(sys.stdin); print('as:', d.get('login', d.get('message')))"

echo "== repo visibility =="
code=$(curl -sS -o /tmp/smoke-repo.json -w "%{http_code}" \
  -H "Authorization: Bearer $GITHUB_TOKEN" "https://api.github.com/repos/$REPO")
echo "GET /repos/$REPO -> $code"
[ "$code" = 200 ] || { echo "token cannot see repo — check repository access + Contents:Read"; exit 1; }

echo "== POST /scan =="
mark=$(date +%s)
code=$(curl -sS -o /dev/null -w "%{http_code}" -X POST "$BASE/scan" \
  -H "Content-Type: application/json" -H "X-Api-Key: $API_KEY" \
  -d "{\"repo\":\"$REPO\"}")
echo "POST /scan -> $code (async)"
[ "$code" = 202 ] || { echo "unexpected status"; exit 1; }

echo "== waiting for crew =="
for _ in $(seq 1 30); do
  line=$(grep "Crew completed" "$LOG" 2>/dev/null | tail -1 || true)
  if [ -n "$line" ] && [ "$(stat -f %m "$LOG")" -ge "$mark" ]; then
    echo "$line" | sed 's/^INFO:src.webhook_router://'
    exit 0
  fi
  sleep 1
done
echo "timed out waiting for crew — check $LOG"
exit 1
