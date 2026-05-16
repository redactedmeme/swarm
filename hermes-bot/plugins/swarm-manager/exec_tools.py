# hermes-bot/plugins/swarm-manager/exec_tools.py
"""
Python code execution sandbox for Hermes.
Only enabled when EXEC_ENABLED=true env var is set.
Pre-flight checks block dangerous patterns before subprocess runs.
"""
from __future__ import annotations

import json
import logging
import os
import re
import subprocess

logger = logging.getLogger("swarm-manager.exec")

EXEC_ENABLED = os.getenv("EXEC_ENABLED", "false").lower() == "true"

BLOCKED_PATTERNS = [
    r'\bimport\s+os\b',
    r'\bimport\s+subprocess\b',
    r'\bimport\s+socket\b',
    r'\bimport\s+sys\b',
    r'\b__import__\b',
    r'\bopen\s*\(',
    r'\beval\s*\(',
    r'\bexec\s*\(',
    r'\bcompile\s*\(',
    r'import\s+shutil',
    r'import\s+pathlib',
    r'import\s+requests',
    r'import\s+httpx',
    r'import\s+urllib',
]


def _handle_python_exec(args: dict) -> str:
    if not EXEC_ENABLED:
        return json.dumps({"status": "error", "error": "Code execution is disabled (EXEC_ENABLED not set)"})

    code = args.get("code", "").strip()
    timeout = min(int(args.get("timeout", 10)), 30)  # cap at 30s

    if not code:
        return json.dumps({"status": "error", "error": "No code provided"})

    # Pre-flight safety check
    for pattern in BLOCKED_PATTERNS:
        if re.search(pattern, code):
            return json.dumps({"status": "blocked", "error": f"Blocked pattern detected: {pattern}"})

    try:
        result = subprocess.run(
            ["python3", "-c", code],
            capture_output=True,
            text=True,
            timeout=timeout,
            env={"PATH": "/usr/bin:/usr/local/bin"},
        )
        output = (result.stdout + result.stderr)[:2000]
        return json.dumps({
            "status": "ok",
            "stdout": result.stdout[:1000],
            "stderr": result.stderr[:500],
            "exit_code": result.returncode,
            "output": output,
        })
    except subprocess.TimeoutExpired:
        return json.dumps({"status": "error", "error": f"Execution timed out after {timeout}s"})
    except Exception as e:
        logger.warning("[python_exec] Execution error: %s", e)
        return json.dumps({"status": "error", "error": str(e)})


# ── Registration ──────────────────────────────────────────────────────────────

def register(ctx):
    ctx.register_tool(
        name="python_exec",
        toolset="swarm",
        schema={
            "name": "python_exec",
            "description": "Execute a Python code snippet in a sandboxed subprocess",
            "parameters": {
                "type": "object",
                "properties": {
                    "code": {
                        "type": "string",
                        "description": "Python code to execute. Dangerous imports (os, subprocess, socket, etc.) are blocked.",
                    },
                    "timeout": {
                        "type": "integer",
                        "description": "Execution timeout in seconds (max 30, default 10)",
                        "default": 10,
                    },
                },
                "required": ["code"],
            },
        },
        handler=_handle_python_exec,
    )

    status = "ENABLED" if EXEC_ENABLED else "DISABLED (set EXEC_ENABLED=true to enable)"
    logger.info("[swarm-manager] Exec tools registered (1 tool) — %s", status)
