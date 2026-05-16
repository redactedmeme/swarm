"""Health monitoring — heartbeat sweep + auto-recovery."""
from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timezone

logger = logging.getLogger("swarm-manager.health")

STALE_THRESHOLD_SECONDS = 300  # 5 minutes

AGENT_SERVICE_MAP = {
    "redactedintern": "smolting-telegram-bot",
    "hermes": "hermes-bot",
    "redacted-chan": "redacted-chan-bot",
    "redactedbuilder": "redactedbuilder-bot",
}


def _get_redis():
    try:
        from .inbox_tools import _get_redis as _ir
    except ImportError:
        from inbox_tools import _get_redis as _ir
    return _ir()


def _handle_health_check(args: dict) -> str:
    r = _get_redis()
    if not r:
        return json.dumps({"status": "error", "error": "Redis unavailable"})

    agents = list(AGENT_SERVICE_MAP.keys())
    report = {}
    now = time.time()

    for agent in agents:
        raw = r.get(f"swarm:heartbeat:{agent}")
        if not raw:
            report[agent] = {"status": "unknown", "last_seen": None, "stale": True}
            continue
        try:
            data = json.loads(raw)
            ts_str = data.get("ts", "")
            ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00")).timestamp()
            age = now - ts
            report[agent] = {
                "status": "healthy" if age < STALE_THRESHOLD_SECONDS else "stale",
                "last_seen": ts_str,
                "age_seconds": round(age),
                "stale": age >= STALE_THRESHOLD_SECONDS,
                "service": AGENT_SERVICE_MAP.get(agent),
            }
        except Exception as e:
            report[agent] = {"status": "error", "error": str(e)}

    stale = [a for a, r in report.items() if r.get("stale")]
    return json.dumps({
        "status": "ok",
        "agents": report,
        "stale_agents": stale,
        "healthy_count": sum(1 for r in report.values() if r.get("status") == "healthy"),
        "total_count": len(report),
    })


def register(ctx):
    ctx.register_tool(
        name="swarm_health_check",
        toolset="swarm",
        schema={
            "name": "swarm_health_check",
            "description": "Check heartbeat status of all swarm agents. Reports which agents are healthy, stale, or unknown. Stale agents (no heartbeat in 5min) may need a restart via railway_restart.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
        handler=_handle_health_check,
    )

    logger.info("[swarm-manager] Health tools registered (1 tool)")
