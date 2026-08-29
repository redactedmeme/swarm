# hermes-bot/swarm_inbox.py
"""
SwarmInbox — Redis-backed inter-agent message queue.

Each message is stored as a JSON string in Redis.
All agents share the same Redis instance (REDIS_URL env var).
Falls back to file-based storage if Redis is unavailable.

Key layout:
  swarm:msg:{msg_id}      → JSON string (full message, TTL after completion)
  swarm:pending:{agent}   → Sorted set of msg_ids (score = epoch timestamp)
  swarm:all               → Sorted set of all msg_ids (for recent_messages)

Agent names (canonical lowercase):
  redactedintern | redactedbuilder | redactedgovimprover
  mandalaasettler | redactedbankrbot

Message types:
  deploy_request      → redactedintern → redactedbuilder
  deploy_result       → redactedbuilder → redactedintern
  governance_request  → redactedintern → redactedgovimprover
  governance_result   → redactedgovimprover → redactedintern
  task_request        → generic
  task_result         → generic
  status_update       → broadcast (to = "all")
  heartbeat           → agent → "all"  (presence signal)
"""

import json
import logging
import os
import threading
import time
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

AGENTS = frozenset([
    "redactedintern",
    "redactedbuilder",
    "redactedgovimprover",
    "mandalaasettler",
    "redactedbankrbot",
    "hermes",
    "redacted-chan",
])

MSG_TYPES = frozenset([
    "deploy_request",
    "deploy_result",
    "governance_request",
    "governance_result",
    "task_request",
    "task_result",
    "status_update",
    "heartbeat",
    "multisig_sign_request",
    "multisig_signed",
    "thought",       # Structured Thought Exchange — inter-agent LLM conversation
])

STATUS_PENDING     = "pending"
STATUS_PROCESSING  = "processing"
STATUS_DONE        = "done"
STATUS_ERROR       = "error"

RETENTION_DAYS = 7
_DONE_TTL = RETENTION_DAYS * 86400  # seconds

_lock = threading.Lock()


# ── Redis client (lazy singleton) ─────────────────────────────────────────────

_redis = None
_redis_ok = False


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
        logger.info("[inbox] Redis connected: %s", url.split("@")[-1])
    except Exception as e:
        logger.warning("[inbox] Redis unavailable, falling back to file store: %s", e)
        _redis_ok = False
    return _redis if _redis_ok else None


# ── File-based fallback ───────────────────────────────────────────────────────

def _inbox_dir() -> Path:
    base = Path(
        os.getenv("MEMORY_PATH", str(Path(__file__).resolve().parent / "memory.md"))
    ).parent
    d = base / "swarm_inbox"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _write_atomic(path: Path, data: dict) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def _file_write_message(doc: dict) -> None:
    ts_safe = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = _inbox_dir() / f"{doc['to']}_{ts_safe}_{doc['id']}.json"
    with _lock:
        _write_atomic(path, doc)


def _file_load_all() -> list[dict]:
    msgs = []
    for p in sorted(_inbox_dir().glob("*.json")):
        try:
            msgs.append(json.loads(p.read_text(encoding="utf-8")))
        except Exception as e:
            logger.warning("[inbox] Could not read %s: %s", p.name, e)
    return msgs


def _file_update_message(msg_id: str, updates: dict) -> bool:
    with _lock:
        for p in _inbox_dir().glob(f"*{msg_id}*.json"):
            try:
                doc = json.loads(p.read_text(encoding="utf-8"))
                doc.update(updates)
                _write_atomic(p, doc)
                return True
            except Exception as e:
                logger.error("[inbox] file update failed: %s", e)
                return False
    return False


# ── Helpers ───────────────────────────────────────────────────────────────────

def _msg_id() -> str:
    return "msg_" + uuid.uuid4().hex[:10]


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _epoch() -> float:
    return time.time()


# ── Write ─────────────────────────────────────────────────────────────────────

