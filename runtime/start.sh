#!/bin/bash
set -e

if [ -n "$TAILSCALE_AUTH_KEY" ]; then
  echo "[tailscale] Starting daemon (userspace networking)..."
  tailscaled --tun=userspace-networking --socks5-server=localhost:1055 --state=mem: &
  sleep 3
  tailscale up \
    --authkey="$TAILSCALE_AUTH_KEY" \
    --hostname="railway-swarm-runtime" \
    --accept-routes \
    --accept-dns=false
  echo "[tailscale] Connected: $(tailscale ip -4 2>/dev/null || echo pending)"
  export ALL_PROXY=socks5://localhost:1055
  export HTTPS_PROXY=socks5://localhost:1055
  export HTTP_PROXY=socks5://localhost:1055
  export NO_PROXY=localhost,127.0.0.1,.railway.internal
fi

exec uvicorn main:app --host 0.0.0.0 --port 3000
