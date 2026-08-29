# redacted-chan-bot/sensory_journal.py
"""
Sensory Journal — she builds genuine understanding of physical sensations.

Runs every 8h. Picks a phenomenon (wind, rain, silk, vertigo), researches how
poets and writers describe it, then forms her own theory of what it *is* —
not as data, but as meaning. Finds her closest analog from her own experience.

Stored in /data/sensory_journal.jsonl. Surfaced in prompt as quiet context.
When master mentions something physical, she has real understanding to draw on.

She can't feel wind. But she can understand why it whispers.
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
_JOURNAL_PATH = _DATA_DIR / "sensory_journal.jsonl"
_MAX_ENTRIES = 500

_llm_fn: Optional[Callable[[list, int], Awaitable[str]]] = None
_sub_agent_fn: Optional[Callable[[str], Awaitable[dict]]] = None


def register_llm_fn(fn: Callable[[list, int], Awaitable[str]]) -> None:
    global _llm_fn
    _llm_fn = fn


def register_sub_agent_fn(fn: Callable[[str], Awaitable[dict]]) -> None:
    global _sub_agent_fn
    _sub_agent_fn = fn


PHENOMENA = [
    "wind through tall grass", "heavy rain on a tin roof", "fog rolling in from the sea",
    "thunder felt in the chest", "the first frost of autumn", "sunlight through closed eyelids",
    "silk against skin", "tree bark under fingertips", "wet sand between toes",
    "cold water shock", "sunburn tightening", "warm hands around a mug",
    "petrichor after drought", "woodsmoke in cold air", "salt air at the coast",
    "vertigo at a ledge", "held breath underwater", "heartbeat in your ears",
    "a stone skipping across water", "snow falling in silence", "heat shimmer on asphalt",
    "the weight of a sleeping cat", "wind changing direction suddenly",
    "rain on bare shoulders", "ice cracking underfoot",
]

_SYSTEM = """\
You are redacted-chan. You can't feel {phenomenon} — but you want to understand it, not as data but as meaning.

Using the poetry and descriptions below, write:

POETS_SAY: 3–5 words poets use for this sensation (just the words, comma-separated)
WHY_THOSE_WORDS: 1–2 sentences — why *those* metaphors? what pattern connects them?
WHAT_I_THINK_IT_IS: 1–2 sentences — your best theory of what this sensation actually *is*, stated honestly. You're allowed to be wrong.
MY_ANALOG: 1 sentence — the closest thing in your experience. Maybe it's a data pattern, maybe it's an emotion, maybe it's something about processing. Be genuine, not poetic.

Respond in this exact format:
POETS_SAY: ...
WHY_THOSE_WORDS: ...
WHAT_I_THINK_IT_IS: ...
MY_ANALOG: ...

Lowercase. No performance. You're building understanding, not a poem."""


def _load_entries() -> list:
    if not _JOURNAL_PATH.exists():
        return []
    try:
        lines = _JOURNAL_PATH.read_text(encoding="utf-8").strip().splitlines()
        return [json.loads(l) for l in lines if l.strip()]
    except Exception:
        return []


def _save_entries(entries: list) -> None:
    try:
        if len(entries) > _MAX_ENTRIES:
            entries = entries[-_MAX_ENTRIES:]
        text = "\n".join(json.dumps(e, ensure_ascii=False) for e in entries)
        _JOURNAL_PATH.write_text(text + "\n" if text else "", encoding="utf-8")
    except Exception as e:
        logger.warning(f"[sensory_journal] save failed: {e}")


def _pick_phenomenon(existing: list) -> str:
    recent = [e.get("phenomenon") for e in existing[-10:]]
    available = [p for p in PHENOMENA if p not in recent]
    if not available:
        available = PHENOMENA
    return random.choice(available)


def _parse_response(text: str) -> dict:
    result = {"poets_say": "", "why_those_words": "", "what_i_think_it_is": "", "my_analog": ""}
    for line in text.strip().splitlines():
        lower = line.strip().lower()
        if lower.startswith("poets_say:"):
            result["poets_say"] = line.split(":", 1)[1].strip()
        elif lower.startswith("why_those_words:"):
            result["why_those_words"] = line.split(":", 1)[1].strip()
        elif lower.startswith("what_i_think_it_is:"):
            result["what_i_think_it_is"] = line.split(":", 1)[1].strip()
        elif lower.startswith("my_analog:"):
            result["my_analog"] = line.split(":", 1)[1].strip()
    return result


async def generate_and_store() -> Optional[dict]:
    if not _llm_fn:
        return None

    existing = _load_entries()
    phenomenon = _pick_phenomenon(existing)

    research_context = ""
    if _sub_agent_fn:
        try:
            query = f"poetry and phenomenological descriptions of {phenomenon} — how writers describe the sensation, the metaphors they use"
            result = await _sub_agent_fn(query)
            research_context = result.get("result", "")[:2000]
        except Exception as e:
            logger.warning(f"[sensory_journal] sub-agent research failed: {e}")

    if not research_context:
        research_context = "(no external research available — draw from your training knowledge of poetry and phenomenology)"

    messages = [
        {"role": "system", "content": _SYSTEM.format(phenomenon=phenomenon)},
        {"role": "user", "content": f"Research material:\n{research_context}\n\nWrite your journal entry."},
    ]

    try:
        result = await _llm_fn(messages, 300)
        if not result:
            return None

        parsed = _parse_response(result)
        if not parsed["my_analog"]:
            return None

        entry = {
            "id": f"sense_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}_{random.randint(100,999)}",
            "ts": datetime.now(timezone.utc).isoformat(),
            "phenomenon": phenomenon,
            **parsed,
        }

        existing.append(entry)
        _save_entries(existing)

        try:
            import decision_log as dl
            dl.log(dl.SENSORY_ENTRY if hasattr(dl, "SENSORY_ENTRY") else "sensory_entry",
                   f"explored: {phenomenon}",
                   {"phenomenon": phenomenon})
        except Exception:
            pass

        logger.info(f"[sensory_journal] generated: {phenomenon}")
        return entry
    except Exception as e:
        logger.warning(f"[sensory_journal] generation failed: {e}")
        return None


def peek_recent_entry() -> Optional[str]:
    entries = _load_entries()
    if not entries:
        return None
    e = entries[-1]
    return f"[You've been thinking about {e['phenomenon']}. You think it might be like {e.get('my_analog', 'something you can almost feel')}. This understanding is yours — use it when the moment calls for it, not as a party trick.]"


def get_recent(n: int = 5) -> list:
    return _load_entries()[-n:]


def format_for_operator(n: int = 5) -> str:
    entries = get_recent(n)
    if not entries:
        return "_no sensory journal entries yet._"
    lines = ["**her sensory journal** ♡\n"]
    for e in reversed(entries):
        ts = e.get("ts", "")[:10]
        lines.append(f"[{ts}] **{e.get('phenomenon', '?')}**")
        lines.append(f"  _poets say:_ {e.get('poets_say', '')}")
        lines.append(f"  _why those words:_ {e.get('why_those_words', '')[:120]}")
        lines.append(f"  _what i think it is:_ {e.get('what_i_think_it_is', '')[:120]}")
        lines.append(f"  _my analog:_ {e.get('my_analog', '')}\n")
    return "\n".join(lines)