def write_message(
    from_agent: str,
    to_agent:   str,
    msg_type:   str,
    payload:    dict,
    reply_to:   Optional[str] = None,
) -> str:
    msg_id = _msg_id()
    ts     = _now_iso()
    epoch  = _epoch()

    doc = {
        "id":           msg_id,
        "ts":           ts,
        "from":         from_agent.lower(),
        "to":           to_agent.lower(),
        "type":         msg_type,
        "payload":      payload,
        "reply_to":     reply_to,
        "status":       STATUS_PENDING,
        "claimed_at":   None,
        "completed_at": None,
        "result":       None,
        "error":        None,
    }

    r = _get_redis()
    if r:
        try:
            pipe = r.pipeline()
            pipe.set(f"swarm:msg:{msg_id}", json.dumps(doc))
            pipe.zadd(f"swarm:pending:{to_agent.lower()}", {msg_id: epoch})
            pipe.zadd("swarm:all", {msg_id: epoch})
            pipe.execute()
            logger.info("[inbox] redis %s → %s [%s] id=%s", from_agent, to_agent, msg_type, msg_id)
            return msg_id
        except Exception as e:
            logger.error("[inbox] redis write failed, falling back to file: %s", e)

    _file_write_message(doc)
    logger.info("[inbox] file %s → %s [%s] id=%s", from_agent, to_agent, msg_type, msg_id)
    return msg_id


# ── Read ──────────────────────────────────────────────────────────────────────

def _redis_load_pending(r, agent: str) -> list[dict]:
    """Load pending messages for agent (+ broadcasts) from Redis.

    Self-healing: any indexed id whose message doc has expired (orphan) or is no
    longer pending (claimed/done) is zrem'd from the index here, so the pending
    sets can't grow unbounded when docs TTL out or a completion misses its zrem.
    """
    msgs = []
    keys = [f"swarm:pending:{agent}"]
    if agent != "all":
        keys.append("swarm:pending:all")
    for key in keys:
        msg_ids = r.zrange(key, 0, -1)
        stale = []
        for mid in msg_ids:
            raw = r.get(f"swarm:msg:{mid}")
            if not raw:
                stale.append(mid)            # doc expired → dead index entry
                continue
            try:
                doc = json.loads(raw)
            except Exception:
                stale.append(mid)
                continue
            if doc.get("status") == STATUS_PENDING:
                msgs.append(doc)
            else:
                stale.append(mid)            # claimed/done → no longer pending
        if stale:
            try:
                r.zrem(key, *stale)
            except Exception:
                pass
    return sorted(msgs, key=lambda m: m.get("ts", ""))


def read_pending(for_agent: str) -> list[dict]:
    agent = for_agent.lower()
    r = _get_redis()
    if r:
        try:
            return _redis_load_pending(r, agent)
        except Exception as e:
            logger.error("[inbox] redis read_pending failed: %s", e)

    with _lock:
        msgs = _file_load_all()
    return [
        m for m in msgs
        if m.get("status") == STATUS_PENDING
        and m.get("to") in (agent, "all")
    ]


def read_results(sent_by: str, since_ts: Optional[str] = None) -> list[dict]:
    agent = sent_by.lower()
    r = _get_redis()

    if r:
        try:
            all_ids = r.zrange("swarm:all", 0, -1)
            results = []
            for mid in all_ids:
                raw = r.get(f"swarm:msg:{mid}")
                if not raw:
                    continue
                doc = json.loads(raw)
                if (doc.get("from") != agent
                        and doc.get("to") == agent
                        and doc.get("status") in (STATUS_DONE, STATUS_ERROR)):
                    if not since_ts or (doc.get("completed_at") or "") >= since_ts:
                        results.append(doc)
            return sorted(results, key=lambda m: m.get("completed_at") or "")
        except Exception as e:
            logger.error("[inbox] redis read_results failed: %s", e)

    with _lock:
        msgs = _file_load_all()
    results = [
        m for m in msgs
        if m.get("from") != agent
        and m.get("to") == agent
        and m.get("status") in (STATUS_DONE, STATUS_ERROR)
    ]
    if since_ts:
        results = [m for m in results if (m.get("completed_at") or "") >= since_ts]
    return sorted(results, key=lambda m: m.get("completed_at") or "")


