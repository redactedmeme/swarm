"""Ingest redacted-chan orchestrator / cognitive JSONL logs.

These live in the redacted-chan data root (bind-mounted read-only). They are
soul-adjacent private content: flagged private=True and kept on-box only.
"""
from __future__ import annotations

import json
import logging
import os

import common as C

logger = logging.getLogger("refinery.orchestrator")
INGESTER = "orchestrator"

# filename -> signal kind hint. All private.
_LOGS = {
    "decision_log.jsonl": "decision",
    "convictions.jsonl": "conviction",
    "curiosity_discoveries.jsonl": "curiosity",
    "independent_thoughts.jsonl": "thought",
    "learning_insights.jsonl": "insight",
    "gap_diary.jsonl": "gap",
}

# candidate keys holding the human-readable body of a log line
_TEXT_KEYS = ("text", "content", "thought", "decision", "conviction", "insight",
              "discovery", "summary", "note", "entry", "message", "detail")


def _line_text(obj: dict, hint: str) -> str:
    for k in _TEXT_KEYS:
        v = obj.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    # fall back to a compact dump minus noisy fields
    slim = {k: v for k, v in obj.items() if k not in ("embedding", "vector")}
    return json.dumps(slim, ensure_ascii=False)[:2000]


def _ingest_file(path: str, hint: str) -> int:
    if not os.path.exists(path):
        return 0
    rows: list[dict] = []
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        for lineno, line in enumerate(f):
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except Exception:
                continue
            if not isinstance(obj, dict):
                obj = {"value": obj}
            text = _line_text(obj, hint)
            ts = obj.get("ts") or obj.get("timestamp") or obj.get("time")
            rows.append({
                "id": C.sig_id("orchestrator", f"{os.path.basename(path)}:{lineno}"),
                "source": "orchestrator",
                "kind": "raw_orchestrator",
                "text": f"[{hint}] {text}",
                "ts": ts if isinstance(ts, str) else None,
                "private": True,
                "provenance": {"file": os.path.basename(path), "line": lineno, "hint": hint},
            })
    return C.upsert_batch(rows)


def run() -> dict:
    per_file = {}
    total = 0
    for fname, hint in _LOGS.items():
        path = os.path.join(C.SRC_REDACTED_CHAN, fname)
        n = _ingest_file(path, hint)
        per_file[fname] = n
        total += n
    stats = {"written": total, "per_file": per_file}
    C.set_cursor(INGESTER, C.now_iso(), stats)
    logger.info("[orchestrator] %s", stats)
    return stats
