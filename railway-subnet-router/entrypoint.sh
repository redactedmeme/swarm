#!/bin/bash
set -e

SUBNET="${TAILSCALE_SUBNET:-fd12::/16}"
HOSTNAME="${TAILSCALE_HOSTNAME:-railway-subnet-router}"

echo "[subnet-router] Starting tailscaled..."
tailscaled \
  --tun=userspace-networking \
  --socks5-server=localhost:1055 \
  --state=/var/lib/tailscale/tailscaled.state \
  &

sleep 3

echo "[subnet-router] Connecting to tailnet..."
tailscale up \
  --authkey="${TAILSCALE_AUTH_KEY}" \
  --hostname="${HOSTNAME}" \
  --advertise-routes="${SUBNET}" \
  --accept-routes \
  --accept-dns=false

echo "[subnet-router] Connected: $(tailscale ip 2>/dev/null)"
echo "[subnet-router] Advertising subnet: ${SUBNET}"

# Keep alive — restart tailscale if it drops
while true; do
  if ! tailscale status > /dev/null 2>&1; then
    echo "[subnet-router] Tailscale dropped — reconnecting..."
    tailscale up \
      --authkey="${TAILSCALE_AUTH_KEY}" \
      --hostname="${HOSTNAME}" \
      --advertise-routes="${SUBNET}" \
      --accept-routes \
      --accept-dns=false
  fi
  sleep 30
done
