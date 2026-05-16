#!/usr/bin/env python3
"""
Main entrypoint for deploying REDACTED AI Swarm workers on Railway / cloud environments.

Launches agents in persistent or one-shot mode using terminal/scripts/redacted_terminal_cloud.py or equivalent runner.
Supports Ollama, Groq, OpenAI, etc. via configuration flags and environment variables.
"""

import argparse
import os
import subprocess
import sys
import time
import signal
from pathlib import Path

# --- Defaults & Constants ---
DEFAULT_AGENT = "agents/characters/RedactedIntern.character.json"
DEFAULT_MODE = "persistent"
DEFAULT_PROVIDER = "ollama"
DEFAULT_OLLAMA_HOST = "http://localhost:11434"
DEFAULT_WORKER_SCRIPT = "terminal/scripts/redacted_terminal_cloud.py"  # or your actual runner script

# --- Global variables for graceful shutdown ---
running = True


def signal_handler(sig, frame):
    global running
    print("[summon_agent] Received shutdown signal (SIGINT/SIGTERM). Exiting gracefully...")
    running = False


signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)


def parse_args():
    parser = argparse.ArgumentParser(description="REDACTED AI Swarm Worker Launcher")
    parser.add_argument("--agent", type=str, default=os.getenv("AGENT_PATH", DEFAULT_AGENT),
                        help="Path to .character.json agent file (default: %(default)s)")
    parser.add_argument("--mode", type=str, default=os.getenv("WORKER_MODE", DEFAULT_MODE),
                        choices=["persistent", "once"], help="Execution mode: persistent (loop) or once")
    parser.add_argument("--provider", type=str, default=os.getenv("LLM_PROVIDER", DEFAULT_PROVIDER),
                        choices=["ollama", "groq", "openai", "openrouter", "grok"],
                        help="LLM backend provider")
    parser.add_argument("--ollama-host", type=str, default=os.getenv("OLLAMA_HOST", DEFAULT_OLLAMA_HOST),
                        help="Ollama server URL (only used if provider=ollama)")
    parser.add_argument("--worker-script", type=str, default=os.getenv("WORKER_SCRIPT", DEFAULT_WORKER_SCRIPT),
                        help="Path to the actual agent runner script")
    parser.add_argument("--max-retries", type=int, default=20,
                        help="Max restart attempts in persistent mode before giving up")
    parser.add_argument("--debug", action="store_true", help="Enable verbose output")

    return parser.parse_args()


def build_command(args):
    """Build the subprocess command based on parsed arguments."""
    repo_root = Path(__file__).parent.parent.resolve()
    worker_script_path = repo_root / args.worker_script
    agent_path = repo_root / args.agent

    if not worker_script_path.is_file():
        print(f"[ERROR] Worker script not found: {worker_script_path}")
        sys.exit(1)

    if not agent_path.is_file():
        print(f"[ERROR] Agent file not found: {agent_path}")
        sys.exit(1)

    cmd = [sys.executable, str(worker_script_path), "--agent", str(agent_path)]

    # Provider-specific flags
    if args.provider == "ollama":
        cmd.extend(["--ollama-host", args.ollama_host])
    # Add more provider flags here as needed (e.g., --api-key-env for Groq/OpenAI)

    if args.debug:
        cmd.append("--debug")

    return cmd, repo_root


def run_persistent(cmd, repo_root, max_retries):
    """Run the worker in persistent mode with automatic restarts."""
    retries = 0
    while running and retries < max_retries:
        print(f"[persistent] Starting worker (attempt {retries + 1}/{max_retries}) ...")
        print(f"[command] {' '.join(cmd)}")

        try:
            result = subprocess.run(cmd, check=True, cwd=repo_root, env=os.environ.copy())
            print(f"[exit] Worker exited with code {result.returncode}")
            if result.returncode == 0:
                print("[persistent] Clean exit — restarting in 10s...")
            else:
                print(f"[persistent] Non-zero exit — restarting in 15s...")
                time.sleep(15)
        except subprocess.CalledProcessError as e:
            print(f"[error] Worker failed: {e}")
            retries += 1
            time.sleep(10)
        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"[unexpected] {e}")
            retries += 1
            time.sleep(5)

    if retries >= max_retries:
        print(f"[fatal] Max retries ({max_retries}) reached. Stopping.")
        sys.exit(1)


def main():
    args = parse_args()

    print("[summon_agent] REDACTED AI Swarm Worker Launcher")
    print(f"  Agent:    {args.agent}")
    print(f"  Mode:     {args.mode}")
    print(f"  Provider: {args.provider}")
    if args.provider == "ollama":
        print(f"  Ollama:   {args.ollama_host}")

    cmd, repo_root = build_command(args)

    if args.mode == "persistent":
        run_persistent(cmd, repo_root, args.max_retries)
    else:
        # One-shot mode
        print("[once] Starting single execution...")
        try:
            subprocess.run(cmd, check=True, cwd=repo_root)
        except subprocess.CalledProcessError as e:
            print(f"[error] Execution failed: {e}")
            sys.exit(e.returncode)


if __name__ == "__main__":
    main()
