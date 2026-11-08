#!/bin/bash
# Xray supervisor — runs the xray binary against the shared config volume and
# restarts the process when the app rewrites config.json or touches .reload.
#
# debian:bookworm-slim has NO pgrep/pkill (procps/psmisc absent), so process
# management uses bash builtins only (kill/kill -0/wait) with an explicit PID.
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

xpid=""

start_xray() {
  "$BIN" run -c "$CONFIG" 2>&1 &
  xpid=$!
  echo "[xray-supervisor] starting xray pid=$xpid"
  # confirm the applied config version once the process proves stable
  (
    sleep 2
    if kill -0 "$xpid" 2>/dev/null; then
      sha256sum "$CONFIG" 2>/dev/null | cut -d' ' -f1 > "$CFG_DIR/.applied.tmp"
      mv "$CFG_DIR/.applied.tmp" "$CFG_DIR/.applied"
    fi
  ) &
}

stop_xray() {
  if [ -n "$xpid" ] && kill -0 "$xpid" 2>/dev/null; then
    kill "$xpid" 2>/dev/null
    i=0
    while kill -0 "$xpid" 2>/dev/null && [ "$i" -lt 20 ]; do
      sleep 0.2
      i=$((i + 1))
    done
    kill -9 "$xpid" 2>/dev/null
  fi
  [ -n "$xpid" ] && wait "$xpid" 2>/dev/null
  xpid=""
}

trap 'stop_xray; exit 0' TERM INT

last_hash=""
while true; do
  cur="$(sha256sum "$CONFIG" 2>/dev/null | cut -d' ' -f1)$(stat -c %y "$MARKER" 2>/dev/null || true)"
  if [ "$cur" != "$last_hash" ]; then
    if [ -n "$last_hash" ]; then
      echo "[xray-supervisor] config changed — restarting xray"
      stop_xray
    fi
    last_hash="$cur"
    start_xray
  elif [ -n "$xpid" ] && ! kill -0 "$xpid" 2>/dev/null; then
    wait "$xpid" 2>/dev/null   # reap crashed child before restarting
    start_xray
  elif [ -z "$xpid" ]; then
    start_xray
  fi
  sleep 3
done
