#!/usr/bin/env bash
# Database backup — pg_dump compressed into the shared backups volume.
set -euo pipefail
cd "$(dirname "$0")/.."
source .env 2>/dev/null || true
OUT=/app/backups
STAMP=$(date +%Y%m%d_%H%M%S)
mkdir -p "$OUT"

if command -v pg_dump >/dev/null 2>&1; then
  pg_dump -h db -U "${POSTGRES_USER:-newvpn}" -d "${POSTGRES_DB:-newvpn}" -Fc -f "$OUT/newvpn_db_$STAMP.dump"
else
  docker compose exec -T db pg_dump -U "${POSTGRES_USER:-newvpn}" -d "${POSTGRES_DB:-newvpn}" -Fc \
    > "$OUT/newvpn_db_$STAMP.dump"
fi
# xray state (reality keys + certs)
tar -czf "$OUT/newvpn_xray_state_$STAMP.tgz" -C / /etc/newvpn/xray 2>/dev/null || true
# retention: keep 14 newest
ls -1t "$OUT"/newvpn_db_*.dump 2>/dev/null | tail -n +15 | xargs -r rm -f
ls -1t "$OUT"/newvpn_xray_state_*.tgz 2>/dev/null | tail -n +15 | xargs -r rm -f
echo "$OUT/newvpn_db_$STAMP.dump"
