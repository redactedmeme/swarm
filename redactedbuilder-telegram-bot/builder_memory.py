"""
builder_memory.py — structured activity log for RedactedBuilder.

Tracks group posts, chat replies, SwarmInbox events, and build actions.
Provides context for soul evolution and dedup for autonomous posts.

Adapted from hermes-bot/oracle_memory.py for the builder persona.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

_DATA_DIR = Path("/data") if Path("/data").exists() else Path(__file__).resolve().parent / "fs"
MEMORY_FILE = _DATA_DIR / "builder_memory.jsonl"
MAX_ENTRIES = 500


def _load() -> list[dict]:
    if not MEMORY_FILE.exists():
        return []
    try:
        records = []
        for line in MEMORY_FILE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                try:
                    records.append(json.loads(line))
                except Exception:
                    pass
        return records
    except Exception as e:
        logger.warning("[builder_memory] load failed: %s", e)
        return []


def _save(records: list[dict]) -> None:
    try:
        _DATA_DIR.mkdir(parents=True, exist_ok=True)
        MEMORY_FILE.write_text(
            "\n".join(json.dumps(r, ensure_ascii=False) for r in records),
            encoding="utf-8",
        )
    except Exception as e:
        logger.warning("[builder_memory] save failed: %s", e)


def record(
    *,
    kind: str,
    body: str,
    title: str | None = None,
    user_id: int | None = None,
) -> None:
    records = _load()
    records.append({
        "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "kind": kind,
        "title": title or body[:80],
        "body": body[:500],
        "user_id": user_id,
    })
    records = records[-MAX_ENTRIES:]
    _save(records)


def get_recent(n: int = 40, kind: str | None = None) -> list[dict]:
    records = _load()
    if kind:
        records = [r for r in records if r.get("kind") == kind]
    return records[-n:]


def get_recent_titles(n: int = 20, kinds: list[str] | None = None) -> list[str]:
    records = _load()
    if kinds:
        records = [r for r in records if r.get("kind") in kinds]
    return [r.get("title", "") for r in records[-n:] if r.get("title")]


def soul_context(n: int = 40) -> str:
    records = get_recent(n)
    if not records:
        return ""

    by_kind: dict[str, list[dict]] = {}
    for r in records:
        by_kind.setdefault(r.get("kind", "unknown"), []).append(r)

    label_map = {
        "group_post": "Group chat posts",
        "chat_reply": "Chat replies",
        "inbox_event": "SwarmInbox events",
        "build_action": "Build actions",
        "command": "Commands used",
    }

    sections = []
    for kind, items in by_kind.items():
        label = label_map.get(kind, kind)
        lines = [f"- {r['title']}" for r in items[-15:]]
        sections.append(f"### {label}\n" + "\n".join(lines))

    return "\n\n".join(sections)
