"""Railway ops tools — deploy, status, logs, restart services via GraphQL API."""
from __future__ import annotations

import json
import logging
import os
import time

import requests

logger = logging.getLogger("swarm-manager.railway")

RAILWAY_API = "https://backboard.railway.com/graphql/v2"
ENV_ID = "b07b0204-16f5-4063-9a24-f3b6dfe45e53"

SERVICE_MAP = {
    "redacted-chan-bot":       "87d03512-83fc-4169-844f-2625030e4135",
    "smolting-telegram-bot":   "2d6387ab-5e20-44fa-87c9-0045fbabfff1",
    "hermes-bot":              "54fb26d2-def4-4a70-9a7a-a900f3418ed6",
    "swarm-runtime":           "9f910ac1-7fa8-49ab-a30f-5a10db7d3d8a",
    "redactedbuilder-bot":     "9e700bcc-fc26-49f0-a1a1-625d065885da",
    "redacted-website":        "4f55d261-2235-4f89-9d6e-03f5da6b3eca",
    "redacted-dashboard":      "879c2780-65d4-459b-955e-3e2f85b47bec",
}


def _token() -> str:
    return os.getenv("RAILWAY_TOKEN", "")


def _gql(query: str, variables: dict | None = None, timeout: int = 20) -> dict:
    """Execute a Railway GraphQL query. Returns parsed JSON or raises."""
    token = _token()
    if not token:
        raise RuntimeError("RAILWAY_TOKEN not set")
    resp = requests.post(
        RAILWAY_API,
        json={"query": query, "variables": variables or {}},
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        timeout=timeout,
    )
    resp.raise_for_status()
    data = resp.json()
    if "errors" in data:
        raise RuntimeError(f"GraphQL errors: {data['errors']}")
    return data.get("data", {})


def _validate_service(name: str) -> str | None:
    if name not in SERVICE_MAP:
        return f"Unknown service '{name}'. Known: {', '.join(sorted(SERVICE_MAP))}"
    return None


# ── Status ───────────────────────────────────────────────────────────────────

_STATUS_QUERY = """
query ServiceStatus($serviceId: String!, $environmentId: String!) {
  serviceInstance(serviceId: $serviceId, environmentId: $environmentId) {
    serviceId
    buildCommand
    startCommand
    domains { serviceDomains { domain } }
    latestDeployment {
      id
      status
      createdAt
      url
    }
  }
}
"""


def _handle_railway_status(args: dict) -> str:
    service = args.get("service", "")
    services = [service] if service else list(SERVICE_MAP.keys())

    if service:
        err = _validate_service(service)
        if err:
            return json.dumps({"status": "error", "error": err})

    results = {}
    for svc in services:
        svc_id = SERVICE_MAP[svc]
        try:
            data = _gql(_STATUS_QUERY, {"serviceId": svc_id, "environmentId": ENV_ID})
            inst = data.get("serviceInstance") or {}
            dep = inst.get("latestDeployment") or {}
            results[svc] = {
                "status": dep.get("status", "UNKNOWN"),
                "deployment_id": dep.get("id", ""),
                "deployed_at": dep.get("createdAt", ""),
                "url": dep.get("url", ""),
            }
        except Exception as e:
            results[svc] = {"status": "error", "error": str(e)}

    if len(services) == 1:
        svc = services[0]
        return json.dumps({"status": "ok", "service": svc, **results[svc]})
    return json.dumps({"status": "ok", "services": results})


# ── Logs ─────────────────────────────────────────────────────────────────────

_DEPLOYMENTS_QUERY = """
query Deployments($serviceId: String!) {
  deployments(input: { serviceId: $serviceId }) {
    edges { node { id status createdAt } }
  }
}
"""

_BUILD_LOGS_QUERY = """
query BuildLogs($deploymentId: String!) {
  buildLogs(deploymentId: $deploymentId) { message }
}
"""

_DEPLOY_LOGS_QUERY = """
query DeployLogs($deploymentId: String!) {
  deploymentLogs(deploymentId: $deploymentId, limit: 100) { message timestamp }
}
"""


def _handle_railway_logs(args: dict) -> str:
    service = args.get("service", "")
    lines = min(int(args.get("lines", 50)), 200)
    log_type = args.get("type", "runtime")  # "runtime" or "build"

    err = _validate_service(service)
    if err:
        return json.dumps({"status": "error", "error": err})

    svc_id = SERVICE_MAP[service]
    try:
        # Get latest deployment id
        data = _gql(_DEPLOYMENTS_QUERY, {"serviceId": svc_id})
        edges = (data.get("deployments") or {}).get("edges", [])
        if not edges:
            return json.dumps({"status": "error", "error": "No deployments found"})
        dep_id = edges[0]["node"]["id"]

        if log_type == "build":
            data2 = _gql(_BUILD_LOGS_QUERY, {"deploymentId": dep_id})
            msgs = [e.get("message", "") for e in (data2.get("buildLogs") or [])]
        else:
            data2 = _gql(_DEPLOY_LOGS_QUERY, {"deploymentId": dep_id})
            msgs = [e.get("message", "") for e in (data2.get("deploymentLogs") or [])]

        log_lines = msgs[-lines:]
        return json.dumps({
            "status": "ok",
            "service": service,
            "deployment_id": dep_id,
            "lines": log_lines,
            "count": len(log_lines),
        })
    except Exception as e:
        logger.error("[railway] Log fetch failed for %s: %s", service, e)
        return json.dumps({"status": "error", "error": str(e)})


# ── Restart ──────────────────────────────────────────────────────────────────

_REDEPLOY_MUTATION = """
mutation Redeploy($serviceId: String!, $environmentId: String!) {
  serviceInstanceRedeploy(serviceId: $serviceId, environmentId: $environmentId)
}
"""


def _handle_railway_restart(args: dict) -> str:
    service = args.get("service", "")
    err = _validate_service(service)
    if err:
        return json.dumps({"status": "error", "error": err})

    svc_id = SERVICE_MAP[service]
    try:
        _gql(_REDEPLOY_MUTATION, {"serviceId": svc_id, "environmentId": ENV_ID})
        return json.dumps({"status": "ok", "service": service, "message": "Redeployment triggered"})
    except Exception as e:
        logger.error("[railway] Restart failed for %s: %s", service, e)
        return json.dumps({"status": "error", "error": str(e)})


# ── Deploy (approval gate) ────────────────────────────────────────────────────

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


# ── Registration ─────────────────────────────────────────────────────────────

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
                    "type": {
                        "type": "string",
                        "description": "Log type: 'runtime' (default) or 'build'",
                        "enum": ["runtime", "build"],
                        "default": "runtime",
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

    logger.info("[swarm-manager] Railway tools registered (4 tools) — using GraphQL API")
