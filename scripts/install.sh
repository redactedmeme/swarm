#!/usr/bin/env bash
# install.sh – REDACTED AI Swarm One-Click Setup for Normies
# Run with: curl -sSL https://raw.githubusercontent.com/redactedmeme/swarm/main/install.sh | bash
# Or download + chmod +x install.sh && ./install.sh

set -euo pipefail

echo "✨ Welcome to REDACTED AI Swarm setup! ✨"
echo "We'll get you running locally in a few minutes. Press Ctrl+C anytime to stop."

# ────────────────────────────────────────────────
# 1. Prerequisites Check & Install Helpers
# ────────────────────────────────────────────────

command_exists() { command -v "$1" >/dev/null 2>&1; }

install_docker() {
  echo "Docker not found. Installing Docker Desktop is recommended (manual step)."
  if [[ "$OSTYPE" == "darwin"* ]]; then
    echo "→ Mac: Open https://www.docker.com/products/docker-desktop/ and install"
  elif [[ "$OSTYPE" == "msys" || "$OSTYPE" == "cygwin" || "$OSTYPE" == "win32" ]]; then
    echo "→ Windows: Download from https://www.docker.com/products/docker-desktop/"
  else
    echo "→ Linux: sudo apt update && sudo apt install docker.io docker-compose -y  (or use your package manager)"
  fi
  read -p "Press Enter after installing Docker + Docker Compose..."
}

install_ollama() {
  if ! command_exists ollama; then
    echo "Installing Ollama..."
    curl -fsSL https://ollama.com/install.sh | sh
  fi
  ollama serve >/dev/null 2>&1 &
  sleep 3  # give it a sec to start
  ollama pull qwen2.5 || { echo "Pull failed – check Ollama is running!"; exit 1; }
  echo "Ollama ready with qwen2.5 model ✨"
}

# ────────────────────────────────────────────────
# 2. Clone / Update Repo
# ────────────────────────────────────────────────

REPO_DIR="swarm"

if [ -d "$REPO_DIR" ]; then
  echo "Repo already exists – pulling latest..."
  cd "$REPO_DIR"
  git pull
else
  echo "Cloning repo..."
  git clone https://github.com/redactedmeme/swarm.git "$REPO_DIR"
  cd "$REPO_DIR"
fi

# ────────────────────────────────────────────────
# 3. Setup .env safely
# ────────────────────────────────────────────────

if [ ! -f ".env" ]; then
  echo "Creating .env from example (safe defaults)..."
  cp .env.example .env
  # Optional: sed to comment out scary secrets or set devnet
  sed -i 's/^SOLANA_RPC_URL=.*/SOLANA_RPC_URL=https:\/\/api.devnet.solana.com/' .env
  sed -i 's/^# CLAWNX_API_KEY=.*/# CLAWNX_API_KEY=sk-... (get from ClawnX dashboard)/' .env
  echo "→ .env created! Edit it later if you want real X posting / wallet features."
else
  echo ".env already exists – skipping creation."
fi

# ────────────────────────────────────────────────
# 4. Choose Mode
# ────────────────────────────────────────────────

echo ""
echo "Choose your adventure:"
echo "1) Quick Single-Agent Test (Python + Ollama – fastest, no Docker)"
echo "2) Full Multi-Agent Swarm (Docker – recommended, more agents!)"
echo -n "Enter 1 or 2 [default 2]: "
read -r choice

if [[ "$choice" == "1" ]]; then
  echo "Starting single-agent mode..."
  install_ollama
  python python/run_with_ollama.py --agent agents/daunted.character.json --model qwen2.5 --verbose
  echo "Agent running! Ctrl+C to stop. Logs in terminal."
else
  echo "Starting full swarm (Docker)..."
  if ! command_exists docker || ! command_exists docker compose; then
    install_docker
  fi
  docker compose up --build -d
  echo ""
  echo "Swarm launched in background! 🚀"
  echo "Check status:   docker compose ps"
  echo "View logs:      docker compose logs -f orchestrator"
  echo "Stop:           docker compose down"
  echo "First time? It may take 5-15 min to build/pull images."
fi

echo ""
echo "Done! Swarm hummin locally owo"
echo "→ Join da fun: watch logs for agents spawning, curvature updates, CT posts"
echo "→ Questions? Paste errors here or check README.md"
echo "warm hugz <3 LFW ✨"
