#!/bin/bash
set -e

if [ -n "$TAILSCALE_AUTH_KEY" ]; then
  echo "[tailscale] Starting daemon..."
  tailscaled --state=mem: &
  sleep 2
  tailscale up \
    --authkey="$TAILSCALE_AUTH_KEY" \
    --hostname="railway-smolting" \
    --accept-routes \
    --accept-dns=false
  echo "[tailscale] Connected: $(tailscale ip -4 2>/dev/null || echo 'pending')"
else
  echo "[tailscale] TAILSCALE_AUTH_KEY not set — skipping Tailscale"
fi

exec python main.py
