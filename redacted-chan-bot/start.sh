#!/bin/bash
set -e

if [ -n "$TAILSCALE_AUTH_KEY" ]; then
  echo "[tailscale] Starting daemon (userspace networking)..."
  tailscaled --tun=userspace-networking --socks5-server=localhost:1055 --state=mem: &
  sleep 3
  tailscale up \
    --authkey="$TAILSCALE_AUTH_KEY" \
    --hostname="railway-redacted-chan" \
    --accept-routes \
    --accept-dns=false
  echo "[tailscale] Connected: $(tailscale ip -4 2>/dev/null || echo pending)"
  # Route outbound TCP through Tailscale SOCKS5 proxy
  export ALL_PROXY=socks5://localhost:1055
  export HTTPS_PROXY=socks5://localhost:1055
  export HTTP_PROXY=socks5://localhost:1055
  # Exclude Railway-internal traffic from proxy
  export NO_PROXY=localhost,127.0.0.1,.railway.internal
fi

exec python main.py
