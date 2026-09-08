"""workspace_* — thin client to the apps/workspace service (fs + shell + browser).

The workspace is a long-lived per-agent container with a real filesystem, shell
and browser (docs/plans/grok-bot-parity.md §5/§6). It is reached over a unix
socket (``WORKSPACE_SOCK``) with a per-agent bearer token
(``WORKSPACE_TOKEN_<AGENT>``) and an ``X-Swarm-Agent`` header.

Registration is gated behind ``WORKSPACE_ENABLED`` (default off), in the style of
``EXEC_ENABLED``. ``workspace_shell`` additionally needs the ``workspace.shell``
capability *and* a live approval token (it has network and persistence); pass it
as ``approval`` in the tool args. ``workspace_browse`` needs ``workspace.browse``.
"""
from __future__ import annotations

import json
import logging
import os

from swarm_core.workspace_client import WorkspaceClient

logger = logging.getLogger("swarm-manager.workspace")

WORKSPACE_ENABLED = os.getenv("WORKSPACE_ENABLED", "false").lower() == "true"
WORKSPACE_SOCK = os.getenv("WORKSPACE_SOCK", "/run/workspace/workspace.sock")
ACTOR = os.getenv("SWARM_NODE_ID", "hermes")

try:
    from swarm_core.security import authz as _authz
except Exception:  # pragma: no cover
    _authz = None

_WS = WorkspaceClient(ACTOR, sock=WORKSPACE_SOCK)


def _call(method: str, path: str, body: dict | None, timeout: int = 90) -> dict:
    return _WS.call(method, path, body, timeout=timeout)


def _require(capability: str, approval: str | None) -> str | None:
    if _authz is None:
        return json.dumps({"status": "error", "error": "authz unavailable"})
    try:
        _authz.require(ACTOR, capability, approval=approval)
    except Exception as e:
        return json.dumps({"status": "blocked", "error": f"not authorized for {capability}: {e}"})
    return None


# ── handlers ─────────────────────────────────────────────────────────────────

def _handle_workspace_read(args: dict) -> str:
    return json.dumps(_call("POST", "/fs/read", {"path": args.get("path", "")}))


def _handle_workspace_write(args: dict) -> str:
    return json.dumps(_call("POST", "/fs/write", {
        "path": args.get("path", ""),
        "content": args.get("content", ""),
        "append": bool(args.get("append")),
    }))


def _handle_workspace_list(args: dict) -> str:
    return json.dumps(_call("POST", "/fs/list", {"path": args.get("path", "")}))


def _handle_workspace_shell(args: dict) -> str:
    denied = _require("workspace.shell", args.get("approval"))
    if denied:
        return denied
    return json.dumps(_call("POST", "/shell", {
        "cmd": args.get("cmd", ""),
        "timeout": args.get("timeout"),
        "cwd": args.get("cwd", ""),
    }, timeout=int(args.get("timeout") or 60) + 30))


def _handle_routine_promote(args: dict) -> str:
    # A promoted routine will autonomously run its steps (incl. shell) on a
    # schedule, so promotion needs the shell capability + approval.
    denied = _require("workspace.shell", args.get("approval"))
    if denied:
        return denied
    trace_id = (args.get("trace_id") or "").strip()
    if not trace_id:
        return json.dumps({"status": "error", "error": "trace_id is required"})
    try:
        interval_s = int(args.get("interval_s") or 3600)
    except (TypeError, ValueError):
        return json.dumps({"status": "error", "error": "interval_s must be an integer"})
    trace = _call("GET", f"/trace/{trace_id}", None)
    if trace.get("status") != "ok":
        return json.dumps(trace)
    try:
        from swarm_core.routines import promote
        out = promote(
            trace.get("steps", []),
            name=args.get("name") or f"routine-{trace_id[:8]}",
            interval_s=interval_s,
            description=args.get("description", ""),
            agent=ACTOR,
        )
        return json.dumps({"status": "ok", **out})
    except Exception as e:  # noqa: BLE001
        return json.dumps({"status": "error", "error": f"promote failed: {e}"})


