#!/usr/bin/env bash
# Restore DB from a .dump backup. Usage: bash scripts/restore.sh backups/newvpn_db_XXX.dump
set -euo pipefail
DUMP=${1:?usage: restore.sh <path/to/dump>}
cd "$(dirname "$0")/.."
source .env 2>/dev/null || true
[ -f "$DUMP" ] || { echo "dump not found: $DUMP"; exit 1; }
read -p "This OVERWRITES the current database. Type YES to continue: " ok
[ "$ok" = "YES" ] || exit 1
if command -v pg_restore >/dev/null 2>&1; then
  pg_restore -h db -U "${POSTGRES_USER:-newvpn}" -d "${POSTGRES_DB:-newvpn}" --clean --if-exists "$DUMP"
else
  docker compose exec -T db env PGPASSWORD="${POSTGRES_PASSWORD:-change_me}" \
    pg_restore -U "${POSTGRES_USER:-newvpn}" -d "${POSTGRES_DB:-newvpn}" --clean --if-exists - < "$DUMP"
fi
echo "restore done."
