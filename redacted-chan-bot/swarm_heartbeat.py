"""
Redis heartbeat keys for swarm agent liveness (webchat /agents, dashboard).

Key: swarm:heartbeat:{agent_id}
Value: JSON {"agent", "ts" (ISO), "unix" (float), ...metadata}
Legacy: plain float unix timestamp (still supported).
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from typing import Any, Optional

HEARTBEAT_KEY_PREFIX = "swarm:heartbeat:"
HEARTBEAT_TTL_SEC = 600
ONLINE_THRESHOLD_SEC = 300

# Canonical id → Redis keys to check (first fresh match wins)
HEARTBEAT_LOOKUP_KEYS: dict[str, list[str]] = {
    "redacted-chan": ["redacted-chan"],
    "hermes": ["hermes"],
    "smolting": ["smolting", "redactedintern"],
    "builder": ["builder", "redactedbuilder"],
    "runtime": ["runtime"],
}

SWARM_AGENT_IDS = list(HEARTBEAT_LOOKUP_KEYS.keys())


def heartbeat_redis_key(agent_id: str) -> str:
    return f"{HEARTBEAT_KEY_PREFIX}{agent_id}"


def build_heartbeat_payload(agent: str, metadata: Optional[dict] = None) -> dict[str, Any]:
    now = time.time()
    return {
        "agent": agent,
        "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "unix": now,
        **(metadata or {}),
    }


def write_redis_heartbeat(redis_client, agent: str, metadata: Optional[dict] = None) -> None:
    """Sync Redis client (redis-py)."""
    payload = build_heartbeat_payload(agent, metadata)
    redis_client.set(
        heartbeat_redis_key(agent),
        json.dumps(payload, ensure_ascii=False),
        ex=HEARTBEAT_TTL_SEC,
    )


def parse_heartbeat_value(raw: Optional[str], now: Optional[float] = None) -> dict[str, Any]:
    """Parse a heartbeat key value → {online, age_s, ts, last_seen}."""
    now = now if now is not None else time.time()
    if not raw:
        return {"online": False, "age_s": None, "ts": None, "last_seen": None, "present": False}

    ts: Optional[float] = None
    last_seen: Optional[str] = raw
    try:
        stripped = raw.strip()
        if stripped.startswith("{"):
            data = json.loads(stripped)
            last_seen = data.get("ts") or last_seen
            if "unix" in data:
                ts = float(data["unix"])
            elif data.get("ts"):
                ts = datetime.fromisoformat(str(data["ts"]).replace("Z", "+00:00")).timestamp()
        else:
            ts = float(stripped)
            last_seen = str(ts)
    except (ValueError, TypeError, json.JSONDecodeError):
        return {"online": False, "age_s": None, "ts": None, "last_seen": None, "present": True}

    if ts is None:
        return {"online": False, "age_s": None, "ts": None, "last_seen": last_seen, "present": True}

    age_s = max(0.0, now - ts)
    return {
        "online": age_s < ONLINE_THRESHOLD_SEC,
        "age_s": round(age_s),
        "ts": ts,
        "last_seen": last_seen,
        "present": True,
    }


def pick_best_heartbeat(candidates: list[dict[str, Any]]) -> dict[str, Any]:
    """Choose freshest heartbeat; prefer online over offline."""
    if not candidates:
        return parse_heartbeat_value(None)
    present = [c for c in candidates if c.get("present")]
    if not present:
        return parse_heartbeat_value(None)

    def sort_key(c: dict[str, Any]) -> tuple:
        age = c.get("age_s")
        return (
            0 if c.get("online") else 1,
            age if age is not None else 10**9,
        )

    return min(present, key=sort_key)


async def read_heartbeat_async(redis_client, agent_id: str) -> dict[str, Any]:
    """Read best heartbeat for agent using async Redis."""
    keys = HEARTBEAT_LOOKUP_KEYS.get(agent_id, [agent_id])
    now = time.time()
    candidates = []
    for key in keys:
        raw = await redis_client.get(heartbeat_redis_key(key))
        if raw is not None:
            parsed = parse_heartbeat_value(raw, now)
            parsed["redis_key"] = key
            candidates.append(parsed)
    return pick_best_heartbeat(candidates)


async def read_heartbeat_keys_async(redis_client, agent_ids: list[str]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for agent_id in agent_ids:
        out[agent_id] = await read_heartbeat_async(redis_client, agent_id)
    return out
