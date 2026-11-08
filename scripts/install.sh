#!/usr/bin/env bash
# NewVpn installer — full server bootstrap (Docker optional path included).
# Usage: sudo bash scripts/install.sh
set -euo pipefail

APP_DIR=$(cd "$(dirname "$0")/.." && pwd)
XRAY_DIR=/opt/newvpn/xray
XRAY_VERSION=${XRAY_VERSION:-v25.3.6}

echo "==> [1/6] Server inspection"
if [ -f /etc/os-release ]; then . /etc/os-release; echo "    OS: $PRETTY_NAME"; fi
command -v docker >/dev/null 2>&1 && echo "    docker: $(docker --version)" || echo "    docker: MISSING"

echo "==> [2/6] Installing Docker if missing"
if ! command -v docker >/dev/null 2>&1; then
  if ! curl -fsSL --max-time 60 https://get.docker.com | sh; then
    echo "    get.docker.com failed — falling back to distro packages"
    apt-get update -qq && apt-get install -y -qq docker.io docker-compose-v2
  fi
  systemctl enable --now docker
fi

echo "==> [3/6] Fetching xray-core binary (with regional mirrors)"
mkdir -p "$XRAY_DIR"
ARCH=$(uname -m); [ "$ARCH" = "x86_64" ] && RARCH=64 || RARCH=arm64-v8a
TMPZIP=$(mktemp --suffix=.zip)
URLS=(
  "https://github.com/XTLS/Xray-core/releases/download/$XRAY_VERSION/Xray-linux-$RARCH.zip"
  "https://ghfast.top/https://github.com/XTLS/Xray-core/releases/download/$XRAY_VERSION/Xray-linux-$RARCH.zip"
  "https://gh-proxy.com/https://github.com/XTLS/Xray-core/releases/download/$XRAY_VERSION/Xray-linux-$RARCH.zip"
)
for u in "${URLS[@]}"; do
  if curl -fL --max-time 120 -o "$TMPZIP" "$u"; then echo "    downloaded: $u"; break; fi
done
unzip -o -q "$TMPZIP" xray -d "$XRAY_DIR" && chmod +x "$XRAY_DIR/xray"
rm -f "$TMPZIP"
"$XRAY_DIR/xray" version | head -1

echo "==> [4/6] Preparing .env"
if [ ! -f "$APP_DIR/.env" ]; then
  cp "$APP_DIR/.env.example" "$APP_DIR/.env"
  KEY=$(openssl rand -base64 32)
  PGPASS=$(openssl rand -hex 16)
  PUBLIC_IP=$(curl -s --max-time 8 https://api.ipify.org || hostname -I | awk '{print $1}')
  sed -i "s|^ENCRYPTION_KEY=.*|ENCRYPTION_KEY=$KEY|" "$APP_DIR/.env"
  sed -i "s|^POSTGRES_PASSWORD=.*|POSTGRES_PASSWORD=$PGPASS|" "$APP_DIR/.env"
  sed -i "s|^SERVER_PUBLIC_IP=.*|SERVER_PUBLIC_IP=$PUBLIC_IP|" "$APP_DIR/.env"
  chmod 600 "$APP_DIR/.env"
  echo "    created .env with generated secrets (edit BOT_TOKEN / ADMIN_TELEGRAM_IDS!)"
else
  echo "    .env already exists — keeping"
fi

echo "==> [5/6] Building & starting services"
cd "$APP_DIR"
docker compose build
docker compose up -d db
docker compose run --rm migrate
docker compose up -d

echo "==> [6/6] Health check"
sleep 5
curl -fsS "http://127.0.0.1:${SUB_API_PORT:-8080}/health" && echo
docker compose ps
echo "Installation complete. Configure BOT_TOKEN and ADMIN_TELEGRAM_IDS in .env, then:"
echo "  docker compose up -d bot"
