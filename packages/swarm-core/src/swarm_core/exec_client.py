"""Shared client for the ``apps/exec-runner`` sandbox (IronClaw control 1).

LLM-supplied code is shipped over a unix socket to a container that has **no
secrets in its environment** and ``network_mode: none``; the runner enforces
CPU / memory / file-size / nproc rlimits and a wall-clock kill and runs
``python3 -I -S`` (no site-packages). This module is the transport plus the
capability check, the cheap pre-filter, and the audit record — the same path
``apps/hermes`` used inline, factored so other agents can reuse it.

    from swarm_core.exec_client import run_code
    run_code("print(sum(range(100)))", actor="redacted-chan")

``EXEC_RUNNER_SOCK`` / ``EXEC_RUNNER_TOKEN`` configure the transport. If the
runner is unreachable this fails closed (returns an error, runs nothing).
"""
from __future__ import annotations

import hashlib
import http.client
import json
import os
import re
import socket

DEFAULT_SOCK = "/run/exec/exec.sock"
TIMEOUT_MAX = 30

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

    def connect(self):
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.settimeout(self.timeout)
        s.connect(self._sock_path)
        self.sock = s


def _record(actor: str, decision: str, code_sha: str, detail: dict) -> None:
    if _audit is None:
        return
    try:
        _audit.record("tool.exec", actor=actor, decision=decision,
                      detail={"tool": "python_exec", "code_sha256": code_sha, **detail})
    except Exception:
        pass


def _call_runner(code: str, timeout: int, sock: str, token: str) -> dict:
    conn = _UnixHTTPConnection(sock, timeout=timeout + 10)
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        conn.request("POST", "/run", body=json.dumps({"code": code, "timeout": timeout}), headers=headers)
        resp = conn.getresponse()
        raw = resp.read().decode("utf-8", "replace")
        if resp.status != 200:
            return {"status": "error", "error": f"runner HTTP {resp.status}: {raw[:200]}"}
        return json.loads(raw)
    finally:
        conn.close()


def run_code(
    code: str,
    *,
    actor: str,
    timeout: int = 10,
    sock: str | None = None,
    token: str | None = None,
) -> dict:
    """Run ``code`` in the exec-runner sandbox as ``actor``.

    Returns a normalized dict: ``{"status": "ok"|"error"|"blocked", "stdout",
    "stderr", "exit_code", "output", "sandbox"}``. ``actor`` must hold the
    ``code.exec`` capability. Never raises for policy / transport failures.
    """
    code = (code or "").strip()
    if not code:
        return {"status": "error", "error": "No code provided"}
    timeout = min(int(timeout or 10), TIMEOUT_MAX)
    sock = sock or os.getenv("EXEC_RUNNER_SOCK", DEFAULT_SOCK)
    token = token if token is not None else os.getenv("EXEC_RUNNER_TOKEN", "")
    code_sha = hashlib.sha256(code.encode("utf-8")).hexdigest()

    if _authz is not None:
        try:
            _authz.require(actor, "code.exec")
        except Exception as e:  # authz.Denied
            _record(actor, "deny", code_sha, {"reason": str(e)})
            return {"status": "blocked", "error": f"not authorized: {e}"}

    for pattern in BLOCKED_PATTERNS:
        if re.search(pattern, code):
            _record(actor, "block", code_sha, {"prefilter": pattern})
            return {"status": "blocked", "error": f"pre-filter matched: {pattern}"}

    try:
        result = _call_runner(code, timeout, sock, token)
    except FileNotFoundError:
        _record(actor, "error", code_sha, {"error": "runner socket missing"})
        return {"status": "error", "error": "exec-runner unavailable (fail closed)"}
    except Exception as e:  # noqa: BLE001
        _record(actor, "error", code_sha, {"error": str(e)[:200]})
        return {"status": "error", "error": f"exec-runner error: {e}"}

    _record(actor, "allow", code_sha, {"status": result.get("status"), "exit_code": result.get("exit_code")})
    out = (result.get("stdout", "") + result.get("stderr", ""))[:2000]
    return {
        "status": result.get("status", "ok"),
        "stdout": result.get("stdout", "")[:1000],
        "stderr": result.get("stderr", "")[:500],
        "exit_code": result.get("exit_code"),
        "output": out,
        "sandbox": result.get("jail"),
    }
