#!/usr/bin/env bash
# Update: pull latest code, rebuild, run migrations, restart services.
set -euo pipefail
APP_DIR=$(cd "$(dirname "$0")/.." && pwd)
cd "$APP_DIR"
git pull --ff-only
docker compose build
docker compose run --rm migrate
docker compose up -d
echo "update done."
