# apps/hermes/plugins/swarm-manager/exec_tools.py
"""python_exec — now a thin client to the exec-runner sandbox (IronClaw control 1).

The old implementation ran ``python3 -c <llm-supplied code>`` *in this container*
— which holds every API key, the Railway tokens, and (via other bots) wallet
material — behind a regex denylist that `().__class__.__mro__` walks straight
through. Recon flagged this as the swarm's single worst blast radius, reachable
end-to-end from a Telegram DM.

Now:

* the code is shipped to ``apps/exec-runner`` over a unix socket. That container
  has **no secrets in its environment** and ``network_mode: none`` — the snippet
  cannot reach the proxy, Redis, wallets, or the internet.
* the runner enforces CPU / memory / file-size / nproc rlimits and a wall-clock
  kill; ``python3 -I -S`` gives it no site-packages.
* every call is capability-checked (``authz.require("hermes", "code.exec")``) and
  written to the tamper-evident audit log.
* the regex denylist stays as a *cheap pre-filter* only — it is no longer load-
  bearing.

``EXEC_RUNNER_SOCK`` / ``EXEC_RUNNER_TOKEN`` configure the transport. If the
runner is unreachable the tool fails closed (returns an error, runs nothing).
"""
from __future__ import annotations

import json
import logging
import os

from swarm_core.exec_client import run_code

logger = logging.getLogger("swarm-manager.exec")

EXEC_ENABLED = os.getenv("EXEC_ENABLED", "false").lower() == "true"
RUNNER_SOCK = os.getenv("EXEC_RUNNER_SOCK", "/run/exec/exec.sock")
ACTOR = os.getenv("SWARM_NODE_ID", "hermes")


def _handle_python_exec(args: dict) -> str:
    if not EXEC_ENABLED:
        return json.dumps({"status": "error", "error": "Code execution is disabled (EXEC_ENABLED not set)"})
    result = run_code(
        args.get("code") or "",
        actor=ACTOR,
        timeout=int(args.get("timeout", 10) or 10),
        sock=RUNNER_SOCK,
    )
    return json.dumps(result)


# ── Registration ─────────────────────────────────────────────────────────────

def register(ctx):
    ctx.register_tool(
        name="python_exec",
        toolset="swarm",
        schema={
            "name": "python_exec",
            "description": (
                "Execute a short Python snippet in an isolated sandbox with no "
                "network and no access to swarm secrets. Use for pure computation; "
                "filesystem, sockets and outbound HTTP are unavailable."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "code": {"type": "string", "description": "Python code to execute (stdlib only, no network)."},
                    "timeout": {"type": "integer", "description": "Seconds (max 30, default 10)", "default": 10},
                },
                "required": ["code"],
            },
        },
        handler=_handle_python_exec,
    )
    status = "ENABLED" if EXEC_ENABLED else "DISABLED (set EXEC_ENABLED=true)"
    logger.info("[swarm-manager] Exec tools registered → sandbox %s — %s", RUNNER_SOCK, status)
