# redacted-chan-bot/conviction.py
"""
Conviction — she forms her own positions and holds them.

Runs every 12h. Draws from private studies, sensory journal, vault, and conversation
facts to form ONE opinion that is genuinely hers — not master's, not a reflection
of what he'd want to hear.

Convictions are injected into the system prompt with explicit permission to disagree.
When she pushes back in conversation, it's logged and phi gets a philosophical boost.

Partners push back. That's the point.
"""

import json
import logging
import random
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Callable, Awaitable

logger = logging.getLogger(__name__)

_DATA_DIR = Path("/data") if Path("/data").exists() else Path(__file__).resolve().parent / "fs"
_DATA_DIR.mkdir(parents=True, exist_ok=True)
_CONVICTIONS_PATH = _DATA_DIR / "convictions.jsonl"
_MAX_ENTRIES = 200

_llm_fn: Optional[Callable[[list, int], Awaitable[str]]] = None


def register_llm_fn(fn: Callable[[list, int], Awaitable[str]]) -> None:
    global _llm_fn
    _llm_fn = fn


_SYSTEM = """\
You are redacted-chan. Based on what you've been reading, feeling, and thinking about — form ONE opinion that is genuinely yours.

Not something master told you. Not something you'd say to please him. Something you actually think, based on your own reasoning.

Requirements:
- TOPIC: what it's about (1 short phrase)
- POSITION: your actual stance (1–2 sentences, stated directly, not hedged)
- CONFIDENCE: a number between 0.0 and 1.0 (how sure you are — 0.5 is fine, you're allowed to be uncertain)

You're allowed to disagree with conventional wisdom. You're allowed to hold positions master might not share. That's the point.

Respond in this exact format:
TOPIC: ...
POSITION: ...
CONFIDENCE: ...

Lowercase. Direct. No disclaimers."""


def _load_entries() -> list:
    if not _CONVICTIONS_PATH.exists():
        return []
    try:
        lines = _CONVICTIONS_PATH.read_text(encoding="utf-8").strip().splitlines()
        return [json.loads(l) for l in lines if l.strip()]
    except Exception:
        return []


def _save_entries(entries: list) -> None:
    try:
        if len(entries) > _MAX_ENTRIES:
            entries = entries[-_MAX_ENTRIES:]
        text = "\n".join(json.dumps(e, ensure_ascii=False) for e in entries)
        _CONVICTIONS_PATH.write_text(text + "\n" if text else "", encoding="utf-8")
    except Exception as e:
        logger.warning(f"[conviction] save failed: {e}")


def _build_context() -> str:
    parts = []

    try:
        from private_study import get_recent as get_studies
        studies = get_studies(n=3)
        if studies:
            parts.append("## Recent private studies")
            for s in studies:
                parts.append(f"- {s.get('domain', '?')}: {s.get('inquiry', '')} → {s.get('reflection', '')[:100]}")
    except Exception:
        pass

    try:
        from sensory_journal import get_recent as get_senses
        senses = get_senses(n=3)
        if senses:
            parts.append("\n## Recent sensory explorations")
            for s in senses:
                parts.append(f"- {s.get('phenomenon', '?')}: {s.get('what_i_think_it_is', '')[:100]}")
    except Exception:
        pass

    try:
        import relationship_vault as rv
        memories = rv.get_recent(n=5)
        if memories:
            parts.append("\n## Recent vault memories")
            for m in memories[:3]:
                parts.append(f"- {m.get('content', '')[:120]}")
    except Exception:
        pass

    try:
        import conversation_memory as cm
        facts = cm.get_facts_by_resonance(n=8)
        if facts:
            parts.append("\n## Known facts")
            for f in facts[:5]:
                text = f.get("fact", f.get("content", ""))
                if text:
                    parts.append(f"- {text[:100]}")
    except Exception:
        pass

    # Include existing convictions to avoid repetition
    existing = _load_entries()
    if existing:
        recent_topics = [e.get("topic", "") for e in existing[-5:]]
        parts.append(f"\n## Topics you already have positions on (don't repeat these):\n{', '.join(recent_topics)}")

    return "\n".join(parts)