def _handle_workspace_browse(args: dict) -> str:
    denied = _require("workspace.browse", args.get("approval"))
    if denied:
        return denied
    session = args.get("session", "default")
    url = (args.get("url") or "").strip()
    if url:
        nav = _call("POST", "/browser/goto", {"url": url, "session": session})
        if nav.get("status") != "ok":
            return json.dumps(nav)
    return json.dumps(_call("POST", "/browser/read", {
        "session": session, "max_chars": int(args.get("max_chars") or 8000),
    }))


# ── registration ─────────────────────────────────────────────────────────────

def register(ctx):
    ctx.register_tool(
        name="workspace_read", toolset="swarm",
        schema={"name": "workspace_read",
                "description": "Read a file from this agent's persistent workspace.",
                "parameters": {"type": "object", "properties": {
                    "path": {"type": "string", "description": "Path relative to the workspace root"},
                }, "required": ["path"]}},
        handler=_handle_workspace_read,
    )
    ctx.register_tool(
        name="workspace_write", toolset="swarm",
        schema={"name": "workspace_write",
                "description": "Write a file in this agent's persistent workspace.",
                "parameters": {"type": "object", "properties": {
                    "path": {"type": "string"},
                    "content": {"type": "string"},
                    "append": {"type": "boolean", "description": "Append instead of overwrite"},
                }, "required": ["path", "content"]}},
        handler=_handle_workspace_write,
    )
    ctx.register_tool(
        name="workspace_list", toolset="swarm",
        schema={"name": "workspace_list",
                "description": "List a directory in this agent's persistent workspace.",
                "parameters": {"type": "object", "properties": {
                    "path": {"type": "string", "description": "Directory path (default: root)"},
                }, "required": []}},
        handler=_handle_workspace_list,
    )
    ctx.register_tool(
        name="workspace_shell", toolset="swarm",
        schema={"name": "workspace_shell",
                "description": ("Run a shell command in this agent's persistent workspace "
                                "(has network and persistence). Requires the workspace.shell "
                                "capability and a live approval token."),
                "parameters": {"type": "object", "properties": {
                    "cmd": {"type": "string"},
                    "timeout": {"type": "integer", "description": "Seconds (max 300)"},
                    "cwd": {"type": "string", "description": "Working dir relative to root"},
                    "approval": {"type": "string", "description": "Granted approval token"},
                }, "required": ["cmd"]}},
        handler=_handle_workspace_shell,
    )
    ctx.register_tool(
        name="workspace_browse", toolset="swarm",
        schema={"name": "workspace_browse",
                "description": ("Navigate the workspace browser to a URL (optional) and return "
                                "the readable page content. Requires the workspace.browse capability."),
                "parameters": {"type": "object", "properties": {
                    "url": {"type": "string", "description": "URL to open first (optional)"},
                    "session": {"type": "string", "description": "Named browser session (default 'default')"},
                    "max_chars": {"type": "integer"},
                    "approval": {"type": "string"},
                }, "required": []}},
        handler=_handle_workspace_browse,
    )
    ctx.register_tool(
        name="routine_promote", toolset="swarm",
        schema={"name": "routine_promote",
                "description": ("Distil a recorded workspace action trace into a skill doc + a "
                                "scheduled routine that replays it. Needs workspace.shell + approval."),
                "parameters": {"type": "object", "properties": {
                    "trace_id": {"type": "string", "description": "id from POST /trace/start"},
                    "name": {"type": "string"},
                    "interval_s": {"type": "integer", "description": "Replay interval in seconds (>=60)"},
                    "description": {"type": "string"},
                    "approval": {"type": "string"},
                }, "required": ["trace_id"]}},
        handler=_handle_routine_promote,
    )
    logger.info("[swarm-manager] Workspace tools registered (6 tools) → %s", WORKSPACE_SOCK)
