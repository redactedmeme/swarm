"""Swarm liveness snapshot — read-only observation of mesh health.

Reads signals the mesh already emits into Redis; writes nothing:
  - heartbeats:  swarm:heartbeat:{agent}  (JSON w/ unix ts, TTL 600s)
  - queue depth: ZCARD swarm:pending:{agent}  and  swarm:pending:all

Exposes a single collect_liveness(redis_client) -> dict used by both the
/liveness HTTP endpoint (api.py) and the periodic alert sweep (alerting.py).
"""
from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any, Optional

import redis as redis_lib

import common as C
import swarm_heartbeat as hb

_PENDING_KEY_PREFIX = "swarm:pending:"

# module-level sync client, lazily created and reused across requests/sweeps
_client = None


def get_redis():
    """Sync Redis client, same construction as ingest/redis_msgs.py."""
    global _client
    if _client is None:
        _client = redis_lib.from_url(
            C.REDIS_URL, decode_responses=True, socket_connect_timeout=5
        )
    return _client


def _read_heartbeat(redis_client, agent_id: str, now: float) -> dict[str, Any]:
    """Sync analogue of swarm_heartbeat.read_heartbeat_async."""
    keys = hb.HEARTBEAT_LOOKUP_KEYS.get(agent_id, [agent_id])
    candidates = []
    for key in keys:
        raw = redis_client.get(hb.heartbeat_redis_key(key))
        if raw is not None:
            parsed = hb.parse_heartbeat_value(raw, now)
            parsed["redis_key"] = key
            candidates.append(parsed)
    return hb.pick_best_heartbeat(candidates)


def _pending_depth(redis_client, alias_keys: list[str]) -> int:
    total = 0
    for key in alias_keys:
        try:
            total += int(redis_client.zcard(f"{_PENDING_KEY_PREFIX}{key}") or 0)
        except Exception:
            pass
    return total


def collect_liveness(redis_client=None) -> dict[str, Any]:
    """Snapshot every known agent's heartbeat freshness + pending-queue depth."""
    r = redis_client or get_redis()
    now = time.time()

    agents: dict[str, Any] = {}
    for agent_id, alias_keys in hb.HEARTBEAT_LOOKUP_KEYS.items():
        beat = _read_heartbeat(r, agent_id, now)
        agents[agent_id] = {
            "online": beat.get("online", False),
            "present": beat.get("present", False),
            "age_s": beat.get("age_s"),
            "last_seen": beat.get("last_seen"),
            "pending": _pending_depth(r, alias_keys),
        }

    try:
        pending_all = int(r.zcard(f"{_PENDING_KEY_PREFIX}all") or 0)
    except Exception:
        pending_all = 0

    return {
        "agents": agents,
        "pending_all": pending_all,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
