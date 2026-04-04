#!/usr/bin/env python3
"""
REDACTED Swarm - unified service launcher.

Mirrors openclaw's gateway-first startup model:
  1. Validate environment
  2. Check service dependencies (Ollama, etc.)
  3. Start the web terminal (web_ui/app.py)
  4. Optionally start the Telegram bot
  5. Optionally start agent daemons

Usage:
    python scripts/start.py                  # web terminal only (auto-detects LLM)
    python scripts/start.py --all            # web terminal + telegram bot
    python scripts/start.py --agent <file>   # also start a persistent agent daemon
    python scripts/start.py --check          # health check only, don't start

Run from repo root.
"""

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
WEB_UI    = REPO_ROOT / "web_ui" / "app.py"
BOT_MAIN  = REPO_ROOT / "smolting-telegram-bot" / "main.py"
SUMMON    = REPO_ROOT / "python" / "summon_agent.py"


# -- Environment validation ---------------------------------------------------

_REQUIRED_FOR = {
    "web terminal (cloud)": ["LLM_PROVIDER"],
    "Telegram bot":         ["TELEGRAM_BOT_TOKEN"],
    "xAI / Grok":          ["XAI_API_KEY"],
    "OpenAI":               ["OPENAI_API_KEY"],
    "Anthropic":            ["ANTHROPIC_API_KEY"],
    "Clawnch analytics":    ["MOLTBOOK_API_KEY"],
}

def _load_env():
    env_file = REPO_ROOT / ".env"
    if env_file.exists():
        try:
            from dotenv import load_dotenv
            load_dotenv(env_file)
        except ImportError:
            # Manual parse fallback (no python-dotenv)
            for line in env_file.read_text().splitlines():
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    k, _, v = line.partition('=')
                    os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def _check_env() -> list[str]:
    """Return list of warnings about missing optional env vars."""
    warnings = []
    provider = os.getenv("LLM_PROVIDER", "ollama").lower()
    if provider in ("xai", "grok") and not os.getenv("XAI_API_KEY"):
        warnings.append("LLM_PROVIDER=xai but XAI_API_KEY is not set")
    if provider == "openai" and not os.getenv("OPENAI_API_KEY"):
        warnings.append("LLM_PROVIDER=openai but OPENAI_API_KEY is not set")
    if provider == "anthropic" and not os.getenv("ANTHROPIC_API_KEY"):
        warnings.append("LLM_PROVIDER=anthropic but ANTHROPIC_API_KEY is not set")
    return warnings


# -- Service health checks ----------------------------------------------------

def _check_ollama() -> bool:
    try:
        import urllib.request
        with urllib.request.urlopen("http://localhost:11434/api/tags", timeout=2) as r:
            return r.status == 200
    except Exception:
        return False


def _check_web_ui_port(port: int = 5000) -> bool:
    import socket
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=1):
            return True
    except Exception:
        return False


def _print_health():
    provider = os.getenv("LLM_PROVIDER", "ollama").lower()
    ollama_ok = _check_ollama()
    web_ok    = _check_web_ui_port()

    print("-- Health check -------------------------------------")
    print(f"  LLM provider : {provider}")
    print(f"  Ollama       : {'OK running' if ollama_ok else 'NOT reachable (localhost:11434)'}")
    print(f"  Web terminal : {'OK running (port 5000)' if web_ok else 'not started yet'}")
    print(f"  XAI_API_KEY  : {'set' if os.getenv('XAI_API_KEY') else 'not set'}")
    print(f"  OPENAI_API_KEY: {'set' if os.getenv('OPENAI_API_KEY') else 'not set'}")
    print(f"  ANTHROPIC_API_KEY: {'set' if os.getenv('ANTHROPIC_API_KEY') else 'not set'}")
    print(f"  TELEGRAM_BOT_TOKEN: {'set' if os.getenv('TELEGRAM_BOT_TOKEN') else 'not set'}")
    print(f"  MOLTBOOK_API_KEY: {'set' if os.getenv('MOLTBOOK_API_KEY') else 'not set'}")
    print("-----------------------------------------------------")

    env_warnings = _check_env()
    for w in env_warnings:
        print(f"  [WARN] {w}")

    if provider == "ollama" and not ollama_ok:
        print("\n  [WARN] Ollama not running. Start with: ollama serve")
        print("         Or set LLM_PROVIDER=xai / anthropic / openai and the matching API key.")


# -- Process launchers --------------------------------------------------------

def _start_web_ui() -> subprocess.Popen:
    env = os.environ.copy()
    # Ensure web_ui can import from repo root and python/
    env["PYTHONPATH"] = str(REPO_ROOT / "python") + os.pathsep + env.get("PYTHONPATH", "")
    print(f"[start] Web terminal -> http://localhost:5000")
    return subprocess.Popen(
        [sys.executable, str(WEB_UI)],
        cwd=str(REPO_ROOT),
        env=env,
    )


def _start_telegram_bot() -> subprocess.Popen:
    if not BOT_MAIN.exists():
        print(f"[skip] Telegram bot not found at {BOT_MAIN}")
        return None
    if not os.getenv("TELEGRAM_BOT_TOKEN"):
        print("[skip] Telegram bot: TELEGRAM_BOT_TOKEN not set")
        return None
    print("[start] Telegram bot")
    return subprocess.Popen(
        [sys.executable, str(BOT_MAIN)],
        cwd=str(BOT_MAIN.parent),
    )


def _start_agent_daemon(agent_file: str) -> subprocess.Popen:
    print(f"[start] Agent daemon: {agent_file}")
    env = os.environ.copy()
    env["PYTHONPATH"] = str(REPO_ROOT / "python") + os.pathsep + env.get("PYTHONPATH", "")
    return subprocess.Popen(
        [sys.executable, str(SUMMON), "--agent", agent_file, "--mode", "persistent"],
        cwd=str(REPO_ROOT / "python"),
        env=env,
    )


# -- Main ---------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="REDACTED Swarm - unified launcher")
    parser.add_argument("--all",    action="store_true", help="Start all services (web UI + Telegram bot)")
    parser.add_argument("--agent",  metavar="FILE",      help="Also start a persistent agent daemon")
    parser.add_argument("--check",  action="store_true", help="Health check only, do not start services")
    args = parser.parse_args()

    _load_env()
    _print_health()

    if args.check:
        return

    processes: list[subprocess.Popen] = []

    # Gateway first: web terminal
    web = _start_web_ui()
    processes.append(web)

    # Wait briefly, then verify it started
    time.sleep(2)
    if not _check_web_ui_port():
        print("[warn] Web terminal did not bind to port 5000 within 2s - check for errors above.")

    if args.all:
        bot = _start_telegram_bot()
        if bot:
            processes.append(bot)

    if args.agent:
        daemon = _start_agent_daemon(args.agent)
        processes.append(daemon)

    print("\nAll services started. Press Ctrl+C to stop all.\n")

    try:
        while True:
            # Restart any crashed processes
            for i, p in enumerate(processes):
                if p and p.poll() is not None:
                    print(f"[warn] Process {p.args[0]} exited with code {p.returncode} - restarting...")
                    processes[i] = subprocess.Popen(p.args, cwd=p.cwd if hasattr(p, 'cwd') else None, env=p.env if hasattr(p, 'env') else None)
            time.sleep(5)
    except KeyboardInterrupt:
        print("\n[stop] Stopping all services...")
        for p in processes:
            if p:
                p.terminate()
        for p in processes:
            if p:
                try:
                    p.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    p.kill()
        print("[stop] Done.")


if __name__ == "__main__":
    main()
