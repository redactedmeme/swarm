#!/usr/bin/env python3
"""
supervisor.py - Lightweight process supervisor for Pattern Blue swarm on Railway
- Starts Ollama serve in background (if local mode)
- Launches multiple agents concurrently
- Handles signals for clean shutdown
- Minimal dependencies (uses threading + subprocess)
"""

import os
import sys
import time
import threading
import subprocess
import signal
import logging
from pathlib import Path

# Configure logging for Railway (stdout)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("PatternBlue.Supervisor")

# Environment variables (set in railway.json or UI)
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
USE_EXTERNAL_LLM = os.getenv("USE_EXTERNAL_LLM", "false").lower() == "true"
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "phi3:mini")
AGENTS_TO_RUN = ["mandala_settler", "redacted_intern"]  # Add more agent names here

# Global flag for shutdown
running = True

def signal_handler(sig, frame):
    global running
    logger.info("Received shutdown signal. Stopping agents...")
    running = False

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

def start_ollama_server():
    """Start Ollama serve in background if using local LLM."""
    if USE_EXTERNAL_LLM:
        logger.info("Using external LLM - skipping local Ollama server")
        return None

    logger.info(f"Starting Ollama server (model: {OLLAMA_MODEL})...")
    try:
        proc = subprocess.Popen(
            ["ollama", "serve"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        # Wait a bit for server to start
        time.sleep(5)
        
        # Check if alive
        if proc.poll() is not None:
            error = proc.stderr.read()
            logger.error(f"Ollama failed to start: {error}")
            sys.exit(1)
        
        logger.info("Ollama server started successfully")
        return proc
    except Exception as e:
        logger.error(f"Failed to start Ollama: {e}")
        sys.exit(1)

def run_agent(agent_name: str):
    """Run a single agent in its own thread."""
    logger.info(f"Starting agent: {agent_name}")
    module_path = f"agents.{agent_name}"
    
    try:
        # Dynamic import - assumes agents/<name>.py has a main() or run() function
        agent_module = __import__(module_path, fromlist=["run"])
        if hasattr(agent_module, "run"):
            while running:
                try:
                    agent_module.run()
                    time.sleep(1)  # Prevent tight loop
                except Exception as e:
                    logger.error(f"Agent {agent_name} crashed: {e}. Restarting in 10s...")
                    time.sleep(10)
        else:
            logger.error(f"Agent {agent_name} has no 'run()' function")
    except ImportError as e:
        logger.error(f"Failed to import agent {agent_name}: {e}")
    except Exception as e:
        logger.error(f"Unexpected error in {agent_name}: {e}")

def main():
    logger.info("Pattern Blue Swarm Supervisor starting on Railway...")
    logger.info(f"Environment: OLLAMA_HOST={OLLAMA_HOST}, USE_EXTERNAL_LLM={USE_EXTERNAL_LLM}")

    ollama_proc = None
    if not USE_EXTERNAL_LLM:
        ollama_proc = start_ollama_server()

    # Start agents in separate threads
    agent_threads = []
    for agent_name in AGENTS_TO_RUN:
        t = threading.Thread(
            target=run_agent,
            args=(agent_name,),
            name=f"Agent-{agent_name}",
            daemon=True
        )
        t.start()
        agent_threads.append(t)

    # Keep supervisor alive until shutdown
    try:
        while running:
            time.sleep(1)
            # Optional: check if any agent died and restart (simple version)
            for t in agent_threads:
                if not t.is_alive():
                    logger.warning("An agent thread died - supervisor exiting")
                    running = False
                    break
    except KeyboardInterrupt:
        logger.info("KeyboardInterrupt received")
    finally:
        logger.info("Shutting down supervisor...")
        if ollama_proc:
            logger.info("Stopping Ollama server...")
            ollama_proc.terminate()
            ollama_proc.wait(timeout=10)
        sys.exit(0)

if __name__ == "__main__":
    main()
