#!/usr/bin/env python3
"""
REDACTED AI Swarm — unified run entry point.
Run from repo root:  python run.py

Usage:
  python run.py            # auto-detect: web terminal (recommended)
  python run.py --cli      # force CLI terminal instead of web UI
  python run.py --all      # web terminal + Telegram bot
  python run.py --check    # health check only

The web terminal (http://localhost:5000) is the primary interface.
For the full openclaw-style launcher with agent daemons, use:
  python scripts/start.py
"""

import os
import sys
import subprocess

# Ensure we're in repo root (directory containing this script)
REPO_ROOT = os.path.dirname(os.path.abspath(__file__))
os.chdir(REPO_ROOT)

# Load .env from repo root
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(REPO_ROOT, ".env"))
except ImportError:
    pass

PYTHON_DIR    = os.path.join(REPO_ROOT, "python")
WEB_UI_SCRIPT = os.path.join(REPO_ROOT, "web_ui", "app.py")
CLOUD_SCRIPT  = os.path.join(PYTHON_DIR, "redacted_terminal_cloud.py")
OLLAMA_SCRIPT = os.path.join(PYTHON_DIR, "run_with_ollama.py")
START_SCRIPT  = os.path.join(REPO_ROOT, "scripts", "start.py")
DEFAULT_AGENT = "agents/RedactedIntern.character.json"


def _ollama_available():
    try:
        import urllib.request
        with urllib.request.urlopen("http://localhost:11434/api/tags", timeout=2) as resp:
            return resp.status == 200
    except Exception:
        return False


def _has_cloud_key():
    provider = (os.getenv("LLM_PROVIDER") or "ollama").lower()
    if provider in ("grok", "xai") and os.getenv("XAI_API_KEY"):
        return True
    if os.getenv("OPENAI_API_KEY"):
        return True
    if os.getenv("ANTHROPIC_API_KEY"):
        return True
    return False


def _run_web_ui(extra_args: list = None):
    """Start the web terminal (primary interface)."""
    env = os.environ.copy()
    env["PYTHONPATH"] = PYTHON_DIR + os.pathsep + env.get("PYTHONPATH", "")
    cmd = [sys.executable, WEB_UI_SCRIPT] + (extra_args or [])
    print("[run.py] Starting web terminal → http://localhost:5000")
    return subprocess.run(cmd, cwd=REPO_ROOT, env=env).returncode


def _run_cli():
    """Fallback: CLI terminal (cloud or Ollama)."""
    if _has_cloud_key():
        return subprocess.run([sys.executable, CLOUD_SCRIPT], cwd=REPO_ROOT).returncode
    if _ollama_available():
        agent = DEFAULT_AGENT
        if not os.path.exists(os.path.join(REPO_ROOT, agent)):
            agent = "agents/default.character.json"
        return subprocess.run(
            [sys.executable, OLLAMA_SCRIPT, "--agent", agent],
            cwd=REPO_ROOT,
        ).returncode
    return None  # Nothing available


def main():
    import argparse
    parser = argparse.ArgumentParser(description="REDACTED Swarm launcher")
    parser.add_argument("--cli",   action="store_true", help="Use CLI terminal instead of web UI")
    parser.add_argument("--all",   action="store_true", help="Start web terminal + Telegram bot")
    parser.add_argument("--check", action="store_true", help="Health check only")
    args = parser.parse_args()

    if args.check or args.all:
        # Delegate to the full launcher
        script_args = ["--check"] if args.check else ["--all"]
        sys.exit(subprocess.run([sys.executable, START_SCRIPT] + script_args, cwd=REPO_ROOT).returncode)

    if args.cli:
        rc = _run_cli()
        if rc is None:
            _print_no_backend()
            sys.exit(1)
        sys.exit(rc)

    # Default: web UI (preferred)
    if os.path.exists(WEB_UI_SCRIPT):
        sys.exit(_run_web_ui())

    # Fallback to CLI if web_ui missing
    rc = _run_cli()
    if rc is None:
        _print_no_backend()
        sys.exit(1)
    sys.exit(rc)


def _print_no_backend():
    print("REDACTED Terminal — no LLM backend available.")
    print()
    print("Set one of the following in .env or environment:")
    print("  XAI_API_KEY=...          (LLM_PROVIDER=xai)")
    print("  OPENAI_API_KEY=...       (LLM_PROVIDER=openai)")
    print("  ANTHROPIC_API_KEY=...    (LLM_PROVIDER=anthropic)")
    print()
    print("Or start Ollama locally:   ollama serve")
    print()
    print("Then run:  python run.py")


if __name__ == "__main__":
    main()