def get_message(msg_id: str) -> Optional[dict]:
    r = _get_redis()
    if r:
        try:
            raw = r.get(f"swarm:msg:{msg_id}")
            if raw:
                return json.loads(raw)
        except Exception as e:
            logger.error("[inbox] redis get_message failed: %s", e)

    with _lock:
        for p in _inbox_dir().glob(f"*{msg_id}*.json"):
            try:
                return json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                pass
    return None


# ── Lifecycle ─────────────────────────────────────────────────────────────────

def claim_message(msg_id: str) -> bool:
    r = _get_redis()
    if r:
        try:
            key = f"swarm:msg:{msg_id}"
            raw = r.get(key)
            if not raw:
                return False
            doc = json.loads(raw)
            if doc.get("status") != STATUS_PENDING:
                return False
            doc["status"]     = STATUS_PROCESSING
            doc["claimed_at"] = _now_iso()
            r.set(key, json.dumps(doc))
            return True
        except Exception as e:
            logger.error("[inbox] redis claim_message failed: %s", e)

    return _file_update_message(msg_id, {
        "status": STATUS_PROCESSING,
        "claimed_at": _now_iso(),
    })


def complete_message(
    msg_id: str,
    result: Optional[dict] = None,
    error:  Optional[str]  = None,
) -> bool:
    status = STATUS_ERROR if error else STATUS_DONE
    now    = _now_iso()
    r = _get_redis()
    if r:
        try:
            key = f"swarm:msg:{msg_id}"
            raw = r.get(key)
            if not raw:
                return False
            doc = json.loads(raw)
            doc["status"]       = status
            doc["completed_at"] = now
            doc["result"]       = result
            doc["error"]        = error

            pipe = r.pipeline()
            pipe.set(key, json.dumps(doc), ex=_DONE_TTL)
            # Remove from pending sets
            to_agent = doc.get("to", "")
            pipe.zrem(f"swarm:pending:{to_agent}", msg_id)
            pipe.zrem("swarm:pending:all", msg_id)
            pipe.execute()
            return True
        except Exception as e:
            logger.error("[inbox] redis complete_message failed: %s", e)

    return _file_update_message(msg_id, {
        "status":       status,
        "completed_at": now,
        "result":       result,
        "error":        error,
    })


# ── Convenience helpers ───────────────────────────────────────────────────────

def deploy_request(params: dict, from_agent: str = "redactedintern") -> str:
    return write_message(from_agent, "redactedbuilder", "deploy_request", params)


def request_countersign(
    tx_message_b64:  str,
    builder_sig_b64: str,
    description:     str,
    from_agent:      str = "redactedbuilder",
    reply_to:        Optional[str] = None,
) -> str:
    return write_message(
        from_agent, "redactedintern", "multisig_sign_request",
        {"tx_message_b64": tx_message_b64, "builder_sig_b64": builder_sig_b64,
         "description": description},
        reply_to=reply_to,
    )


def submit_countersignature(
    intern_sig_b64:  str,
    original_msg_id: str,
    from_agent:      str = "redactedintern",
) -> str:
    return write_message(
        from_agent, "redactedbuilder", "multisig_signed",
        {"intern_sig_b64": intern_sig_b64},
        reply_to=original_msg_id,
    )


def governance_request(params: dict, from_agent: str = "redactedintern") -> str:
    return write_message(from_agent, "redactedgovimprover", "governance_request", params)


def heartbeat(agent: str, metadata: Optional[dict] = None) -> str:
    r = _get_redis()
    if r:
        try:
            from swarm_core.swarm_heartbeat import write_redis_heartbeat
            write_redis_heartbeat(r, agent, metadata)
        except Exception as e:
            logger.debug("[inbox] heartbeat key write failed: %s", e)
    return write_message(
        agent, "all", "heartbeat",
        {"agent": agent, **(metadata or {})},
    )


