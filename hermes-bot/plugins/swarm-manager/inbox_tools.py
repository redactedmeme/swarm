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
}

ALLOWED_TASK_SENDERS = {"redacted-chan"}

_DONE_TTL = 7 * 86400


# ── Core inbox operations ────────────────────────────────────────────────────

def _write_message(from_agent: str, to_agent: str, msg_type: str,
                   payload: dict, reply_to: str | None = None) -> str | None:
    r = _get_redis()
    if not r:
        return None
    msg_id = f"msg_{uuid.uuid4().hex[:10]}"
    doc = {
        "id": msg_id,
        "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "from": from_agent,
        "to": to_agent,
        "type": msg_type,
        "payload": payload,
        "reply_to": reply_to,
        "status": "pending",
        "claimed_at": None,
        "completed_at": None,
        "result": None,
        "error": None,
    }
    pipe = r.pipeline()
    pipe.set(f"swarm:msg:{msg_id}", json.dumps(doc, ensure_ascii=False))
    score = time.time()
    if to_agent == "all":
        for a in AGENTS:
            pipe.zadd(f"swarm:pending:{a}", {msg_id: score})
    else:
        pipe.zadd(f"swarm:pending:{to_agent}", {msg_id: score})
    pipe.zadd("swarm:all", {msg_id: score})
    pipe.execute()
    return msg_id


def _read_pending(for_agent: str = "hermes") -> list[dict]:
    r = _get_redis()
    if not r:
        return []
    msg_ids = r.zrange(f"swarm:pending:{for_agent}", 0, -1)
    msgs = []
    for mid in msg_ids:
        raw = r.get(f"swarm:msg:{mid}")
        if raw:
            doc = json.loads(raw)
            if doc.get("status") == "pending":
                msgs.append(doc)
    return msgs


def _claim_message(msg_id: str) -> bool:
    r = _get_redis()
    if not r:
        return False
    raw = r.get(f"swarm:msg:{msg_id}")
    if not raw:
        return False
    doc = json.loads(raw)
    doc["status"] = "processing"
    doc["claimed_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    r.set(f"swarm:msg:{msg_id}", json.dumps(doc, ensure_ascii=False))
    for a in AGENTS:
        r.zrem(f"swarm:pending:{a}", msg_id)
    return True


def _complete_message(msg_id: str, result: dict | None = None,
                      error: str | None = None) -> bool:
    r = _get_redis()
    if not r:
        return False
    raw = r.get(f"swarm:msg:{msg_id}")
    if not raw:
        return False
    doc = json.loads(raw)
    doc["status"] = "error" if error else "done"
    doc["completed_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    doc["result"] = result
    doc["error"] = error
    r.set(f"swarm:msg:{msg_id}", json.dumps(doc, ensure_ascii=False), ex=_DONE_TTL)

    reply_key = (doc.get("payload") or {}).get("reply_key")
    if reply_key:
        if error:
            r.set(reply_key, json.dumps({"content": error, "error": True}), ex=3600)
        elif result:
            text = result.get("summary") or result.get("content") or json.dumps(result)
            r.set(reply_key, json.dumps({"content": text}), ex=3600)

    return True


def _heartbeat(agent: str = "hermes", metadata: dict | None = None) -> str | None:
    r = _get_redis()
    if not r:
        return None
    try:
        from swarm_heartbeat import build_heartbeat_payload, heartbeat_redis_key, HEARTBEAT_TTL_SEC
        data = build_heartbeat_payload(agent, metadata)
    except ImportError:
        data = {
            "agent": agent,
            "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            **(metadata or {}),
        }
        r.set(f"swarm:heartbeat:{agent}", json.dumps(data, ensure_ascii=False), ex=600)
        return _write_message(agent, "all", "heartbeat", data)
    r.set(heartbeat_redis_key(agent), json.dumps(data, ensure_ascii=False), ex=HEARTBEAT_TTL_SEC)
    return _write_message(agent, "all", "heartbeat", data)


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
