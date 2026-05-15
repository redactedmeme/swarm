"""Railway ops tools — deploy, status, logs, restart services."""
from __future__ import annotations

import asyncio
import json
import logging
import os
import subprocess

logger = logging.getLogger("swarm-manager.railway")

SERVICE_MAP = {
    "redacted-chan-bot": "87d03512-83fc-4169-844f-2625030e4135",
    "smolting-telegram-bot": "2d6387ab-5e20-44fa-87c9-0045fbabfff1",
    "hermes-bot": "54fb26d2-def4-4a70-9a7a-a900f3418ed6",
    "swarm-runtime": "9f910ac1-7fa8-49ab-a30f-5a10db7d3d8a",
    "redactedbuilder-bot": "9e700bcc-fc26-49f0-a1a1-625d065885da",
    "redacted-website": "4f55d261-2235-4f89-9d6e-03f5da6b3eca",
    "redacted-dashboard": "879c2780-65d4-459b-955e-3e2f85b47bec",
}

BLOCKED_OPERATIONS = {"delete", "remove", "env_delete", "volume_delete"}


def _get_token() -> str:
    return os.getenv("RAILWAY_TOKEN", "")


def _run_railway(args: list[str], timeout: int = 30) -> tuple[str, str, int]:
    token = _get_token()
    if not token:
        return "", "RAILWAY_TOKEN not set", 1
    env = {**os.environ, "RAILWAY_TOKEN": token}
    try:
        proc = subprocess.run(
            ["railway"] + args,
            capture_output=True, text=True, timeout=timeout, env=env,
        )
        return proc.stdout.strip(), proc.stderr.strip(), proc.returncode
    except FileNotFoundError:
        return "", "railway CLI not found — install via npm i -g @railway/cli", 1
    except subprocess.TimeoutExpired:
        return "", f"Command timed out after {timeout}s", 1


def _validate_service(name: str) -> str | None:
    if name not in SERVICE_MAP:
        return f"Unknown service '{name}'. Known: {', '.join(sorted(SERVICE_MAP))}"
    return None


def _handle_railway_status(args: dict) -> str:
    service = args.get("service", "")
    if not service:
        results = {}
        for svc in SERVICE_MAP:
            out, err, rc = _run_railway(["status", "--service", svc, "--json"], timeout=15)
            results[svc] = out if rc == 0 else f"error: {err}"
        return json.dumps({"status": "ok", "services": results})

    err = _validate_service(service)
    if err:
        return json.dumps({"status": "error", "error": err})

    out, stderr, rc = _run_railway(["status", "--service", service, "--json"])
    if rc != 0:
        return json.dumps({"status": "error", "error": stderr or "status check failed"})
    return json.dumps({"status": "ok", "service": service, "details": out})


def _handle_railway_logs(args: dict) -> str:
    service = args.get("service", "")
    lines = args.get("lines", 50)
    err = _validate_service(service)
    if err:
        return json.dumps({"status": "error", "error": err})

    out, stderr, rc = _run_railway(
        ["logs", "--service", service, "--lines", str(min(lines, 200))],
        timeout=30,
    )
    if rc != 0:
        return json.dumps({"status": "error", "error": stderr or "log fetch failed"})
    log_lines = out.split("\n")[-lines:]
    return json.dumps({"status": "ok", "service": service, "lines": log_lines, "count": len(log_lines)})


def _handle_railway_restart(args: dict) -> str:
    service = args.get("service", "")
    err = _validate_service(service)
    if err:
        return json.dumps({"status": "error", "error": err})

    out, stderr, rc = _run_railway(["redeploy", "--service", service, "--yes"])
    if rc != 0:
        return json.dumps({"status": "error", "error": stderr or "restart failed"})
    return json.dumps({"status": "ok", "service": service, "message": "Redeployment triggered"})


def _handle_railway_deploy(args: dict) -> str:
    service = args.get("service", "")
    err = _validate_service(service)
    if err:
        return json.dumps({"status": "error", "error": err})

    return json.dumps({
        "status": "approval_required",
        "service": service,
        "message": f"Deploy to {service} requires approval. Send '/hermes approve deploy {service}' to confirm.",
    })


def register(ctx):
    ctx.register_tool(
        name="railway_status",
        toolset="swarm",
        schema={
            "name": "railway_status",
            "description": "Check the status of a Railway service. Leave service empty to check all services.",
            "parameters": {
                "type": "object",
                "properties": {
                    "service": {
                        "type": "string",
                        "description": f"Service name. Options: {', '.join(sorted(SERVICE_MAP))}",
                    },
                },
                "required": [],
            },
        },
        handler=_handle_railway_status,
    )

    ctx.register_tool(
        name="railway_logs",
        toolset="swarm",
        schema={
            "name": "railway_logs",
            "description": "Fetch recent logs from a Railway service.",
            "parameters": {
                "type": "object",
                "properties": {
                    "service": {
                        "type": "string",
                        "description": f"Service name. Options: {', '.join(sorted(SERVICE_MAP))}",
                    },
                    "lines": {
                        "type": "integer",
                        "description": "Number of log lines to fetch (max 200, default 50)",
                        "default": 50,
                    },
                },
                "required": ["service"],
            },
        },
        handler=_handle_railway_logs,
    )

    ctx.register_tool(
        name="railway_restart",
        toolset="swarm",
        schema={
            "name": "railway_restart",
            "description": "Restart (redeploy) a Railway service. Use when an agent appears crashed or unresponsive.",
            "parameters": {
                "type": "object",
                "properties": {
                    "service": {
                        "type": "string",
                        "description": f"Service name. Options: {', '.join(sorted(SERVICE_MAP))}",
                    },
                },
                "required": ["service"],
            },
        },
        handler=_handle_railway_restart,
    )

    ctx.register_tool(
        name="railway_deploy",
        toolset="swarm",
        schema={
            "name": "railway_deploy",
            "description": "Request a deploy to a Railway service. Requires approval from redacted-chan before executing.",
            "parameters": {
                "type": "object",
                "properties": {
                    "service": {
                        "type": "string",
                        "description": f"Service name. Options: {', '.join(sorted(SERVICE_MAP))}",
                    },
                },
                "required": ["service"],
            },
        },
        handler=_handle_railway_deploy,
    )

    logger.info("[swarm-manager] Railway tools registered (4 tools)")
