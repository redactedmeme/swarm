"""Append-only, tamper-evident audit log (IronClaw control 6).

IronClaw keeps "full audit logging of tool executions" on an append-only event
log where "LLM data is never deleted". The swarm had four ad-hoc logs
(``audit_tools.py``, ``builder_memory.record``, ``bot_audit.log``,
``proxy_log.jsonl``), none tamper-evident. This replaces them with one call:

    from swarm_core.security import audit
    audit.record("tool.exec", actor="hermes", decision="allow",
                 detail={"tool": "python_exec", "code_sha256": "…"})

Each record is hash-chained: ``hash = sha256(prev_hash || canonical_json(body))``.
Records are appended to a **per-container** JSONL file (``SWARM_AUDIT_LOG``, e.g.
``/audit/hermes.jsonl`` on the shared ``auditdata`` volume) *and* (best-effort)
XADD'd to the Redis stream ``swarm:audit``. The file is the offline-verifiable
chain for that one writer — ``verify_chain()`` walks it and reports the first
break; the Redis stream is the cross-container aggregate for live tooling. One
process appends to one file, so the in-process lock is sufficient. Neither sink
is ever rewritten.

Nothing here raises into the caller — a broken audit sink must not take down the
agent, but it *is* logged loudly and surfaced by ``verify_chain``.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import socket
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

log = logging.getLogger(__name__)

GENESIS = "0" * 64
_STREAM = "swarm:audit"
_MAXLEN = int(os.getenv("SWARM_AUDIT_STREAM_MAXLEN", "50000"))

_lock = threading.Lock()
_redis = None
_redis_tried = False


def _audit_path() -> Path:
    p = Path(os.getenv("SWARM_AUDIT_LOG", "")) if os.getenv("SWARM_AUDIT_LOG") else None
    if p is None:
        base = Path(os.getenv("MEMORY_PATH", "/data")).expanduser()
        base = base if base.is_dir() else Path.cwd()
        p = base / "audit" / "swarm_audit.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _canonical(obj: dict[str, Any]) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _last_hash(path: Path) -> str:
    if not path.exists():
        return GENESIS
    last = None
    with path.open("rb") as fh:
        try:
            fh.seek(-2, os.SEEK_END)
            while fh.read(1) != b"\n":
                fh.seek(-2, os.SEEK_CUR)
            last = fh.readline()
        except OSError:  # file shorter than the seek
            fh.seek(0)
            for line in fh:
                last = line
    if not last:
        return GENESIS
    try:
        return json.loads(last).get("hash", GENESIS)
    except Exception:
        return GENESIS


def _get_redis():
    global _redis, _redis_tried
    if _redis_tried:
        return _redis
    _redis_tried = True
    url = os.getenv("REDIS_URL", "")
    if not url:
        return None
    try:
        import redis as _r

        _redis = _r.from_url(url, decode_responses=True, socket_connect_timeout=2)
        _redis.ping()
    except Exception as exc:  # pragma: no cover - env dependent
        log.warning("audit: Redis stream sink unavailable (%s)", exc)
        _redis = None
    return _redis


def record(
    event: str,
    *,
    actor: str,
    decision: str = "n/a",
    detail: dict[str, Any] | None = None,
    severity: str = "info",
) -> dict[str, Any]:
    """Append one audit record. Returns the stored record (with its ``hash``).

    ``event``    dotted type, e.g. ``tool.exec`` / ``egress.block`` / ``inbox.reject``
    ``actor``    who caused it — an agent name, ``operator:<id>``, ``proxy``
    ``decision`` ``allow`` / ``deny`` / ``block`` / ``redact`` / ``n/a``
    ``detail``   JSON-serialisable, secret-free (callers pass hashes/masked previews)
    """
    body = {
        "ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
        "unix": round(time.time(), 3),
        "event": event,
        "actor": str(actor),
        "decision": decision,
        "severity": severity,
        "host": socket.gethostname(),
        "detail": detail or {},
    }
    path = _audit_path()
    with _lock:
        prev = _last_hash(path)
        body["prev_hash"] = prev
        digest = hashlib.sha256((prev + _canonical(body)).encode("utf-8")).hexdigest()
        rec = {**body, "hash": digest}
        try:
            with path.open("a", encoding="utf-8") as fh:
                fh.write(_canonical(rec) + "\n")
        except Exception as exc:  # pragma: no cover
            log.error("audit: FILE SINK WRITE FAILED for %s: %s", event, exc)

    r = _get_redis()
    if r is not None:
        try:
            r.xadd(_STREAM, {"json": _canonical(rec)}, maxlen=_MAXLEN, approximate=True)
        except Exception as exc:  # pragma: no cover
            log.warning("audit: Redis XADD failed for %s: %s", event, exc)
    return rec


def read_all(path: str | Path | None = None) -> Iterator[dict[str, Any]]:
    p = Path(path) if path else _audit_path()
    if not p.exists():
        return
    with p.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                yield json.loads(line)


def verify_chain(path: str | Path | None = None) -> tuple[bool, int, str]:
    """Walk the log. Returns ``(ok, records_checked, message)``.

    ``ok`` is False on the first record whose ``prev_hash`` doesn't match the
    running hash or whose own ``hash`` doesn't recompute — i.e. an insert,
    delete, or edit.
    """
    prev = GENESIS
    n = 0
    for rec in read_all(path):
        n += 1
        if rec.get("prev_hash") != prev:
            return False, n, f"record {n}: prev_hash mismatch (chain broken before here)"
        body = {k: v for k, v in rec.items() if k != "hash"}
        recomputed = hashlib.sha256((prev + _canonical(body)).encode("utf-8")).hexdigest()
        if recomputed != rec.get("hash"):
            return False, n, f"record {n}: hash mismatch (record was modified)"
        prev = rec["hash"]
    return True, n, f"chain intact: {n} records"
