#!/bin/bash
# Xray supervisor — runs the xray binary against the shared config volume and
# restarts the process when the app rewrites config.json or touches .reload.
set -u
CFG_DIR=/etc/newvpn/xray
CONFIG=$CFG_DIR/config.json
MARKER=$CFG_DIR/.reload
BIN=/usr/local/bin/xray

# wait for app to produce a config
for i in $(seq 1 120); do
  [ -f "$CONFIG" ] && break
  echo "[xray-supervisor] waiting for $CONFIG..."
  sleep 5
done

last_hash=""
while true; do
  cur=$(sha256sum "$CONFIG" 2>/dev/null | cut -d' ' -f1)$(stat -c %y "$MARKER" 2>/dev/null || true)
  if [ "$cur" != "$last_hash" ]; then
    if [ -n "$last_hash" ]; then
      echo "[xray-supervisor] config changed — restarting xray"
      pkill -x xray 2>/dev/null || true
      sleep 1
    fi
    last_hash="$cur"
  fi
  if ! pgrep -x xray >/dev/null 2>&1; then
    echo "[xray-supervisor] starting xray"
    "$BIN" run -c "$CONFIG" &
  fi
  sleep 3
done
