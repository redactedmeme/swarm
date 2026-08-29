"""Ingest swarm mesh messages from Redis `swarm:msg:*` (JSON strings).

Idempotent via deterministic signal ids. Pruning of consumed keys is OFF unless
REFINERY_PRUNE=true, and even then only prunes terminal (done/error) messages,
never pending/processing ones that a live agent may still consume.
"""
from __future__ import annotations

import json
import logging

import common as C

logger = logging.getLogger("refinery.redis_msgs")
INGESTER = "redis_msgs"

# Message types that carry little refinable signal; ingested but low confidence.
_LOW_SIGNAL = {"heartbeat", "ping", "ack"}
_TERMINAL = {"done", "error"}


def run() -> dict:
    import redis as redis_lib
    r = redis_lib.from_url(C.REDIS_URL, decode_responses=True, socket_connect_timeout=5)
    r.ping()

    rows: list[dict] = []
    prune_keys: list[str] = []
    scanned = 0
    for key in r.scan_iter(match="swarm:msg:*", count=500):
        scanned += 1
        raw = r.get(key)
        if not raw:
            continue
        try:
            m = json.loads(raw)
        except Exception:
            continue
        mtype = (m.get("type") or "unknown").lower()
        frm, to = m.get("from", "?"), m.get("to", "?")
        payload = m.get("payload")
        body = ""
        if isinstance(payload, dict):
            body = payload.get("text") or payload.get("content") or payload.get("message") or ""
            if not body:
                body = json.dumps(payload, ensure_ascii=False)[:2000]
        elif payload:
            body = str(payload)
        text = f"[{mtype}] {frm}->{to}: {body}".strip()

        rows.append({
            "id": C.sig_id("redis", m.get("id", key)),
            "source": "redis",
            "kind": "raw_msg",
            "text": text,
            "ts": m.get("ts"),
            "confidence": 0.3 if mtype in _LOW_SIGNAL else 0.8,
            "provenance": {"key": key, "type": mtype, "from": frm, "to": to,
                           "status": m.get("status")},
        })

        if C.PRUNE and (m.get("status") in _TERMINAL) and mtype in _LOW_SIGNAL:
            prune_keys.append(key)

    written = C.upsert_batch(rows)

    pruned = 0
    if C.PRUNE and prune_keys:
        for i in range(0, len(prune_keys), 500):
            pruned += r.delete(*prune_keys[i:i + 500])

    stats = {"scanned": scanned, "written": written, "pruned": pruned}
    C.set_cursor(INGESTER, str(scanned), stats)
    logger.info("[redis_msgs] %s", stats)
    return stats
