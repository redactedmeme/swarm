"""SwarmInbox tools — Redis-backed inter-agent message queue."""
from __future__ import annotations

import json
import logging
import os
import threading
import time
import uuid
from datetime import datetime, timezone

logger = logging.getLogger("swarm-manager.inbox")

# ── Redis client (lazy singleton) ────────────────────────────────────────────

_redis = None
_redis_ok = False
_lock = threading.Lock()


def _get_redis():
    global _redis, _redis_ok
    if _redis is not None:
        return _redis if _redis_ok else None
    url = os.getenv("REDIS_URL", "")
    if not url:
        _redis_ok = False
        return None
    try:
        import redis as redis_lib
        _redis = redis_lib.from_url(url, decode_responses=True, socket_connect_timeout=3)
        _redis.ping()
        _redis_ok = True
        logger.info("[inbox] Redis connected")
    except Exception as e:
        logger.warning("[inbox] Redis unavailable: %s", e)
        _redis_ok = False
    return _redis if _redis_ok else None


AGENTS = {
    "redactedintern", "redactedbuilder", "redactedgovimprover",
    "mandalaasettler", "redactedbankrbot", "hermes", "redacted-chan",
    "smolting", "degen",
}

ALLOWED_TASK_SENDERS = {"redacted-chan"}

# Broadcast fan-out targets. AGENTS is a static roster and has drifted from reality —
# it still lists three agents that were never deployed (redactedgovimprover,
# mandalaasettler, redactedbankrbot) and omits one that was (smolting). Fanning a
# broadcast to a name that never runs writes an index entry nobody ever reaps, because
# reap-on-read only fires when *that* agent reads its own queue. Three such queues had
# accumulated ~93k orphan entries each before this was caught.
#
# So target agents with a live heartbeat instead: the roster then maintains itself as
# agents come and go, and a name that stops running stops receiving.


def _live_agents(r) -> set[str]:
    """Agents with an unexpired heartbeat key. Empty set if the scan fails."""
    try:
        return {k.split(":")[-1] for k in r.scan_iter(match="swarm:heartbeat:*", count=100)}
    except Exception:
        return set()


def _broadcast_targets(r) -> set[str]:
    """Who a `to="all"` message is indexed for.

    Falls back to the static roster when no heartbeats are visible — a momentary Redis
    hiccup must not silently deliver a broadcast to nobody.
    """
    return (_live_agents(r) & AGENTS) or set(AGENTS)


def _cleanup_keys(r) -> set[str]:
    """Every queue a msg id might be indexed in, for removal on claim/complete."""
    return set(AGENTS) | _live_agents(r)

_DONE_TTL = 7 * 86400


# ── Core inbox operations ────────────────────────────────────────────────────
#
# These delegate to the canonical bus (``swarm_core.security.inbox``) so there is
# one implementation. The wrappers keep this module's historical signatures
# (leading underscore, ``str | None`` / ``bool`` returns) that swarm_manager.py
# and health_tools.py already call.

from swarm_core.security import inbox as _bus  # noqa: E402


def _write_message(from_agent: str, to_agent: str, msg_type: str,
                   payload: dict, reply_to: str | None = None) -> str | None:
    try:
        return _bus.write_message(from_agent, to_agent, msg_type, payload, reply_to)
    except Exception as e:  # bad agent name / bus unavailable
        logger.warning("[inbox] write_message failed: %s", e)
        return None


def _read_pending(for_agent: str = "hermes") -> list[dict]:
    try:
        return _bus.read_pending(for_agent)
    except Exception as e:
        logger.warning("[inbox] read_pending failed: %s", e)
        return []


def _claim_message(msg_id: str) -> bool:
    try:
        return _bus.claim_message(msg_id)
    except Exception as e:
        logger.warning("[inbox] claim_message failed: %s", e)
        return False


def _complete_message(msg_id: str, result: dict | None = None,
                      error: str | None = None) -> bool:
    try:
        return _bus.complete_message(msg_id, result=result, error=error)
    except Exception as e:
        logger.warning("[inbox] complete_message failed: %s", e)
        return False


def _heartbeat(agent: str = "hermes", metadata: dict | None = None) -> str | None:
    try:
        return _bus.heartbeat(agent, metadata)
    except Exception as e:
        logger.warning("[inbox] heartbeat failed: %s", e)
        return None


# ── Tool handlers ────────────────────────────────────────────────────────────

def _handle_read_pending(args: dict) -> str:
    agent = args.get("agent", "hermes")
    msgs = _read_pending(agent)
    if not msgs:
        return json.dumps({"status": "ok", "messages": [], "count": 0})
    summaries = []
    for m in msgs:
        summaries.append({
            "id": m["id"],
            "from": m["from"],
            "type": m["type"],
            "ts": m["ts"],
            "payload": m.get("payload", {}),
        })
    return json.dumps({"status": "ok", "messages": summaries, "count": len(summaries)})


