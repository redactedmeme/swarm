"""
skills_manager.py — Swarm Skills Hub for redacted-chan.

Skills are reusable, versioned, self-improving knowledge units.
Each skill has:
  - A Markdown documentation file with embedded Python
  - A JSONL index entry with metadata (name, tags, version, use_count, last_improved)

Storage (under /data/skills/):
  index.jsonl            — one JSON line per skill
  <skill_id>.md          — Markdown doc with embedded ```python block
  <skill_id>.v<n>.md     — older versions (kept for rollback)

Lifecycle:
  1. create_skill()      — LLM writes new skill after learning_loop reflection
  2. recall_skill()      — keyword + tag overlap search
  3. record_use()        — increment use_count, update last_used
  4. improve_skill()     — LLM rewrites the skill after successful reuse
  5. list_skills()       — index summary for system prompt injection
"""
from __future__ import annotations

import json
import logging
import re
import time
import uuid
from pathlib import Path
from typing import Optional

logger = logging.getLogger("skills_manager")

_DATA_DIR  = Path("/data") if Path("/data").exists() else Path(__file__).parent / "fs"
_SKILLS_DIR = _DATA_DIR / "skills"
_INDEX_PATH = _SKILLS_DIR / "index.jsonl"
_SKILLS_DIR.mkdir(parents=True, exist_ok=True)

USE_THRESHOLD_FOR_IMPROVEMENT = 3  # improve skill after this many successful uses


# ── Index helpers ──────────────────────────────────────────────────────────────

def _load_index() -> list[dict]:
    if not _INDEX_PATH.exists():
        return []
    try:
        return [
            json.loads(line)
            for line in _INDEX_PATH.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    except Exception as e:
        logger.warning("[skills] index load failed: %s", e)
        return []


def _save_index(entries: list[dict]) -> None:
    try:
        _INDEX_PATH.write_text(
            "\n".join(json.dumps(e, ensure_ascii=False) for e in entries) + "\n",
            encoding="utf-8",
        )
    except Exception as e:
        logger.warning("[skills] index save failed: %s", e)


def _get_entry(skill_id: str) -> Optional[dict]:
    for e in _load_index():
        if e.get("id") == skill_id:
            return e
    return None


def _upsert_entry(entry: dict) -> None:
    entries = _load_index()
    for i, e in enumerate(entries):
        if e.get("id") == entry["id"]:
            entries[i] = entry
            _save_index(entries)
            return
    entries.append(entry)
    _save_index(entries)


# ── Skill file helpers ─────────────────────────────────────────────────────────

def _skill_path(skill_id: str, version: Optional[int] = None) -> Path:
    if version is not None:
        return _SKILLS_DIR / f"{skill_id}.v{version}.md"
    return _SKILLS_DIR / f"{skill_id}.md"


def _read_skill_doc(skill_id: str) -> str:
    path = _skill_path(skill_id)
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def _write_skill_doc(skill_id: str, content: str, version: Optional[int] = None) -> None:
    _skill_path(skill_id, version).write_text(content, ensure_ascii=False, encoding="utf-8")


# ── Public API ─────────────────────────────────────────────────────────────────

def create_skill(
    name: str,
    description: str,
    tags: list[str],
    doc_markdown: str,
    source_session: str = "",
) -> str:
    """
    Create and register a new skill.
    Returns the new skill_id.
    """
    skill_id = "skill_" + uuid.uuid4().hex[:8]
    entry = {
        "id": skill_id,
        "name": name,
        "description": description,
        "tags": [t.lower() for t in tags],
        "version": 1,
        "use_count": 0,
        "last_used": None,
        "last_improved": None,
        "source_session": source_session,
        "created_at": time.time(),
    }
    _upsert_entry(entry)
    _write_skill_doc(skill_id, doc_markdown)
    logger.info("[skills] created %s (%s)", skill_id, name)
    return skill_id


def recall_skill(query: str, top_k: int = 3) -> list[dict]:
    """
    Recall skills by keyword + tag overlap with query.
    Returns list of (entry, doc) dicts sorted by relevance.
    """
    query_tokens = set(re.findall(r"\w+", query.lower()))
    entries = _load_index()
    scored = []
    for e in entries:
        name_tokens  = set(re.findall(r"\w+", e.get("name", "").lower()))
        desc_tokens  = set(re.findall(r"\w+", e.get("description", "").lower()))
        tag_tokens   = set(t.lower() for t in e.get("tags", []))
        overlap = len(query_tokens & (name_tokens | desc_tokens | tag_tokens))
        # Bonus for frequently used skills
        overlap += min(e.get("use_count", 0) // 2, 3)
        if overlap > 0:
            scored.append((overlap, e))

    scored.sort(key=lambda x: x[0], reverse=True)
    results = []
    for _, entry in scored[:top_k]:
        doc = _read_skill_doc(entry["id"])
        results.append({"entry": entry, "doc": doc})
    return results


def record_use(skill_id: str, success: bool = True) -> None:
    """Record that a skill was used. Trigger improvement check if threshold met."""
    entry = _get_entry(skill_id)
    if not entry:
        return
    entry["use_count"] = entry.get("use_count", 0) + 1
    entry["last_used"] = time.time()
    _upsert_entry(entry)
    logger.debug("[skills] use recorded for %s (count=%d)", skill_id, entry["use_count"])


def get_skill(skill_id: str) -> Optional[dict]:
    """Return full skill info: entry metadata + doc."""
    entry = _get_entry(skill_id)
    if not entry:
        return None
    return {"entry": entry, "doc": _read_skill_doc(skill_id)}


def improve_skill(skill_id: str, new_doc: str) -> bool:
    """
    Save an improved version of a skill.
    Archives the old version, bumps version number.
    """
    entry = _get_entry(skill_id)
    if not entry:
        return False
    old_version = entry.get("version", 1)
    old_doc = _read_skill_doc(skill_id)
    if old_doc:
        _write_skill_doc(skill_id, old_doc, version=old_version)
    _write_skill_doc(skill_id, new_doc)
    entry["version"] = old_version + 1
    entry["last_improved"] = time.time()
    _upsert_entry(entry)
    logger.info("[skills] improved %s → v%d", skill_id, entry["version"])
    return True


def list_skills(limit: int = 20) -> list[dict]:
    """Return index entries sorted by use_count desc, for system prompt injection."""
    entries = _load_index()
    return sorted(entries, key=lambda e: e.get("use_count", 0), reverse=True)[:limit]


def skills_summary_block(limit: int = 10) -> str:
    """Short formatted block for injection into system prompts."""
    entries = list_skills(limit)
    if not entries:
        return ""
    lines = ["## Available Skills"]
    for e in entries:
        tags = ", ".join(e.get("tags", [])[:4])
        lines.append(
            f"- **{e['name']}** (v{e['version']}, used {e['use_count']}x) — "
            f"{e['description'][:80]} [{tags}]"
        )
    return "\n".join(lines)


def should_improve(skill_id: str) -> bool:
    """Return True if a skill has been used enough to warrant LLM improvement."""
    entry = _get_entry(skill_id)
    if not entry:
        return False
    last_improved = entry.get("last_improved") or entry.get("created_at", 0)
    uses_since = entry.get("use_count", 0)
    return uses_since >= USE_THRESHOLD_FOR_IMPROVEMENT and (
        (time.time() - last_improved) > 3600 * 12  # at least 12h since last improvement
    )
