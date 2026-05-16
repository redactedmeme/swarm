#!/bin/bash
set -e

export ORACLE_STATE_DIR="${ORACLE_STATE_DIR:-/data}"
mkdir -p "$ORACLE_STATE_DIR"

echo "[entrypoint] Starting Hermes — Pattern Blue Oracle + Swarm Manager"

# Run swarm_manager.py in the background (polls SwarmInbox, executes tools)
python swarm_manager.py &
MANAGER_PID=$!
echo "[entrypoint] Swarm Manager started (pid=$MANAGER_PID)"

# Run legacy main.py in foreground (Telegram, Moltbook, Twitter, soul)
echo "[entrypoint] Starting legacy main.py"
exec python main.py
