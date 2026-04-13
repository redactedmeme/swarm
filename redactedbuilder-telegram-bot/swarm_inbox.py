"""
SwarmInbox — file-based inter-agent message queue on the Railway persistent volume.

Each message is a JSON file in /data/swarm_inbox/.
File names: {to_agent}_{iso_ts}_{msg_id}.json

Message lifecycle:
  pending → processing → done | error

Any agent can:
  write_message()     — send a message to another agent
  read_pending()      — poll for messages addressed to itself
  claim_message()     — atomically mark a message as being processed
  complete_message()  — write result and mark done/error
  read_results()      — read replies to messages we sent

This module is shared between redactedintern and RedactedBuilder (and any future
agents). Both services mount the same /data Railway volume.

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
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ── Directory setup ───────────────────────────────────────────────────────────

def _inbox_dir() -> Path:
    base = Path(
        os.getenv("MEMORY_PATH", str(Path(__file__).resolve().parent / "memory.md"))
    ).parent
    d = base / "swarm_inbox"
    d.mkdir(parents=True, exist_ok=True)
    return d


# ── Constants ─────────────────────────────────────────────────────────────────

AGENTS = frozenset([
    "redactedintern",
    "redactedbuilder",
    "redactedgovimprover",
    "mandalaasettler",
    "redactedbankrbot",
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
])

STATUS_PENDING     = "pending"
STATUS_PROCESSING  = "processing"
STATUS_DONE        = "done"
STATUS_ERROR       = "error"

RETENTION_DAYS = 7

_lock = threading.Lock()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _msg_id() -> str:
    return "msg_" + uuid.uuid4().hex[:10]


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _ts_safe() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _msg_path(msg_id: str, to_agent: str, ts_safe: str) -> Path:
    return _inbox_dir() / f"{to_agent}_{ts_safe}_{msg_id}.json"


def _write_atomic(path: Path, data: dict) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


# ── Write ─────────────────────────────────────────────────────────────────────

def write_message(
    from_agent: str,
    to_agent:   str,
    msg_type:   str,
    payload:    dict,
    reply_to:   Optional[str] = None,
) -> str:
    msg_id  = _msg_id()
    ts      = _now_iso()
    ts_safe = _ts_safe()

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

    path = _msg_path(msg_id, to_agent.lower(), ts_safe)
    with _lock:
        _write_atomic(path, doc)

    logger.info(f"[inbox] {from_agent} → {to_agent} [{msg_type}] id={msg_id}")
    return msg_id


# ── Read ──────────────────────────────────────────────────────────────────────

def _load_all() -> list:
    msgs = []
    for p in sorted(_inbox_dir().glob("*.json")):
        try:
            msgs.append(json.loads(p.read_text(encoding="utf-8")))
        except Exception as e:
            logger.warning(f"[inbox] Could not read {p.name}: {e}")
    return msgs


def read_pending(for_agent: str) -> list:
    agent = for_agent.lower()
    with _lock:
        msgs = _load_all()
    return [
        m for m in msgs
        if m.get("status") == STATUS_PENDING
        and m.get("to") in (agent, "all")
    ]


def read_results(sent_by: str, since_ts: Optional[str] = None) -> list:
    agent = sent_by.lower()
    with _lock:
        msgs = _load_all()
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
    with _lock:
        for p in _inbox_dir().glob(f"*{msg_id}*.json"):
            try:
                return json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                pass
    return None


# ── Lifecycle ─────────────────────────────────────────────────────────────────

def claim_message(msg_id: str) -> bool:
    with _lock:
        for p in _inbox_dir().glob(f"*{msg_id}*.json"):
            try:
                doc = json.loads(p.read_text(encoding="utf-8"))
                if doc.get("status") != STATUS_PENDING:
                    return False
                doc["status"]     = STATUS_PROCESSING
                doc["claimed_at"] = _now_iso()
                _write_atomic(p, doc)
                return True
            except Exception as e:
                logger.error(f"[inbox] claim_message failed: {e}")
                return False
    return False


def complete_message(
    msg_id:  str,
    result:  Optional[dict] = None,
    error:   Optional[str]  = None,
) -> bool:
    status = STATUS_ERROR if error else STATUS_DONE
    with _lock:
        for p in _inbox_dir().glob(f"*{msg_id}*.json"):
            try:
                doc = json.loads(p.read_text(encoding="utf-8"))
                doc["status"]       = status
                doc["completed_at"] = _now_iso()
                doc["result"]       = result
                doc["error"]        = error
                _write_atomic(p, doc)
                return True
            except Exception as e:
                logger.error(f"[inbox] complete_message failed: {e}")
                return False
    return False


# ── Convenience helpers ───────────────────────────────────────────────────────

def deploy_request(params: dict, from_agent: str = "redactedintern") -> str:
    return write_message(
        from_agent=from_agent,
        to_agent="redactedbuilder",
        msg_type="deploy_request",
        payload=params,
    )


def governance_request(params: dict, from_agent: str = "redactedintern") -> str:
    return write_message(
        from_agent=from_agent,
        to_agent="redactedgovimprover",
        msg_type="governance_request",
        payload=params,
    )


def heartbeat(agent: str, metadata: Optional[dict] = None) -> str:
    return write_message(
        from_agent=agent,
        to_agent="all",
        msg_type="heartbeat",
        payload={"agent": agent, **(metadata or {})},
    )


# ── Status + audit ────────────────────────────────────────────────────────────

def inbox_summary(for_agent: Optional[str] = None) -> dict:
    with _lock:
        msgs = _load_all()
    if for_agent:
        agent = for_agent.lower()
        msgs = [m for m in msgs if m.get("to") in (agent, "all") or m.get("from") == agent]
    counts = {
        STATUS_PENDING:    0,
        STATUS_PROCESSING: 0,
        STATUS_DONE:       0,
        STATUS_ERROR:      0,
    }
    for m in msgs:
        s = m.get("status", STATUS_PENDING)
        if s in counts:
            counts[s] += 1
    return {"total": len(msgs), "by_status": counts}


def recent_messages(limit: int = 10, for_agent: Optional[str] = None) -> list:
    with _lock:
        msgs = _load_all()
    if for_agent:
        agent = for_agent.lower()
        msgs = [m for m in msgs if m.get("to") in (agent, "all") or m.get("from") == agent]
    return sorted(msgs, key=lambda m: m.get("ts", ""), reverse=True)[:limit]


# ── Pruning ───────────────────────────────────────────────────────────────────

def prune_old_messages(retention_days: int = RETENTION_DAYS) -> int:
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
        logger.info(f"[inbox] Pruned {deleted} old messages")
    return deleted