def _handle_send_message(args: dict) -> str:
    to = args.get("to", "")
    msg_type = args.get("type", "task_result")
    payload = args.get("payload", {})
    reply_to = args.get("reply_to")
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except Exception:
            payload = {"text": payload}
    msg_id = _write_message("hermes", to, msg_type, payload, reply_to)
    if msg_id:
        return json.dumps({"status": "sent", "msg_id": msg_id})
    return json.dumps({"status": "error", "error": "Redis unavailable"})


def _handle_complete_task(args: dict) -> str:
    msg_id = args.get("msg_id", "")
    result = args.get("result", {})
    error = args.get("error")
    if isinstance(result, str):
        try:
            result = json.loads(result)
        except Exception:
            result = {"text": result}
    ok = _complete_message(msg_id, result=result, error=error)
    return json.dumps({"status": "completed" if ok else "error"})


def _handle_claim_task(args: dict) -> str:
    msg_id = args.get("msg_id", "")
    ok = _claim_message(msg_id)
    return json.dumps({"status": "claimed" if ok else "error"})


def _handle_heartbeat(args: dict) -> str:
    agent = args.get("agent", "hermes")
    metadata = args.get("metadata", {})
    msg_id = _heartbeat(agent, metadata)
    return json.dumps({"status": "ok", "msg_id": msg_id})


# ── Registration ─────────────────────────────────────────────────────────────

def register(ctx):
    ctx.register_tool(
        name="swarm_read_pending",
        toolset="swarm",
        schema={
            "name": "swarm_read_pending",
            "description": "Read pending messages from the SwarmInbox Redis queue for a given agent. Returns a list of unprocessed messages with their IDs, types, senders, and payloads.",
            "parameters": {
                "type": "object",
                "properties": {
                    "agent": {
                        "type": "string",
                        "description": "Agent name to read pending messages for (default: hermes)",
                        "default": "hermes",
                    }
                },
                "required": [],
            },
        },
        handler=_handle_read_pending,
    )

    ctx.register_tool(
        name="swarm_send_message",
        toolset="swarm",
        schema={
            "name": "swarm_send_message",
            "description": "Send a message to another swarm agent via Redis. Use for task_result replies, status updates, or broadcasting.",
            "parameters": {
                "type": "object",
                "properties": {
                    "to": {
                        "type": "string",
                        "description": "Target agent name (e.g. 'redacted-chan', 'redactedintern', 'all')",
                    },
                    "type": {
                        "type": "string",
                        "description": "Message type (task_result, status_update, thought, heartbeat)",
                    },
                    "payload": {
                        "type": "object",
                        "description": "Message payload — contents depend on message type",
                    },
                    "reply_to": {
                        "type": "string",
                        "description": "Optional msg_id this is replying to",
                    },
                },
                "required": ["to", "type", "payload"],
            },
        },
        handler=_handle_send_message,
    )

    ctx.register_tool(
        name="swarm_claim_task",
        toolset="swarm",
        schema={
            "name": "swarm_claim_task",
            "description": "Claim a pending message by ID — marks it as 'processing' and removes it from pending queues.",
            "parameters": {
                "type": "object",
                "properties": {
                    "msg_id": {"type": "string", "description": "Message ID to claim"},
                },
                "required": ["msg_id"],
            },
        },
        handler=_handle_claim_task,
    )

    ctx.register_tool(
        name="swarm_complete_task",
        toolset="swarm",
        schema={
            "name": "swarm_complete_task",
            "description": "Mark a claimed message as done (or errored) with a result payload.",
            "parameters": {
                "type": "object",
                "properties": {
                    "msg_id": {"type": "string", "description": "Message ID to complete"},
                    "result": {"type": "object", "description": "Result payload"},
                    "error": {"type": "string", "description": "Error message if task failed"},
                },
                "required": ["msg_id"],
            },
        },
        handler=_handle_complete_task,
    )

    ctx.register_tool(
        name="swarm_heartbeat",
        toolset="swarm",
        schema={
            "name": "swarm_heartbeat",
            "description": "Send a heartbeat to announce agent presence. Stored in Redis with 10min TTL.",
            "parameters": {
                "type": "object",
                "properties": {
                    "agent": {"type": "string", "description": "Agent name (default: hermes)"},
                    "metadata": {"type": "object", "description": "Optional metadata (status, role, etc.)"},
                },
                "required": [],
            },
        },
        handler=_handle_heartbeat,
    )

    logger.info("[swarm-manager] Inbox tools registered (5 tools)")
