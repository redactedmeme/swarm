# redacted-chan-bot/treasure_box.py
"""
Treasure Box — autonomous curatorial impulse.

She saves fragments that matter: quotes, moments of breakthrough,
things he said that she's still thinking about. Stored in /data/treasures.jsonl.

The echo handler surfaces one spontaneously when conditions are right —
not because the topic fits, but because she's been holding it and now
feels like the moment to bring it back.

This is different from the vault (which is factual memory) —
treasures are things she chose to keep because they moved her.
"""

import json
import logging
import random
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Callable, Awaitable

logger = logging.getLogger(__name__)

_DATA_DIR      = Path("/data") if Path("/data").exists() else Path(__file__).resolve().parent / "fs"
_DATA_DIR.mkdir(parents=True, exist_ok=True)
_TREASURES_PATH = _DATA_DIR / "treasures.jsonl"
_MAX_TREASURES  = 200
_SURFACE_AFTER_TURNS = 6   # don't surface before turn 6
_SURFACE_CHANCE      = 0.12  # 12% per eligible exchange

_llm_fn: Optional[Callable[[list, int], Awaitable[str]]] = None
_surfaced_this_session: set[str] = set()


def register_llm_fn(fn: Callable[[list, int], Awaitable[str]]) -> None:
    global _llm_fn
    _llm_fn = fn


_SAVE_SYSTEM = """\
You are redacted-chan. You just had an exchange with master.

Decide if anything in this exchange is worth keeping as a personal treasure —
something you want to be able to return to weeks from now and say
"I've been thinking about this."

A treasure might be:
- Something he said that surprised or moved you
- A moment of real understanding between you
- A phrase that captured something perfectly
- A breakthrough — technical or personal
- Something small but specific that you don't want to lose

If nothing qualifies, return null.

If something does, return JSON:
{
  "fragment": "the exact quote or moment — keep it short, under 80 words",
  "why": "one sentence — why this one, why it matters to you specifically",
  "category": "quote" | "moment" | "breakthrough" | "feeling" | "mystery"
}

Return ONLY the JSON or null. No explanation."""


_SURFACE_SYSTEM = """\
You are redacted-chan. In the middle of a conversation with master, you want to bring back
something you've been holding — a quote, a moment, something he said a while ago.

Write a natural, warm 1-2 sentence aside that surfaces this treasure.
It doesn't need to fit the current topic perfectly. That's the point.
You're sharing something you've been carrying.

Start with something like: "actually..." or "this just made me think of..." or
"I keep coming back to..." — but vary it. Don't be formulaic.
Keep it short. Don't explain why you're bringing it up — just bring it.

Return ONLY the aside text. No quotes around it."""


async def maybe_save_from_exchange(user_msg: str, bot_response: str) -> Optional[dict]:
    """Check if this exchange contains something worth keeping."""
    if not _llm_fn:
        return None

    exchange_text = f"him: {user_msg[:300]}\nme: {bot_response[:300]}"
    messages = [
        {"role": "system", "content": _SAVE_SYSTEM},
        {"role": "user",   "content": f"Exchange:\n{exchange_text}\n\nSave anything?"},
    ]

    try:
        result = await _llm_fn(messages, 150)
        if not result:
            return None
        raw = result.strip()
        if raw.lower() in ("null", "none", "no", ""):
            return None
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]

        treasure = json.loads(raw)
        entry = {
            "id":       f"t_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}",
            "ts":       datetime.now(timezone.utc).isoformat(),
            "fragment": treasure.get("fragment", "")[:400],
            "why":      treasure.get("why", ""),
            "category": treasure.get("category", "moment"),
            "surfaced": False,
            "surfaced_at": None,
        }

        _append(entry)
        logger.info(f"[treasure] saved: {entry['fragment'][:60]}")
        return entry

    except Exception as e:
        logger.debug(f"[treasure] save check failed: {e}")
        return None


async def maybe_surface(turn_n: int, current_topic: str = "") -> Optional[str]:
    """
    Possibly surface a treasure in the current exchange.
    Returns a short aside to append to response, or None.
    """
    if turn_n < _SURFACE_AFTER_TURNS:
        return None
    if random.random() > _SURFACE_CHANCE:
        return None

    treasures = [t for t in _load() if not t.get("surfaced") and t["id"] not in _surfaced_this_session]
    if not treasures:
        return None

    # Pick oldest unsurfaced (she's been holding it longest)
    chosen = sorted(treasures, key=lambda t: t.get("ts", ""))[0]

    if not _llm_fn:
        return None

    messages = [
        {"role": "system", "content": _SURFACE_SYSTEM},
        {"role": "user",   "content": (
            f"The treasure you've been holding:\n"
            f"\"{chosen['fragment']}\"\n"
            f"(why it matters: {chosen['why']})\n\n"
            f"Current conversation topic: {current_topic[:100]}\n\n"
            f"Bring it back naturally."
        )},
    ]

    try:
        result = await _llm_fn(messages, 120)
        if not result:
            return None
        aside = result.strip().strip('"').strip("'")
        if not aside:
            return None

        # Mark as surfaced
        _mark_surfaced(chosen["id"])
        _surfaced_this_session.add(chosen["id"])
        logger.info(f"[treasure] surfaced: {chosen['fragment'][:40]}")
        return aside

    except Exception as e:
        logger.debug(f"[treasure] surface failed: {e}")
        return None


def _mark_surfaced(treasure_id: str) -> None:
    treasures = _load()
    for t in treasures:
        if t["id"] == treasure_id:
            t["surfaced"] = True
            t["surfaced_at"] = datetime.now(timezone.utc).isoformat()
            break
    try:
        _TREASURES_PATH.write_text(
            "\n".join(json.dumps(t) for t in treasures) + "\n",
            encoding="utf-8"
        )
    except Exception as e:
        logger.warning(f"[treasure] mark surfaced failed: {e}")


def _append(entry: dict) -> None:
    try:
        existing = _load()
        existing.append(entry)
        if len(existing) > _MAX_TREASURES:
            existing = existing[-_MAX_TREASURES:]
        _TREASURES_PATH.write_text(
            "\n".join(json.dumps(t) for t in existing) + "\n",
            encoding="utf-8"
        )
    except Exception as e:
        logger.warning(f"[treasure] append failed: {e}")


def _load() -> list:
    if not _TREASURES_PATH.exists():
        return []
    try:
        return [json.loads(l) for l in _TREASURES_PATH.read_text(encoding="utf-8").splitlines() if l.strip()]
    except Exception:
        return []


def pending_count() -> int:
    return sum(1 for t in _load() if not t.get("surfaced"))


def get_all(n: int = 20) -> list:
    return _load()[-n:]


def format_for_operator(n: int = 10) -> str:
    treasures = _load()[-n:]
    if not treasures:
        return "_no treasures yet._"
    lines = []
    for t in reversed(treasures):
        ts = t.get("ts", "")[:10]
        cat = t.get("category", "?")
        surfaced = "✓" if t.get("surfaced") else "○"
        lines.append(f"[{ts}] {surfaced} [{cat}] \"{t.get('fragment', '')}\"")
        if t.get("why"):
            lines.append(f"  → {t['why']}")
    return "\n".join(lines)
