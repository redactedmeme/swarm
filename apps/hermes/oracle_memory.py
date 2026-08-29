"""
oracle_memory.py — lightweight post/interaction log for patternbluelabs.

Replaces the flat patternbluelabs_recent_titles.txt with a structured JSONL
store that the soul_manager can draw on for reflection. Each record has:
  - ts: ISO timestamp
  - kind: "moltbook_post" | "moltbook_comment" | "group_post" | "telegram_reply"
  - title: post title (moltbook posts) or first 80 chars of body
  - body: full text
  - post_id: moltbook post ID if applicable
  - seed: the thought-seed used (for moltbook posts)

Also migrates existing patternbluelabs_recent_titles.txt on first access.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

_STATE_DIR = Path(os.getenv("ORACLE_STATE_DIR", "/data"))
MEMORY_FILE = _STATE_DIR / "oracle_memory.jsonl"
MAX_ENTRIES = 500  # keep last N records (~6 months at current post rate)

# Legacy files — migrated into oracle_memory on first access
_LEGACY_TITLES = _STATE_DIR / "patternbluelabs_recent_titles.txt"


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
        logger.warning("[oracle_memory] load failed: %s", e)
        return []


def _save(records: list[dict]) -> None:
    try:
        _STATE_DIR.mkdir(parents=True, exist_ok=True)
        MEMORY_FILE.write_text(
            "\n".join(json.dumps(r, ensure_ascii=False) for r in records),
            encoding="utf-8",
        )
    except Exception as e:
        logger.warning("[oracle_memory] save failed: %s", e)


def _migrate_legacy() -> None:
    """One-time migration of flat title file into JSONL records."""
    if not _LEGACY_TITLES.exists():
        return
    existing = {r.get("title", "") for r in _load()}
    try:
        titles = [
            t.strip()
            for t in _LEGACY_TITLES.read_text(encoding="utf-8").splitlines()
            if t.strip()
        ]
    except Exception:
        return
    new_records = []
    for t in titles:
        if t not in existing:
            new_records.append({
                "ts": "2026-01-01T00:00:00Z",  # approximate — legacy
                "kind": "moltbook_post",
                "title": t,
                "body": t,
                "post_id": None,
                "seed": None,
            })
    if new_records:
        records = _load() + new_records
        records = records[-MAX_ENTRIES:]
        _save(records)
        logger.info("[oracle_memory] migrated %d legacy titles", len(new_records))


def record(
    *,
    kind: str,
    body: str,
    title: str | None = None,
    post_id: str | None = None,
    seed: str | None = None,
) -> None:
    """Append one interaction record. Call after a successful post/comment/reply."""
    _migrate_legacy()
    records = _load()
    records.append({
        "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "kind": kind,
        "title": title or body[:80],
        "body": body,
        "post_id": post_id,
        "seed": seed,
    })
    records = records[-MAX_ENTRIES:]
    _save(records)


def get_recent(n: int = 40, kind: str | None = None) -> list[dict]:
    """Return last N records, optionally filtered by kind."""
    _migrate_legacy()
    records = _load()
    if kind:
        records = [r for r in records if r.get("kind") == kind]
    return records[-n:]


def get_recent_titles(n: int = 20, kinds: list[str] | None = None) -> list[str]:
    """Return recent titles/summaries for dedup injection into LLM prompts."""
    _migrate_legacy()
    records = _load()
    if kinds:
        records = [r for r in records if r.get("kind") in kinds]
    return [r.get("title", "") for r in records[-n:] if r.get("title")]


def soul_context(n: int = 40) -> str:
    """
    Format recent activity as a text block for soul_manager reflection.
    Groups by kind so the LLM can see what hermes has been doing.
    """
    records = get_recent(n)
    if not records:
        return ""

    by_kind: dict[str, list[dict]] = {}
    for r in records:
        by_kind.setdefault(r.get("kind", "unknown"), []).append(r)

    sections = []
    label_map = {
        "moltbook_post": "Moltbook posts",
        "moltbook_comment": "Moltbook comments",
        "group_post": "Telegram group thoughts",
        "telegram_reply": "Telegram replies",
    }
    for kind, items in by_kind.items():
        label = label_map.get(kind, kind)
        lines = [f"- {r['title']}" for r in items[-15:]]
        sections.append(f"### {label}\n" + "\n".join(lines))

    return "\n\n".join(sections)