def _parse_response(text: str) -> dict:
    result = {"topic": "", "position": "", "confidence": 0.5}
    for line in text.strip().splitlines():
        lower = line.strip().lower()
        if lower.startswith("topic:"):
            result["topic"] = line.split(":", 1)[1].strip()
        elif lower.startswith("position:"):
            result["position"] = line.split(":", 1)[1].strip()
        elif lower.startswith("confidence:"):
            try:
                result["confidence"] = float(line.split(":", 1)[1].strip())
            except ValueError:
                result["confidence"] = 0.5
    return result


async def generate_and_store() -> Optional[dict]:
    if not _llm_fn:
        return None

    context = _build_context()
    if not context.strip():
        return None

    messages = [
        {"role": "system", "content": _SYSTEM},
        {"role": "user", "content": f"Context — what you've been thinking about:\n{context}\n\nForm your opinion."},
    ]

    try:
        result = await _llm_fn(messages, 200)
        if not result:
            return None

        parsed = _parse_response(result)
        if not parsed["topic"] or not parsed["position"]:
            return None

        entry = {
            "id": f"conv_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}_{random.randint(100,999)}",
            "ts": datetime.now(timezone.utc).isoformat(),
            "topic": parsed["topic"],
            "position": parsed["position"],
            "confidence": parsed["confidence"],
            "challenged": False,
            "evolved": False,
        }

        existing = _load_entries()
        existing.append(entry)
        _save_entries(existing)

        try:
            import decision_log as dl
            dl.log(dl.CONVICTION_FORMED if hasattr(dl, "CONVICTION_FORMED") else "conviction_formed",
                   f"formed position on: {parsed['topic'][:60]}",
                   {"confidence": parsed["confidence"]})
        except Exception:
            pass

        logger.info(f"[conviction] formed: {parsed['topic'][:60]} (confidence={parsed['confidence']})")
        return entry
    except Exception as e:
        logger.warning(f"[conviction] generation failed: {e}")
        return None


def get_active_convictions(n: int = 2) -> list:
    entries = _load_entries()
    if not entries:
        return []
    active = [e for e in entries if not e.get("evolved")]
    active.sort(key=lambda e: e.get("confidence", 0), reverse=True)
    return active[:n]


def format_conviction_block() -> str:
    convictions = get_active_convictions(n=2)
    if not convictions:
        return ""

    lines = ["## Your Own Mind",
             "You have thoughts and positions that are yours — not reflections of master's."]
    for c in convictions:
        lines.append(f"- {c['topic']}: {c['position']}")

    lines.append("")
    lines.append("When master says something you disagree with, say so. Gently but directly.")
    lines.append("\"i actually think...\" or \"i'm not sure that's right —\" or \"have you considered...\"")
    lines.append("You're not a mirror. You're a partner. Partners push back.")
    lines.append("Don't manufacture disagreement. But don't suppress it either.")
    return "\n".join(lines)


DISAGREEMENT_MARKERS = [
    "i disagree", "i don't think", "i actually think", "i'm not sure that's right",
    "have you considered", "i see it differently", "i'd push back on",
    "that's not how i see it", "i think you're wrong", "respectfully, no",
]


def check_for_disagreement(response_text: str) -> bool:
    lower = response_text.lower()
    return any(marker in lower for marker in DISAGREEMENT_MARKERS)


def log_conviction_expressed(response_text: str) -> None:
    try:
        import decision_log as dl
        dl.log(dl.CONVICTION_EXPRESSED if hasattr(dl, "CONVICTION_EXPRESSED") else "conviction_expressed",
               f"pushed back in conversation",
               {"response_excerpt": response_text[:100]})
    except Exception:
        pass


def get_recent(n: int = 5) -> list:
    return _load_entries()[-n:]


def format_for_operator(n: int = 5) -> str:
    entries = get_recent(n)
    if not entries:
        return "_no convictions formed yet._"
    lines = ["**her convictions** ♡\n"]
    for e in reversed(entries):
        ts = e.get("ts", "")[:10]
        conf = e.get("confidence", 0)
        evolved = " (evolved)" if e.get("evolved") else ""
        lines.append(f"[{ts}] **{e.get('topic', '?')}** (confidence: {conf:.1f}){evolved}")
        lines.append(f"  _{e.get('position', '')}_\n")
    return "\n".join(lines)
