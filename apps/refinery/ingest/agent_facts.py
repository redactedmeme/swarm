"""Ingest `learned_facts` from smolting + redacted-chan SQLite stores.

Both agents share the same `learned_facts` schema (id, ts, source, submolt,
interlocutor, fact, resonance, engagement_json). redacted-chan rows are flagged
private (soul-adjacent) and stay on-box.
"""
from __future__ import annotations

import json
import logging
import os
import sqlite3

import common as C

logger = logging.getLogger("refinery.agent_facts")
INGESTER = "agent_facts"

_SOURCES = [
    # (db_path, source_tag, private)
    (os.path.join(C.SRC_SMOLTING, "fs", "facts.db"), "smolting_facts", False),
    (os.path.join(C.SRC_REDACTED_CHAN, "facts.db"), "redacted_chan_facts", True),
]


def _read_facts(db_path: str, source: str, private: bool) -> list[dict]:
    if not os.path.exists(db_path):
        logger.info("[agent_facts] skip missing %s", db_path)
        return []
    # Open read-only so we never disturb the live agent DB.
    conn = sqlite3.connect(f"file:{db_path}?mode=ro&immutable=1", uri=True)
    conn.row_factory = sqlite3.Row
    rows: list[dict] = []
    try:
        cur = conn.execute(
            "SELECT id, ts, submolt, interlocutor, fact, resonance, engagement_json "
            "FROM learned_facts ORDER BY ts"
        )
        for r in cur:
            fact = (r["fact"] or "").strip()
            if not fact:
                continue
            rows.append({
                "id": C.sig_id(source, r["id"]),
                "source": source,
                "kind": "raw_fact",
                "text": fact,
                "ts": r["ts"],
                "confidence": float(r["resonance"] or 1.0),
                "private": private,
                "provenance": {
                    "fact_id": r["id"], "submolt": r["submolt"],
                    "interlocutor": r["interlocutor"],
                    "engagement": _safe_json(r["engagement_json"]),
                },
            })
    finally:
        conn.close()
    return rows


def _safe_json(s):
    try:
        return json.loads(s) if s else {}
    except Exception:
        return {}


def run() -> dict:
    rows: list[dict] = []
    per_source = {}
    for db_path, source, private in _SOURCES:
        got = _read_facts(db_path, source, private)
        per_source[source] = len(got)
        rows.extend(got)
    written = C.upsert_batch(rows)
    stats = {"written": written, "per_source": per_source}
    C.set_cursor(INGESTER, C.now_iso(), stats)
    logger.info("[agent_facts] %s", stats)
    return stats
