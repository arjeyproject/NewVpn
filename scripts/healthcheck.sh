#!/usr/bin/env bash
# Health check: DB, API, xray ports, bot process.
set -u
cd "$(dirname "$0")/.."
FAIL=0
if curl -fsS --max-time 5 "http://127.0.0.1:${SUB_API_PORT:-8080}/health" >/dev/null 2>&1; then
  echo "api: OK"
else
  echo "api: FAIL"; FAIL=1
fi
docker compose ps --format '{{.Name}} {{.Status}}' 2>/dev/null | while read -r l; do echo "container: $l"; done
if docker compose exec -T bot python -c "import app" 2>/dev/null; then echo "bot code: OK"; else echo "bot code: FAIL"; FAIL=1; fi
for p in 443 8080 8443; do
  (echo > /dev/tcp/127.0.0.1/$p) >/dev/null 2>&1 && echo "port $p: OPEN" || { echo "port $p: CLOSED"; FAIL=1; }
done
exit $FAIL
