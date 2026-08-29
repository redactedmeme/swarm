#!/bin/bash

if [ -n "$TAILSCALE_AUTH_KEY" ]; then
  echo "[tailscale] Starting daemon (userspace networking)..."
  tailscaled --tun=userspace-networking --socks5-server=localhost:1055 --state=mem: &
  sleep 3
  if tailscale up \
      --authkey="$TAILSCALE_AUTH_KEY" \
      --hostname="railway-redacted-chan" \
      --accept-routes \
      --accept-dns=false 2>&1; then
    echo "[tailscale] Connected: $(tailscale ip -4 2>/dev/null || echo pending)"
    export ALL_PROXY=socks5://localhost:1055
    export HTTPS_PROXY=socks5://localhost:1055
    export HTTP_PROXY=socks5://localhost:1055
    export NO_PROXY=localhost,127.0.0.1,.railway.internal
  else
    echo "[tailscale] Warning: failed to connect (no TUN?), running without Tailscale"
  fi
fi

exec python main.py
