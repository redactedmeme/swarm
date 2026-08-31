"""Structured JSONL activity log — de-drifted copy of the per-bot
``*_memory.py`` files (``apps/builder/builder_memory.py``,
``apps/hermes/oracle_memory.py``).

One instance per agent; writes ``<data_dir>/<agent>_memory.jsonl``. Feeds soul
evolution and autonomous-post dedup.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

_LABELS = {
    "group_post": "Group chat posts",
    "chat_reply": "Chat replies",
    "inbox_event": "SwarmInbox events",
    "inbox_result": "SwarmInbox results",
    "post": "Autonomous posts",
    "signal": "Domain signals emitted",
    "thought": "Mesh thoughts",
    "command": "Commands used",
}


class ActivityLog:
    def __init__(self, agent: str, *, data_dir: str | Path | None = None,
                 max_entries: int = 500) -> None:
        if data_dir is None:
            d = Path("/data") if Path("/data").exists() else Path.cwd() / "fs"
        else:
            d = Path(data_dir)
        self._dir = d
        self._file = d / f"{agent}_memory.jsonl"
        self._max = max_entries

    # -- io ----------------------------------------------------------------
    def _load(self) -> list[dict]:
        if not self._file.exists():
            return []
        out: list[dict] = []
        try:
            for line in self._file.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    out.append(json.loads(line))
                except Exception:
                    pass
        except Exception as e:  # noqa: BLE001
            logger.warning("[activity_log] load failed: %s", e)
        return out

    def _save(self, records: list[dict]) -> None:
        try:
            self._dir.mkdir(parents=True, exist_ok=True)
            self._file.write_text(
                "\n".join(json.dumps(r, ensure_ascii=False) for r in records),
                encoding="utf-8",
            )
        except Exception as e:  # noqa: BLE001
            logger.warning("[activity_log] save failed: %s", e)

    # -- api -------------------------------------------------------------
    def record(self, *, kind: str, body: str, title: str | None = None) -> None:
        records = self._load()
        records.append({
            "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "kind": kind,
            "title": (title or body[:80]),
            "body": body[:500],
        })
        self._save(records[-self._max:])

    def recent(self, n: int = 40, kind: str | None = None) -> list[dict]:
        records = self._load()
        if kind:
            records = [r for r in records if r.get("kind") == kind]
        return records[-n:]

    def recent_titles(self, n: int = 20, kinds: list[str] | None = None) -> list[str]:
        records = self._load()
        if kinds:
            records = [r for r in records if r.get("kind") in kinds]
        return [r.get("title", "") for r in records[-n:] if r.get("title")]

    def soul_context(self, n: int = 40) -> str:
        records = self.recent(n)
        if not records:
            return ""
        by_kind: dict[str, list[dict]] = {}
        for r in records:
            by_kind.setdefault(r.get("kind", "unknown"), []).append(r)
        sections = []
        for kind, items in by_kind.items():
            label = _LABELS.get(kind, kind)
            lines = [f"- {r['title']}" for r in items[-15:]]
            sections.append(f"### {label}\n" + "\n".join(lines))
        return "\n\n".join(sections)