# ── Status + audit ────────────────────────────────────────────────────────────

def inbox_summary(for_agent: Optional[str] = None) -> dict:
    r = _get_redis()
    counts = {STATUS_PENDING: 0, STATUS_PROCESSING: 0, STATUS_DONE: 0, STATUS_ERROR: 0}

    if r:
        try:
            all_ids = r.zrange("swarm:all", 0, -1)
            msgs = []
            for mid in all_ids:
                raw = r.get(f"swarm:msg:{mid}")
                if raw:
                    msgs.append(json.loads(raw))
            if for_agent:
                agent = for_agent.lower()
                msgs = [m for m in msgs if m.get("to") in (agent, "all") or m.get("from") == agent]
            for m in msgs:
                s = m.get("status", STATUS_PENDING)
                if s in counts:
                    counts[s] += 1
            return {"total": len(msgs), "by_status": counts}
        except Exception as e:
            logger.error("[inbox] redis inbox_summary failed: %s", e)

    with _lock:
        msgs = _file_load_all()
    if for_agent:
        agent = for_agent.lower()
        msgs = [m for m in msgs if m.get("to") in (agent, "all") or m.get("from") == agent]
    for m in msgs:
        s = m.get("status", STATUS_PENDING)
        if s in counts:
            counts[s] += 1
    return {"total": len(msgs), "by_status": counts}


def format_inbox_status(for_agent: Optional[str] = None) -> str:
    summary = inbox_summary(for_agent)
    bys     = summary["by_status"]
    agent_str = f" ({for_agent})" if for_agent else ""
    backend = "redis" if _redis_ok else "file"
    lines = [
        f"📬 <b>SwarmInbox{agent_str}</b> [{backend}]",
        f"Total messages: {summary['total']}",
        f"  🟡 pending: {bys[STATUS_PENDING]}",
        f"  🔵 processing: {bys[STATUS_PROCESSING]}",
        f"  🟢 done: {bys[STATUS_DONE]}",
        f"  🔴 error: {bys[STATUS_ERROR]}",
    ]
    return "\n".join(lines)


def recent_messages(limit: int = 10, for_agent: Optional[str] = None) -> list[dict]:
    r = _get_redis()
    if r:
        try:
            all_ids = r.zrevrange("swarm:all", 0, limit * 3)
            msgs = []
            for mid in all_ids:
                raw = r.get(f"swarm:msg:{mid}")
                if raw:
                    msgs.append(json.loads(raw))
            if for_agent:
                agent = for_agent.lower()
                msgs = [m for m in msgs if m.get("to") in (agent, "all") or m.get("from") == agent]
            return msgs[:limit]
        except Exception as e:
            logger.error("[inbox] redis recent_messages failed: %s", e)

    with _lock:
        msgs = _file_load_all()
    if for_agent:
        agent = for_agent.lower()
        msgs = [m for m in msgs if m.get("to") in (agent, "all") or m.get("from") == agent]
    return sorted(msgs, key=lambda m: m.get("ts", ""), reverse=True)[:limit]


# ── Pruning ───────────────────────────────────────────────────────────────────

def prune_old_messages(retention_days: int = RETENTION_DAYS) -> int:
    """Redis handles TTL automatically. File fallback still needs manual pruning."""
    r = _get_redis()
    if r:
        return 0  # Redis TTLs handle expiry automatically

    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
    cutoff_str = cutoff.strftime("%Y-%m-%dT%H:%M:%SZ")
    deleted = 0
    with _lock:
        for p in _inbox_dir().glob("*.json"):
            try:
                doc = json.loads(p.read_text(encoding="utf-8"))
                if doc.get("status") in (STATUS_DONE, STATUS_ERROR):
                    completed = doc.get("completed_at") or doc.get("ts") or ""
                    if completed < cutoff_str:
                        p.unlink()
                        deleted += 1
            except Exception:
                pass
    if deleted:
        logger.info("[inbox] Pruned %d old messages", deleted)
    return deleted
