#!/usr/bin/env bash
# REDACTED AI Swarm — run terminal (Linux/macOS)
# Usage: ./run.sh   or   bash run.sh

set -e
REPO_ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$REPO_ROOT"

# Optional: install minimal deps for cloud terminal
# pip install openai requests python-dotenv --quiet

exec python run.py
