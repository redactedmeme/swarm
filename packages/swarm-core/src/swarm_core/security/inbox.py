# swarm_core/security/inbox.py
"""SwarmInbox — Redis-backed inter-agent message queue, with HMAC message
signing (IronClaw control 7).

Consolidates the four near-identical ``swarm_inbox.py`` copies
(``apps/{hermes,builder,smolting,chan}``) into one shared implementation and
closes the gap IronClaw's threat model calls out: the old bus trusted
``from_agent.lower()`` blindly and any Redis writer could inject a message that
an agent would act on (up to and including ``python_exec``).

What's added over the old copies
--------------------------------
* Every message carries ``sig`` = HMAC-SHA256 over its canonical form and a
  random ``nonce``. ``from`` / ``to`` are validated against the agent roster.
* Readers verify the signature, the sender, and that the ``(from, type, to)``
  triple is permitted (``_ROUTES``) before returning a message. Failures are
  dropped and audited (``inbox.reject``).
* Enforcement is staged via ``SWARM_INBOX_ENFORCE``:
    ``strict`` (default) — drop unverifiable messages
    ``warn``            — return them, but audit every failure (rollout mode)
    ``off``             — legacy behaviour (no verification)

Keys
----
* Per-agent secret ``SWARM_INBOX_KEY_<AGENT>`` (AGENT upper-cased, ``-`` → ``_``)
  is preferred; a reader needs the keys of every sender it accepts.
* Otherwise a single shared ``SWARM_INBOX_HMAC_KEY`` is used by all agents —
  enough to stop arbitrary Redis writers, not enough to stop one compromised
  agent forging another's identity. Prefer per-agent keys in production.

The public API (functions + constants) is unchanged from the old module, so
callers only need to swap the import.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import threading
import time
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

from .identity import AGENTS as _ROSTER
from .identity import AgentId

try:  # audit is best-effort; never let it break the bus
    from . import audit as _audit
except Exception:  # pragma: no cover
    _audit = None

logger = logging.getLogger(__name__)

# ── Constants (unchanged public surface) ─────────────────────────────────────

AGENTS = frozenset(_ROSTER)

MSG_TYPES = frozenset(
    [
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
        "thought",
    ]
)

STATUS_PENDING = "pending"
STATUS_PROCESSING = "processing"
STATUS_DONE = "done"
STATUS_ERROR = "error"

RETENTION_DAYS = 7
_DONE_TTL = RETENTION_DAYS * 86400

_lock = threading.Lock()

# ── Signing config ──────────────────────────────────────────────────────────

_SHARED_KEY = os.getenv("SWARM_INBOX_HMAC_KEY", "").encode() or None
# Default: enforce only once key material exists — a keyless container that
# hasn't been cut over yet keeps working (in `warn`, which still audits every
# would-be rejection) instead of hard-failing its inbox. Set explicitly to
# override.
_ENFORCE = os.getenv(
    "SWARM_INBOX_ENFORCE",
    "strict" if (_SHARED_KEY or any(k.startswith("SWARM_INBOX_KEY_") for k in os.environ)) else "warn",
).strip().lower()
# Fields that are part of the signed identity of a message. Lifecycle fields
# (status/claimed_at/result/…) are intentionally excluded so they can mutate.
_SIGNED_FIELDS = ("id", "ts", "nonce", "from", "to", "type", "payload", "reply_to")

# (from, type) -> allowed recipients. "*" = any roster agent or "all".
# A message failing this is dropped even with a valid signature.
_ROUTES: dict[tuple[str, str], set[str]] = {
    ("redactedintern", "deploy_request"): {"redactedbuilder"},
    ("redactedbuilder", "deploy_result"): {"redactedintern"},
    ("redactedintern", "governance_request"): {"redactedgovimprover"},
    ("redactedgovimprover", "governance_result"): {"redactedintern"},
    ("redactedbuilder", "multisig_sign_request"): {"redactedintern"},
    ("redactedintern", "multisig_signed"): {"redactedbuilder"},
}
_OPEN_TYPES = {"task_request", "task_result", "status_update", "heartbeat", "thought"}


def _agent_key(agent: str) -> Optional[bytes]:
    env = "SWARM_INBOX_KEY_" + agent.upper().replace("-", "_")
    val = os.getenv(env, "")
    if val:
        return val.encode()
    return _SHARED_KEY


def _canonical(doc: dict) -> bytes:
    body = {k: doc.get(k) for k in _SIGNED_FIELDS}
    return json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def _sign(doc: dict) -> str:
    key = _agent_key(doc["from"])
    if not key:
        return ""
    return hmac.new(key, _canonical(doc), hashlib.sha256).hexdigest()


def _route_ok(frm: str, typ: str, to: str) -> bool:
    if typ in _OPEN_TYPES:
        return to in _ROSTER or to == "all"
    allowed = _ROUTES.get((frm, typ))
    if allowed is None:
        return False
    return "*" in allowed or to in allowed


def _reject(reason: str, doc: dict) -> None:
    logger.warning("[inbox] REJECT %s from=%s to=%s type=%s id=%s",
                   reason, doc.get("from"), doc.get("to"), doc.get("type"), doc.get("id"))
    if _audit is not None:
        try:
            _audit.record(
                "inbox.reject",
                actor=str(doc.get("from", "unknown")),
                decision="deny",
                severity="warning",
                detail={"reason": reason, "id": doc.get("id"), "type": doc.get("type"),
                        "to": doc.get("to")},
            )
        except Exception:
            pass


def verify_doc(doc: dict) -> bool:
    """True iff ``doc`` is a well-formed, correctly-signed, correctly-routed
    message. Honours ``SWARM_INBOX_ENFORCE``."""
    if _ENFORCE == "off":
        return True
    frm, to, typ = doc.get("from", ""), doc.get("to", ""), doc.get("type", "")
    ok = True
    if frm not in _ROSTER:
        _reject("unknown-sender", doc); ok = False
    elif not _route_ok(frm, typ, to):
        _reject("route-not-allowed", doc); ok = False
    else:
        key = _agent_key(frm)
        sig = doc.get("sig") or ""
        if not key:
            _reject("no-key-configured", doc); ok = False
        elif not sig or not hmac.compare_digest(sig, _sign(doc)):
            _reject("bad-signature", doc); ok = False
    return ok or _ENFORCE == "warn"


# ── Redis client (lazy singleton) ───────────────────────────────────────────

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


# ── File-based fallback ─────────────────────────────────────────────────────

def _inbox_dir() -> Path:
    base = Path(os.getenv("MEMORY_PATH", str(Path(__file__).resolve().parent / "memory.md"))).parent
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


# ── Helpers ────────────────────────────────────────────────────────────────

def _msg_id() -> str:
    return "msg_" + uuid.uuid4().hex[:10]


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _epoch() -> float:
    return time.time()


# ── Write ──────────────────────────────────────────────────────────────────

def write_message(
    from_agent: str,
    to_agent: str,
    msg_type: str,
    payload: dict,
    reply_to: Optional[str] = None,
) -> str:
    # Validate identities at the boundary (raises ValueError on junk).
    frm = str(AgentId(from_agent))
    to = AgentId.recipient(to_agent)

    msg_id = _msg_id()
    doc = {
        "id": msg_id,
        "ts": _now_iso(),
        "nonce": uuid.uuid4().hex,
        "from": frm,
        "to": to,
        "type": msg_type,
        "payload": payload,
        "reply_to": reply_to,
        "status": STATUS_PENDING,
        "claimed_at": None,
        "completed_at": None,
        "result": None,
        "error": None,
    }
    doc["sig"] = _sign(doc)
    if not doc["sig"] and _ENFORCE != "off":
        logger.error(
            "[inbox] no signing key for %s — set SWARM_INBOX_KEY_%s or SWARM_INBOX_HMAC_KEY",
            frm, frm.upper().replace("-", "_"),
        )

    epoch = _epoch()
    r = _get_redis()
    if r:
        try:
            pipe = r.pipeline()
            pipe.set(f"swarm:msg:{msg_id}", json.dumps(doc))
            pipe.zadd(f"swarm:pending:{to}", {msg_id: epoch})
            pipe.zadd("swarm:all", {msg_id: epoch})
            pipe.execute()
            logger.info("[inbox] redis %s → %s [%s] id=%s", frm, to, msg_type, msg_id)
            return msg_id
        except Exception as e:
            logger.error("[inbox] redis write failed, falling back to file: %s", e)

    _file_write_message(doc)
    logger.info("[inbox] file %s → %s [%s] id=%s", frm, to, msg_type, msg_id)
    return msg_id


# ── Read ───────────────────────────────────────────────────────────────────

def _redis_load_pending(r, agent: str) -> list[dict]:
    msgs = []
    keys = [f"swarm:pending:{agent}"]
    if agent != "all":
        keys.append("swarm:pending:all")
    for key in keys:
        msg_ids = r.zrange(key, 0, -1)
        for mid in msg_ids:
            raw = r.get(f"swarm:msg:{mid}")
            if not raw:
                continue
            try:
                doc = json.loads(raw)
                if doc.get("status") == STATUS_PENDING and verify_doc(doc):
                    msgs.append(doc)
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
        and verify_doc(m)
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
                        if verify_doc(doc):
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
        and verify_doc(m)
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


# ── Lifecycle ──────────────────────────────────────────────────────────────

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
            if not verify_doc(doc):
                return False
            doc["status"] = STATUS_PROCESSING
            doc["claimed_at"] = _now_iso()
            r.set(key, json.dumps(doc))
            return True
        except Exception as e:
            logger.error("[inbox] redis claim_message failed: %s", e)

    return _file_update_message(msg_id, {"status": STATUS_PROCESSING, "claimed_at": _now_iso()})


def complete_message(msg_id: str, result: Optional[dict] = None, error: Optional[str] = None) -> bool:
    status = STATUS_ERROR if error else STATUS_DONE
    now = _now_iso()
    r = _get_redis()
    if r:
        try:
            key = f"swarm:msg:{msg_id}"
            raw = r.get(key)
            if not raw:
                return False
            doc = json.loads(raw)
            doc["status"] = status
            doc["completed_at"] = now
            doc["result"] = result
            doc["error"] = error

            pipe = r.pipeline()
            pipe.set(key, json.dumps(doc), ex=_DONE_TTL)
            to_agent = doc.get("to", "")
            pipe.zrem(f"swarm:pending:{to_agent}", msg_id)
            pipe.zrem("swarm:pending:all", msg_id)
            pipe.execute()
            _write_reply_key(r, doc, result, error)
            return True
        except Exception as e:
            logger.error("[inbox] redis complete_message failed: %s", e)

    return _file_update_message(msg_id, {
        "status": status, "completed_at": now, "result": result, "error": error,
    })


def _write_reply_key(r, doc: dict, result: Optional[dict], error: Optional[str]) -> None:
    """Mirror the completion onto ``payload.reply_key`` if the sender asked for a
    direct-poll reply (the chan→hermes delegation contract in
    ``apps/chan/hermes_dispatch.py``). Best-effort; never raises."""
    reply_key = (doc.get("payload") or {}).get("reply_key")
    if not reply_key:
        return
    try:
        if error:
            r.set(reply_key, json.dumps({"content": error, "error": True}), ex=3600)
        else:
            body = result or {}
            text = body.get("summary") or body.get("content") or json.dumps(body)
            r.set(reply_key, json.dumps({"content": text}), ex=3600)
    except Exception as e:  # pragma: no cover - defensive
        logger.debug("[inbox] reply_key write failed: %s", e)


# ── Convenience helpers ────────────────────────────────────────────────────

def deploy_request(params: dict, from_agent: str = "redactedintern") -> str:
    return write_message(from_agent, "redactedbuilder", "deploy_request", params)


def request_countersign(
    tx_message_b64: str,
    builder_sig_b64: str,
    description: str,
    from_agent: str = "redactedbuilder",
    reply_to: Optional[str] = None,
) -> str:
    return write_message(
        from_agent, "redactedintern", "multisig_sign_request",
        {"tx_message_b64": tx_message_b64, "builder_sig_b64": builder_sig_b64,
         "description": description},
        reply_to=reply_to,
    )


def submit_countersignature(intern_sig_b64: str, original_msg_id: str,
                            from_agent: str = "redactedintern") -> str:
    return write_message(
        from_agent, "redactedbuilder", "multisig_signed",
        {"intern_sig_b64": intern_sig_b64}, reply_to=original_msg_id,
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
    return write_message(agent, "all", "heartbeat", {"agent": agent, **(metadata or {})})


# ── Status + audit ─────────────────────────────────────────────────────────

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
    bys = summary["by_status"]
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


# ── Pruning ────────────────────────────────────────────────────────────────

def prune_old_messages(retention_days: int = RETENTION_DAYS) -> int:
    r = _get_redis()
    if r:
        return 0

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


def sign_doc(doc: dict) -> dict:
    """Return ``doc`` with a fresh ``sig`` (and ``nonce`` if absent). Exposed for
    tests and for migrating file-store messages."""
    doc.setdefault("nonce", uuid.uuid4().hex)
    doc["sig"] = _sign(doc)
    return doc
