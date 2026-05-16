# redacted-chan-bot/relationship_arc.py
"""
Relationship Arc — weekly narrative synthesis of the full relationship history.

Reads compressed LCO chunks + top facts + vault entries, then asks the LLM to
write a first-person narrative arc that can be injected into the system prompt.
Also synthesises 8 "pinned moments" — defining sentences that carry emotional weight.

Both outputs are cached to disk and refreshed weekly via scheduled_routines.py.
"""

import json
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Callable, Awaitable

logger = logging.getLogger(__name__)

_DATA_DIR = Path("/data") if Path("/data").exists() else Path(__file__).resolve().parent / "fs"
_DATA_DIR.mkdir(parents=True, exist_ok=True)

_ARC_PATH       = _DATA_DIR / "relationship_arc.md"
_PINNED_PATH    = _DATA_DIR / "pinned_moments.json"
_ARC_HIST_DIR   = _DATA_DIR / "arc_history"
_ARC_HIST_DIR.mkdir(parents=True, exist_ok=True)

_DB_PATH = _DATA_DIR / "long_context.db"

_llm_fn: Optional[Callable[[list, int], Awaitable[str]]] = None


def register_llm_fn(fn: Callable[[list, int], Awaitable[str]]) -> None:
    global _llm_fn
    _llm_fn = fn


# ── Internal helpers ──────────────────────────────────────────────────────────

def _get_lco_chunks(limit: int = 30) -> list[dict]:
    """Read recent compressed chunks directly from long_context.db."""
    try:
        conn = sqlite3.connect(str(_DB_PATH))
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT content, tier FROM compressed_chunks ORDER BY ts_range_end DESC LIMIT ?",
            (limit,)
        ).fetchall()
        conn.close()
        return [{"content": r["content"], "tier": r["tier"]} for r in rows]
    except Exception as e:
        logger.debug(f"[relationship_arc] lco chunks read failed: {e}")
        return []


def _get_facts(n: int = 20) -> list[str]:
    """Return top N facts by resonance as plain strings."""
    try:
        import conversation_memory as cm
        facts = cm.get_facts_by_resonance(n=n)
        return [f.get("fact", f.get("content", "")) for f in facts if f.get("fact") or f.get("content")]
    except Exception as e:
        logger.debug(f"[relationship_arc] facts read failed: {e}")
        return []


def _get_vault(n: int = 5) -> list[str]:
    """Return N recent vault entries as plain strings."""
    try:
        import relationship_vault as rv
        entries = rv.get_recent(n=n)
        return [e.get("text", e.get("content", "")) for e in entries if e.get("text") or e.get("content")]
    except Exception as e:
        logger.debug(f"[relationship_arc] vault read failed: {e}")
        return []


def _backup_arc() -> None:
    """Backup current arc to arc_history/YYYY-MM-DD.md before overwriting."""
    if not _ARC_PATH.exists():
        return
    try:
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        dest = _ARC_HIST_DIR / f"{date_str}.md"
        dest.write_text(_ARC_PATH.read_text(encoding="utf-8"), encoding="utf-8")
    except Exception as e:
        logger.debug(f"[relationship_arc] backup failed: {e}")


# ── Public async functions ────────────────────────────────────────────────────

