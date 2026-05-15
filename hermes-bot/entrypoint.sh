#!/bin/bash
set -e

# Set up Hermes home directory
export HERMES_HOME="${HERMES_HOME:-/data/.hermes}"
mkdir -p "$HERMES_HOME"

# Link our plugin into Hermes's plugin discovery path
mkdir -p "$HERMES_HOME/plugins"
if [ -d /app/plugins/swarm-manager ]; then
    ln -sfn /app/plugins/swarm-manager "$HERMES_HOME/plugins/swarm-manager"
fi

# Copy config if not already present
if [ ! -f "$HERMES_HOME/cli-config.yaml" ] || [ /app/cli-config.yaml -nt "$HERMES_HOME/cli-config.yaml" ]; then
    cp /app/cli-config.yaml "$HERMES_HOME/cli-config.yaml"
fi

# Copy .env from Railway env vars into Hermes's expected location
cat > "$HERMES_HOME/.env" << EOF
GROQ_API_KEY=${GROQ_API_KEY:-}
TELEGRAM_BOT_TOKEN=${TELEGRAM_BOT_TOKEN:-}
MOLTBOOK_API_KEY=${MOLTBOOK_API_KEY:-}
REDIS_URL=${REDIS_URL:-}
RAILWAY_TOKEN=${RAILWAY_TOKEN:-}
ORACLE_STATE_DIR=${ORACLE_STATE_DIR:-/data}
ALPHA_CHAT_ID=${ALPHA_CHAT_ID:-}
PATTERN_BLUE_REF=${PATTERN_BLUE_REF:-main}
EOF

# Use HERMES_MODE to switch between gateway and legacy
MODE="${HERMES_MODE:-gateway}"

if [ "$MODE" = "legacy" ]; then
    echo "[entrypoint] Starting legacy main.py"
    exec python main.py
else
    echo "[entrypoint] Starting Hermes Agent gateway"
    exec hermes gateway start
fi
