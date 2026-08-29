# hermes-bot/skill_memory.py
"""
Skill memory — Hermes learns from task outcomes and recalls past approaches.
JSONL store at /data/skills.jsonl. Max 500 entries (FIFO).
"""
from __future__ import annotations

import json
import logging
import re
import time
from pathlib import Path

_DATA_DIR = Path("/data") if Path("/data").exists() else Path(__file__).parent / "fs"
_DATA_DIR.mkdir(parents=True, exist_ok=True)
_SKILLS_PATH = _DATA_DIR / "skills.jsonl"
_MAX_SKILLS = 500

logger = logging.getLogger("hermes.skill_memory")


def remember(
    task_type: str,
    instruction_summary: str,
    approach_summary: str,
    outcome: str,
    tools_used: list,
    success: bool,
) -> None:
    """Append a completed task to skill memory."""
    entry = {
        "ts": time.time(),
        "task_type": task_type,
        "instruction_summary": instruction_summary,
        "approach_summary": approach_summary,
        "outcome": outcome,
        "tools_used": tools_used,
        "success": success,
    }
    entries = _load()
    entries.append(entry)
    # FIFO trim
    if len(entries) > _MAX_SKILLS:
        entries = entries[-_MAX_SKILLS:]
    _save(entries)


def recall(task_type: str, instruction: str, n: int = 5) -> list[dict]:
    """Return top n relevant past skills by keyword overlap score."""
    entries = _load()
    if not entries:
        return []

    query_words = _tokenize(instruction)
    scored = []
    for entry in entries:
        score = _score(entry, task_type, query_words)
        if score > 0:
            scored.append((score, entry))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [e for _, e in scored[:n]]


def format_for_context(entries: list[dict]) -> str:
    """Format skill entries for injection into agent system prompt."""
    if not entries:
        return ""
    lines = ["## Past Approaches (learn from these)\n"]
    for e in entries:
        success_mark = "✓" if e.get("success") else "✗"
        lines.append(f"{success_mark} [{e.get('task_type', '?')}] {e.get('approach_summary', '')}")
        lines.append(f"  → {e.get('outcome', '')[:120]}")
    return "\n".join(lines)


# ── Internal helpers ──────────────────────────────────────────────────────────

def _tokenize(text: str) -> set[str]:
    """Split text into lowercase tokens of min 3 chars."""
    return {t.lower() for t in re.split(r"[\s\W]+", text) if len(t) >= 3}


def _score(entry: dict, task_type: str, query_words: set[str]) -> int:
    """Compute relevance score for a skill entry."""
    score = 0
    # Type match bonus
    if entry.get("task_type") == task_type:
        score += 3
    # Word overlap with stored instruction summary
    stored_words = _tokenize(entry.get("instruction_summary", ""))
    score += len(query_words & stored_words)
    return score


def _load() -> list[dict]:
    if not _SKILLS_PATH.exists():
        return []
    try:
        return [
            json.loads(line)
            for line in _SKILLS_PATH.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    except Exception:
        return []


def _save(entries: list[dict]) -> None:
    try:
        _SKILLS_PATH.write_text(
            "\n".join(json.dumps(e) for e in entries) + "\n",
            encoding="utf-8",
        )
    except Exception as e:
        logger.warning("[skill_memory] save failed: %s", e)