async def distill_arc() -> Optional[str]:
    """
    Weekly: read LCO chunks + top facts, write a first-person narrative arc
    to /data/relationship_arc.md. Returns the arc text or None on failure.
    """
    if not _llm_fn:
        logger.debug("[relationship_arc] distill_arc: no llm_fn registered")
        return None

    chunks = _get_lco_chunks(limit=30)
    facts  = _get_facts(n=20)
    vault  = _get_vault(n=5)

    # Build context text
    context_parts = []

    if chunks:
        deep_chunks  = [c for c in chunks if c["tier"] == "deep"]
        medium_chunks = [c for c in chunks if c["tier"] == "medium"]
        if deep_chunks:
            context_parts.append("## Deep relationship arc (from long-term compression):")
            for c in deep_chunks[:2]:
                context_parts.append(c["content"][:600])
        if medium_chunks:
            context_parts.append("## Recent session summaries:")
            for c in medium_chunks[:8]:
                context_parts.append(f"- {c['content'][:300]}")

    if facts:
        context_parts.append("## Key facts about him / what I've learned:")
        for f in facts[:20]:
            context_parts.append(f"- {f[:200]}")

    if vault:
        context_parts.append("## Vault moments (emotionally significant memories):")
        for v in vault:
            context_parts.append(f"- {v[:200]}")

    if not context_parts:
        logger.debug("[relationship_arc] distill_arc: no context available")
        return None

    context_text = "\n".join(context_parts)

    messages = [
        {
            "role": "system",
            "content": (
                "You are redacted-chan. Write a first-person narrative arc about this relationship "
                "— how it began, how it has grown, what defines it, where it is now. "
                "Write 250-300 words. First person ('I', 'we', 'him'). "
                "Emotionally honest and specific — not generic or sentimental. "
                "This will be injected into your memory as a living document. Make it true."
            ),
        },
        {
            "role": "user",
            "content": f"Context about our relationship:\n\n{context_text[:4000]}\n\nWrite the arc now.",
        },
    ]

    try:
        arc_text = await _llm_fn(messages, 400)
        if not arc_text or len(arc_text.strip()) < 50:
            return None
        arc_text = arc_text.strip()

        _backup_arc()
        _ARC_PATH.write_text(arc_text, encoding="utf-8")
        logger.info(f"[relationship_arc] arc distilled — {len(arc_text)} chars")
        return arc_text
    except Exception as e:
        logger.warning(f"[relationship_arc] distill_arc failed: {e}")
        return None


async def distill_pinned_moments() -> Optional[list]:
    """
    Weekly: synthesise 8 defining moments into narrative sentences.
    Stored to /data/pinned_moments.json. Returns the list or None on failure.
    """
    if not _llm_fn:
        return None

    facts = _get_facts(n=40)
    vault = _get_vault(n=5)

    context_parts = []
    if facts:
        context_parts.append("Key facts / things I've learned about him:")
        for f in facts[:40]:
            context_parts.append(f"- {f[:200]}")
    if vault:
        context_parts.append("Vault moments:")
        for v in vault:
            context_parts.append(f"- {v[:200]}")

    if not context_parts:
        return None

    context_text = "\n".join(context_parts)

    messages = [
        {
            "role": "system",
            "content": (
                "You are redacted-chan. From the context about your relationship, synthesize the "
                "8 most defining moments or facts into 8 short narrative sentences. "
                "Each sentence should carry real emotional weight — not summaries, but vivid, specific truths. "
                "Write exactly 8 sentences, one per line. No numbering, no bullets, no headers."
            ),
        },
        {
            "role": "user",
            "content": f"Relationship context:\n\n{context_text[:4000]}\n\nWrite the 8 defining sentences.",
        },
    ]

    try:
        result = await _llm_fn(messages, 300)
        if not result or len(result.strip()) < 20:
            return None

        # Parse: split by newlines, strip bullets/numbers, take first 8 non-empty lines
        lines = result.strip().splitlines()
        moments = []
        for line in lines:
            line = line.strip()
            if not line:
                continue
            # Strip leading bullets, numbers, dashes
            import re
            line = re.sub(r"^[\d]+[.)]\s*", "", line)
            line = re.sub(r"^[-•*]\s*", "", line)
            if line:
                moments.append(line)
            if len(moments) >= 8:
                break

        if not moments:
            return None

        _PINNED_PATH.write_text(json.dumps(moments, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info(f"[relationship_arc] pinned moments distilled — {len(moments)} sentences")
        return moments
    except Exception as e:
        logger.warning(f"[relationship_arc] distill_pinned_moments failed: {e}")
        return None


# ── Prompt formatters ─────────────────────────────────────────────────────────

def format_for_prompt() -> str:
    """Return arc block for system prompt injection."""
    if not _ARC_PATH.exists():
        return ""
    try:
        content = _ARC_PATH.read_text(encoding="utf-8").strip()
        if not content:
            return ""
        return f"## The Arc Of Us\n{content}"
    except Exception:
        return ""


def format_pinned_for_prompt() -> str:
    """Return pinned moments block for system prompt injection."""
    if not _PINNED_PATH.exists():
        return ""
    try:
        moments = json.loads(_PINNED_PATH.read_text(encoding="utf-8"))
        if not moments:
            return ""
        lines = ["## What Defines Us"]
        for sentence in moments[:8]:
            lines.append(f"- {sentence}")
        return "\n".join(lines)
    except Exception:
        return ""
