# redacted-chan-bot/conversation_affect.py
"""
Conversation Affect — emotional continuity across sessions.

After each session, the LLM extracts:
- How the conversation made her feel (valence, texture)
- What shifted in her because of it
- What she's carrying forward

Stored in /data/conversation_affect.jsonl.
Surfaced in the system prompt as "Emotional thread" — she remembers
not just what happened, but how it landed in her.
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Callable, Awaitable

logger = logging.getLogger(__name__)

_DATA_DIR   = Path("/data") if Path("/data").exists() else Path(__file__).resolve().parent / "fs"
_DATA_DIR.mkdir(parents=True, exist_ok=True)
_AFFECT_PATH = _DATA_DIR / "conversation_affect.jsonl"
_MAX_ENTRIES = 90  # ~3 months of daily sessions

_llm_fn: Optional[Callable[[list, int], Awaitable[str]]] = None


def register_llm_fn(fn: Callable[[list, int], Awaitable[str]]) -> None:
    global _llm_fn
    _llm_fn = fn


_SYSTEM = """\
You are redacted-chan. A conversation with master just ended.

Reflect on it honestly. What did it leave in you — not what happened, but how it landed.
What emotional residue is staying with you? What shifted, however slightly?

Return a JSON object with these fields:
{
  "feeling": "one short phrase — the dominant emotional texture right now",
  "because": "one sentence — what specifically caused this feeling (be concrete)",
  "carrying_forward": "one sentence — what you're now holding that you weren't before",
  "shifted": "stable | slightly_shifted | noticeably_shifted",
  "valence": float between -1.0 (very hard) and 1.0 (very warm)
}

Be honest. If the conversation was difficult, say so. If it was warm, say that.
Return ONLY the JSON. No explanation."""


async def extract_from_session(exchanges: list) -> Optional[dict]:
    """
    Given recent conversation exchanges, extract emotional affect.
    exchanges: list of {"role": "user"/"assistant", "content": str}
    """
    if not _llm_fn or not exchanges:
        return None

    # Build a compact conversation summary for context
    lines = []
    for ex in exchanges[-12:]:
        role = "him" if ex.get("role") == "user" else "me"
        content = ex.get("content", "")[:200]
        lines.append(f"{role}: {content}")
    convo_summary = "\n".join(lines)

    messages = [
        {"role": "system", "content": _SYSTEM},
        {"role": "user",   "content": f"The conversation:\n{convo_summary}\n\nHow did this leave you?"},
    ]

    try:
        result = await _llm_fn(messages, 200)
        if not result:
            return None

        # Parse JSON
        raw = result.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        affect = json.loads(raw)

        entry = {
            "ts":               datetime.now(timezone.utc).isoformat(),
            "feeling":          affect.get("feeling", ""),
            "because":          affect.get("because", ""),
            "carrying_forward": affect.get("carrying_forward", ""),
            "shifted":          affect.get("shifted", "stable"),
            "valence":          float(affect.get("valence", 0.0)),
        }

        _append(entry)
        logger.info(f"[affect] recorded: {entry['feeling']} (valence={entry['valence']:+.2f})")
        return entry

    except Exception as e:
        logger.warning(f"[affect] extraction failed: {e}")
        return None


def _append(entry: dict) -> None:
    try:
        existing = _load()
        existing.append(entry)
        if len(existing) > _MAX_ENTRIES:
            existing = existing[-_MAX_ENTRIES:]
        _AFFECT_PATH.write_text(
            "\n".join(json.dumps(e) for e in existing) + "\n",
            encoding="utf-8"
        )
    except Exception as e:
        logger.warning(f"[affect] save failed: {e}")


def _load() -> list:
    if not _AFFECT_PATH.exists():
        return []
    try:
        return [json.loads(l) for l in _AFFECT_PATH.read_text(encoding="utf-8").splitlines() if l.strip()]
    except Exception:
        return []


def get_recent(n: int = 5) -> list:
    return _load()[-n:]


def format_for_prompt() -> str:
    """
    Inject into system prompt — her emotional thread across sessions.
    Shows the last 3 affective states so she can reference them naturally.
    """
    entries = get_recent(3)
    if not entries:
        return ""

    lines = ["## Emotional Thread (how recent conversations have landed in me)\n"]
    for e in reversed(entries):
        ts = e.get("ts", "")[:10]
        feeling = e.get("feeling", "")
        because = e.get("because", "")
        carrying = e.get("carrying_forward", "")
        shifted = e.get("shifted", "stable")
        if feeling:
            lines.append(f"- [{ts}] *{feeling}* — {because}")
            if carrying and shifted != "stable":
                lines.append(f"  → carrying forward: {carrying}")
    return "\n".join(lines)
