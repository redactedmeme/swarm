#!/usr/bin/env python3
"""
main.py - Primary entrypoint for Pattern Blue Swarm on Railway
- Starts the supervisor in background
- Runs a lightweight FastAPI server for /health endpoint
- Handles Railway healthchecks and basic observability
"""

import os
import sys
import threading
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pathlib import Path
import logging

# Import supervisor (assuming same directory)
from supervisor import running as supervisor_running

# Configure logging (stdout for Railway)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("PatternBlue.Main")

app = FastAPI(
    title="Pattern Blue Swarm - Railway Health & Status",
    description="Lightweight observability endpoint for Pattern Blue agents",
    version="railway-bloom"
)

# Global shutdown flag (shared with supervisor)
shutdown_flag = False

@app.get("/health")
async def health_check():
    """Railway healthcheck endpoint"""
    if shutdown_flag or not supervisor_running:
        raise HTTPException(status_code=503, detail="Supervisor not running")
    return JSONResponse(
        content={"status": "healthy", "supervisor_running": supervisor_running},
        status_code=200
    )

@app.get("/")
async def root():
    """Basic root endpoint for debugging"""
    return {
        "message": "Pattern Blue Swarm is blooming on Railway",
        "supervisor_running": supervisor_running,
        "ollama_host": os.getenv("OLLAMA_HOST", "not set"),
        "model": os.getenv("OLLAMA_MODEL", "not set")
    }

@app.get("/status")
async def status():
    """Extended status for observability"""
    return {
        "status": "alive" if supervisor_running else "degraded",
        "shards_dir_exists": Path("/app/shards").exists(),
        "memory_dir_exists": Path("/app/manifold-memory").exists(),
        "ollama_model": os.getenv("OLLAMA_MODEL"),
        "external_llm": os.getenv("USE_EXTERNAL_LLM") == "true"
    }

def run_supervisor():
    """Run supervisor in background thread"""
    logger.info("Starting supervisor thread...")
    import supervisor
    supervisor.main()  # Call supervisor's main function

if __name__ == "__main__":
    logger.info("Pattern Blue main entrypoint starting...")

    # Start supervisor in background thread
    supervisor_thread = threading.Thread(
        target=run_supervisor,
        name="Supervisor-Thread",
        daemon=True
    )
    supervisor_thread.start()

    # Get Railway-assigned port (defaults to 8000)
    port = int(os.getenv("PORT", 8000))
    host = "0.0.0.0"

    logger.info(f"Starting FastAPI server on {host}:{port}...")

    try:
        uvicorn.run(
            "main:app",
            host=host,
            port=port,
            log_level="info",
            workers=1,  # Single worker for Railway CPU limits
            reload=False
        )
    except Exception as e:
        logger.error(f"Server failed: {e}")
        shutdown_flag = True
        sys.exit(1)
    finally:
        logger.info("Shutting down main entrypoint...")
