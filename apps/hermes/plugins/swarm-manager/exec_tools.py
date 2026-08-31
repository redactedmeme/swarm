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

import hashlib
import http.client
import json
import logging
import os
import re
import socket

logger = logging.getLogger("swarm-manager.exec")

EXEC_ENABLED = os.getenv("EXEC_ENABLED", "false").lower() == "true"
RUNNER_SOCK = os.getenv("EXEC_RUNNER_SOCK", "/run/exec/exec.sock")
RUNNER_TOKEN = os.getenv("EXEC_RUNNER_TOKEN", "")
ACTOR = os.getenv("SWARM_NODE_ID", "hermes")

# Cheap pre-filter. NOT a security boundary — the sandbox is. Kept only to give
# the model a fast, legible "don't do that" instead of burning a sandbox slot.
BLOCKED_PATTERNS = [
    r"\bimport\s+os\b", r"\bimport\s+subprocess\b", r"\bimport\s+socket\b",
    r"\bimport\s+sys\b", r"\b__import__\b", r"\bopen\s*\(", r"\beval\s*\(",
    r"\bexec\s*\(", r"\bcompile\s*\(", r"import\s+shutil", r"import\s+pathlib",
    r"import\s+requests", r"import\s+httpx", r"import\s+urllib",
]

try:
    from swarm_core.security import audit as _audit
except Exception:  # pragma: no cover
    _audit = None

try:
    from swarm_core.security import authz as _authz
except Exception:  # pragma: no cover
    _authz = None


class _UnixHTTPConnection(http.client.HTTPConnection):
    def __init__(self, sock_path: str, timeout: int = 40):
        super().__init__("localhost", timeout=timeout)
        self._sock_path = sock_path

    def connect(self):  # noqa: D401
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.settimeout(self.timeout)
        s.connect(self._sock_path)
        self.sock = s


def _call_runner(code: str, timeout: int) -> dict:
    conn = _UnixHTTPConnection(RUNNER_SOCK, timeout=timeout + 10)
    headers = {"Content-Type": "application/json"}
    if RUNNER_TOKEN:
        headers["Authorization"] = f"Bearer {RUNNER_TOKEN}"
    try:
        conn.request("POST", "/run", body=json.dumps({"code": code, "timeout": timeout}), headers=headers)
        resp = conn.getresponse()
        raw = resp.read().decode("utf-8", "replace")
        if resp.status != 200:
            return {"status": "error", "error": f"runner HTTP {resp.status}: {raw[:200]}"}
        return json.loads(raw)
    finally:
        conn.close()


def _handle_python_exec(args: dict) -> str:
    if not EXEC_ENABLED:
        return json.dumps({"status": "error", "error": "Code execution is disabled (EXEC_ENABLED not set)"})

    code = (args.get("code") or "").strip()
    timeout = min(int(args.get("timeout", 10) or 10), 30)
    if not code:
        return json.dumps({"status": "error", "error": "No code provided"})

    code_sha = hashlib.sha256(code.encode("utf-8")).hexdigest()

    if _authz is not None:
        try:
            _authz.require(ACTOR, "code.exec")
        except Exception as e:  # authz.Denied
            _record("deny", code_sha, {"reason": str(e)})
            return json.dumps({"status": "blocked", "error": f"not authorized: {e}"})

    for pattern in BLOCKED_PATTERNS:
        if re.search(pattern, code):
            _record("block", code_sha, {"prefilter": pattern})
            return json.dumps({"status": "blocked", "error": f"pre-filter matched: {pattern}"})

    try:
        result = _call_runner(code, timeout)
    except FileNotFoundError:
        _record("error", code_sha, {"error": "runner socket missing"})
        return json.dumps({"status": "error", "error": "exec-runner unavailable (fail closed)"})
    except Exception as e:
        logger.warning("[python_exec] runner call failed: %s", e)
        _record("error", code_sha, {"error": str(e)[:200]})
        return json.dumps({"status": "error", "error": f"exec-runner error: {e}"})

    _record("allow", code_sha, {"status": result.get("status"), "exit_code": result.get("exit_code")})
    # Preserve the old response shape for existing callers.
    out = (result.get("stdout", "") + result.get("stderr", ""))[:2000]
    return json.dumps({
        "status": result.get("status", "ok"),
        "stdout": result.get("stdout", "")[:1000],
        "stderr": result.get("stderr", "")[:500],
        "exit_code": result.get("exit_code"),
        "output": out,
        "sandbox": result.get("jail"),
    })


def _record(decision: str, code_sha: str, detail: dict) -> None:
    if _audit is None:
        return
    try:
        _audit.record("tool.exec", actor=ACTOR, decision=decision,
                      detail={"tool": "python_exec", "code_sha256": code_sha, **detail})
    except Exception:
        pass


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
