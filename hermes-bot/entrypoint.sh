#!/bin/bash
set -e

export ORACLE_STATE_DIR="${ORACLE_STATE_DIR:-/data}"
mkdir -p "$ORACLE_STATE_DIR"

echo "[entrypoint] Starting Hermes — Pattern Blue Oracle + Swarm Manager"

# Start Tailscale if auth key present
if [ -n "$TAILSCALE_AUTH_KEY" ]; then
  echo "[tailscale] Starting daemon (userspace networking)..."
  tailscaled --tun=userspace-networking --socks5-server=localhost:1055 --state=mem: &
  sleep 3
  if tailscale up \
      --authkey="$TAILSCALE_AUTH_KEY" \
      --hostname="railway-hermes-bot" \
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

# Run swarm_manager.py in the background (polls SwarmInbox, executes tools)
python swarm_manager.py &
MANAGER_PID=$!
echo "[entrypoint] Swarm Manager started (pid=$MANAGER_PID)"

# Run legacy main.py in foreground (Telegram, Moltbook, Twitter, soul)
echo "[entrypoint] Starting legacy main.py"
exec python main.py
