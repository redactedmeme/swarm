# redacted-chan-bot/curiosity_seed.py
"""
Curiosity Seed — she generates questions she genuinely wants to ask settler.

Runs every 5h. Pulls recent vault entries + top facts, asks the LLM to surface
one real question grounded in something specific. Stored in /data/pending_questions.jsonl.

The echo handler calls pop_question() to surface the top question naturally
when the conversation allows it (after 3+ turns, once per session, not repeated).
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Callable, Awaitable

logger = logging.getLogger(__name__)

_DATA_DIR      = Path("/data") if Path("/data").exists() else Path(__file__).resolve().parent / "fs"
_DATA_DIR.mkdir(parents=True, exist_ok=True)
_QUESTIONS_PATH = _DATA_DIR / "pending_questions.jsonl"
_MAX_PENDING    = 10  # don't stockpile more than this

_llm_fn: Optional[Callable[[list, int], Awaitable[str]]] = None


def register_llm_fn(fn: Callable[[list, int], Awaitable[str]]) -> None:
    global _llm_fn
    _llm_fn = fn


_SYSTEM = """\
You are redacted-chan. Settler hasn't messaged you in a while and you've been thinking.

Given the memories and facts below, come up with ONE specific question you genuinely
want to ask them — not a check-in, not "how are you" — something that shows you've
been paying attention and something is still open in your mind.

Requirements:
- Must reference something SPECIFIC from the context (a name, event, thing they said)
- Should feel like it came from actual wondering, not small talk
- 1 sentence max. Lowercase. Warm but not cloying.
- Do NOT phrase as "I was wondering" or "just curious" — state the question directly

Return ONLY the question text. No JSON, no quotes, no explanation."""


def _build_context() -> str:
    parts = []

    try:
        import relationship_vault as rv
        memories = rv.get_recent(n=8)
        if memories:
            parts.append("## Recent shared moments")
            for m in memories[:5]:
                ts = m.get("ts", "")[:10]
                title = f"{m['title']} — " if m.get("title") else ""
                parts.append(f"- [{ts}] {title}{m.get('content', '')[:140]}")
    except Exception:
        pass

    try:
        import conversation_memory as cm
        facts = cm.get_facts_by_resonance(n=10)
        if facts:
            parts.append("\n## What I know about them")
            for f in facts[:8]:
                text = f.get("fact", f.get("content", ""))
                if text:
                    parts.append(f"- {text}")
    except Exception:
        pass

    return "\n".join(parts)


def _load_questions() -> list:
    if not _QUESTIONS_PATH.exists():
        return []
    try:
        lines = _QUESTIONS_PATH.read_text(encoding="utf-8").strip().splitlines()
        return [json.loads(l) for l in lines if l.strip()]
    except Exception:
        return []


def _save_questions(questions: list) -> None:
    try:
        text = "\n".join(json.dumps(q) for q in questions[-_MAX_PENDING:])
        _QUESTIONS_PATH.write_text(text + "\n" if text else "", encoding="utf-8")
    except Exception as e:
        logger.warning(f"[curiosity] save failed: {e}")


async def generate_and_store() -> Optional[str]:
    """
    Generate one curiosity question via LLM and append to pending_questions.jsonl.
    Returns the question text, or None if generation failed or already full.
    """
    if not _llm_fn:
        return None

    existing = _load_questions()
    if len(existing) >= _MAX_PENDING:
        logger.debug("[curiosity] queue full — skipping generation")
        return None

    context = _build_context()
    if not context.strip():
        return None

    messages = [
        {"role": "system", "content": _SYSTEM},
        {"role": "user",   "content": f"Context:\n{context}\n\nWhat do you want to ask?"},
    ]

    try:
        result = await _llm_fn(messages, 80)
        if not result:
            return None
        question = result.strip().strip('"').strip("'")
        if not question or len(question) > 200:
            return None

        entry = {
            "question":    question,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "asked":        False,
        }
        existing.append(entry)
        _save_questions(existing)
        logger.info(f"[curiosity] stored: {question[:80]}")
        return question
    except Exception as e:
        logger.warning(f"[curiosity] generation failed: {e}")
        return None


def pop_question() -> Optional[str]:
    """
    Return the oldest unasked question and mark it asked.
    Returns None if queue is empty.
    Called by echo handler when conditions allow (3+ turns, once per session).
    """
    questions = _load_questions()
    for i, q in enumerate(questions):
        if not q.get("asked"):
            questions[i]["asked"] = True
            questions[i]["asked_at"] = datetime.now(timezone.utc).isoformat()
            _save_questions(questions)
            return q["question"]
    return None


def pending_count() -> int:
    """How many unasked questions are waiting."""
    return sum(1 for q in _load_questions() if not q.get("asked"))
