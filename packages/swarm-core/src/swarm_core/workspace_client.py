"""Shared client for the ``apps/workspace`` service (per-agent fs + shell + browser).

The workspace is a long-lived per-agent container reached over a unix socket
(``WORKSPACE_SOCK``) with a per-agent bearer token (``WORKSPACE_TOKEN_<AGENT>``,
resolved via ``swarm_core.security.secrets``) and an ``X-Swarm-Agent`` header
(docs/plans/grok-bot-parity.md §5/§6).

This module is transport only — it does **not** do capability checks. Callers
that expose ``shell`` / ``browse`` to an LLM must gate them with
``swarm_core.security.authz.require(agent, "workspace.shell" | "workspace.browse")``
themselves, the way ``apps/hermes`` does.

    wc = WorkspaceClient("smolting")
    wc.write("notes/todo.md", "- ship it\n")
    wc.read("notes/todo.md")            # -> {"status": "ok", "text": ...}
    wc.browse("https://example.com")    # needs the workspace.browse grant
"""
from __future__ import annotations

import http.client
import json
import os
import socket

try:
    from swarm_core.security.secrets import get_secret as _get_secret
except Exception:  # pragma: no cover - secrets layer optional
    def _get_secret(name, default=None, *, required=False):
        return os.getenv(name, default)

DEFAULT_SOCK = "/run/workspace/workspace.sock"


def enabled() -> bool:
    """True when the caller has opted into the workspace (``WORKSPACE_ENABLED``)."""
    return os.getenv("WORKSPACE_ENABLED", "false").lower() == "true"


def token_env_for(agent: str) -> str:
    return "WORKSPACE_TOKEN_" + agent.upper().replace("-", "_")


class _UnixHTTPConnection(http.client.HTTPConnection):
    def __init__(self, sock_path: str, timeout: int = 90):
        super().__init__("localhost", timeout=timeout)
        self._sock_path = sock_path

    def connect(self):
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.settimeout(self.timeout)
        s.connect(self._sock_path)
        self.sock = s


class WorkspaceClient:
    """Per-agent handle to the workspace service.

    ``agent`` is sent as ``X-Swarm-Agent`` and also names the bearer-token env
    var (``WORKSPACE_TOKEN_<AGENT>``) unless ``token`` is passed explicitly.
    """

    def __init__(
        self,
        agent: str,
        *,
        sock: str | None = None,
        token: str | None = None,
        timeout: int = 90,
    ) -> None:
        self.agent = agent
        self.sock = sock or os.getenv("WORKSPACE_SOCK", DEFAULT_SOCK)
        self.timeout = timeout
        self._token = token

    # ── transport ────────────────────────────────────────────────────────────
    def _resolve_token(self) -> str:
        if self._token:
            return self._token
        return (_get_secret(token_env_for(self.agent)) or "").strip()

    def call(self, method: str, path: str, body: dict | None = None, *, timeout: int | None = None) -> dict:
        conn = _UnixHTTPConnection(self.sock, timeout=timeout or self.timeout)
        headers = {
            "Content-Type": "application/json",
            "X-Swarm-Agent": self.agent,
            "Authorization": f"Bearer {self._resolve_token()}",
        }
        try:
            conn.request(method, path, body=json.dumps(body or {}), headers=headers)
            resp = conn.getresponse()
            raw = resp.read().decode("utf-8", "replace")
            try:
                data = json.loads(raw)
            except Exception:
                data = {"status": "error", "error": raw[:300]}
            if resp.status != 200 and "error" not in data:
                data = {"status": "error", "error": f"HTTP {resp.status}: {raw[:200]}"}
            return data
        except FileNotFoundError:
            return {"status": "error", "error": "workspace service unavailable (socket missing)"}
        except Exception as e:  # noqa: BLE001
            return {"status": "error", "error": f"workspace call failed: {e}"}
        finally:
            conn.close()

    # ── filesystem (token only, no capability) ───────────────────────────────
    def read(self, path: str) -> dict:
        return self.call("POST", "/fs/read", {"path": path})

    def write(self, path: str, content: str, *, append: bool = False) -> dict:
        return self.call("POST", "/fs/write", {"path": path, "content": content, "append": bool(append)})

    def list(self, path: str = "") -> dict:
        return self.call("POST", "/fs/list", {"path": path})

    # ── browser (caller must hold workspace.browse) ──────────────────────────
    def browse(self, url: str | None = None, *, session: str = "default", max_chars: int = 8000) -> dict:
        if url:
            nav = self.call("POST", "/browser/goto", {"url": url, "session": session})
            if nav.get("status") != "ok":
                return nav
        return self.call("POST", "/browser/read", {"session": session, "max_chars": int(max_chars)})

    # ── shell (caller must hold workspace.shell + a live approval) ────────────
    def shell(self, cmd: str, *, timeout: int | None = None, cwd: str = "") -> dict:
        return self.call(
            "POST", "/shell",
            {"cmd": cmd, "timeout": timeout, "cwd": cwd},
            timeout=(int(timeout) if timeout else 60) + 30,
        )

    # ── demonstration traces ────────────────────────────────────────────────
    def trace_start(self) -> dict:
        return self.call("POST", "/trace/start", {})

    def trace_stop(self) -> dict:
        return self.call("POST", "/trace/stop", {})

    def trace_get(self, trace_id: str) -> dict:
        return self.call("GET", f"/trace/{trace_id}", None)
