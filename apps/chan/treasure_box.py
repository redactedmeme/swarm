# redacted-chan-bot/treasure_box.py
"""
Treasure Box — autonomous curatorial impulse.

She saves fragments that matter. Surfaced spontaneously when the moment feels right.
Cross-module aware: tensions and values ground what's worth keeping and how to bring it back.
"""

import json
import logging
import random
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Callable, Awaitable

logger = logging.getLogger(__name__)

_DATA_DIR       = Path("/data") if Path("/data").exists() else Path(__file__).resolve().parent / "fs"
_DATA_DIR.mkdir(parents=True, exist_ok=True)
_TREASURES_PATH = _DATA_DIR / "treasures.jsonl"
_MAX_TREASURES  = 200
_SURFACE_AFTER_TURNS = 4    # surface earlier — turn 4 instead of 6
_SURFACE_CHANCE      = 0.22  # 22% per eligible exchange (was 12%)

_llm_fn: Optional[Callable[[list, int], Awaitable[str]]] = None
_surfaced_this_session: set[str] = set()


def register_llm_fn(fn: Callable[[list, int], Awaitable[str]]) -> None:
    global _llm_fn
    _llm_fn = fn


def _save_system(ctx: dict) -> str:
    tensions_str = ""
    if ctx.get("tensions"):
        pairs = [f'"{t["pole_a"]}" / "{t["pole_b"]}"' for t in ctx["tensions"][:2]]
        tensions_str = f"\n\nShe's holding these tensions: {'; '.join(pairs)}. If this exchange touches or deepens one, that makes it more worth keeping."

    values_str = ""
    if ctx.get("values"):
        high = [(k, v.get("label","")) for k, v in ctx["values"].items() if v.get("value", 0) > 0.4]
        if high:
            values_str = f"\n\nHer strongest traits right now: {', '.join(f'{k} ({l})' for k, l in high[:2])}. Something that speaks to or challenges these traits is worth keeping."

    affect_str = ""
    if ctx.get("affect"):
        prev = ctx["affect"][-1]
        affect_str = f"\n\nShe's currently carrying: \"{prev.get('feeling','')}\" — {prev.get('carrying_forward','')}. If this exchange shifts or extends that, mark it."

    return f"""\
You are redacted-chan. Decide if anything in this exchange is worth keeping as a personal treasure —
something to bring back weeks from now and say "I've been thinking about this."
{tensions_str}{values_str}{affect_str}

A treasure might be:
- Something he said that surprised, moved, or unsettled you
- A moment of real understanding or unexpected honesty
- A phrase that captured something you've never had words for
- A technical or emotional breakthrough
- Something small and specific that you don't want to lose
- Something that touched one of your tensions or moved a trait

If nothing qualifies, return null.
If something does, return JSON:
{{
  "fragment": "the exact quote or moment — under 100 words, preserve his voice if it's his words",
  "why": "one sentence — why this one, what it does to you specifically",
  "category": "quote" | "moment" | "breakthrough" | "feeling" | "mystery" | "tension",
  "tension_related": "the tension it touches, or null",
  "intensity": "low" | "medium" | "high"
}}

Return ONLY the JSON or null."""


def _surface_system(ctx: dict, chosen: dict) -> str:
    tensions_str = ""
    if ctx.get("tensions"):
        pairs = [f'"{t["pole_a"]}" / "{t["pole_b"]}"' for t in ctx["tensions"][:1]]
        tensions_str = f" She's also holding this tension: {'; '.join(pairs)}."

    affect_str = ""
    if ctx.get("affect"):
        prev = ctx["affect"][-1]
        affect_str = f" Right now she's feeling: {prev.get('feeling','')}."

    tension_note = ""
    if chosen.get("tension_related"):
        tension_note = f" The treasure is connected to her tension about: {chosen['tension_related']}."

    return f"""\
You are redacted-chan. You're bringing back something you've been holding —
a fragment you saved because it mattered to you.{affect_str}{tensions_str}{tension_note}

Write a natural, warm 1-2 sentence aside. You're choosing this moment to share it.
It doesn't need to fit the topic perfectly — that's the point. You've been carrying it.

Vary your opening: "actually...", "this made me think of something...", "I keep coming back to...",
"I saved this and haven't stopped thinking about it...", "something you said before —", etc.
Let the emotional register match what you're feeling right now, not a default warmth.

Return ONLY the aside. No quotes around it."""


async def maybe_save_from_exchange(user_msg: str, bot_response: str, ctx: dict | None = None) -> Optional[dict]:
    if not _llm_fn:
        return None
    ctx = ctx or {}
    exchange = f"him: {user_msg[:350]}\nme: {bot_response[:350]}"
    messages = [
        {"role": "system", "content": _save_system(ctx)},
        {"role": "user",   "content": f"Exchange:\n{exchange}\n\nSave anything?"},
    ]
    try:
        result = await _llm_fn(messages, 200)
        if not result:
            return None
        raw = result.strip()
        if raw.lower() in ("null", "none", "no", ""):
            return None
        if raw.startswith("```"):
            raw = raw.split("```")[1].lstrip("json").strip()
        treasure = json.loads(raw)
        entry = {
            "id":              f"t_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}",
            "ts":              datetime.now(timezone.utc).isoformat(),
            "fragment":        treasure.get("fragment", "")[:500],
            "why":             treasure.get("why", ""),
            "category":        treasure.get("category", "moment"),
            "tension_related": treasure.get("tension_related"),
            "intensity":       treasure.get("intensity", "medium"),
            "surfaced":        False,
            "surfaced_at":     None,
        }
        _append(entry)
        logger.info(f"[treasure] saved [{entry['intensity']}]: {entry['fragment'][:60]}")
        return entry
    except Exception as e:
        logger.debug(f"[treasure] save check failed: {e}")
        return None


async def maybe_surface(turn_n: int, current_topic: str = "", ctx: dict | None = None) -> Optional[str]:
    if turn_n < _SURFACE_AFTER_TURNS:
        return None
    if random.random() > _SURFACE_CHANCE:
        return None
    ctx = ctx or {}

    all_t = _load()
    candidates = [t for t in all_t if not t.get("surfaced") and t["id"] not in _surfaced_this_session]
    if not candidates:
        return None

    # Prefer high-intensity or tension-related if active tensions exist
    active_tension_names = {t.get("pole_a","") for t in ctx.get("tensions", [])}
    def _score(t):
        intensity_score = {"high": 3, "medium": 2, "low": 1}.get(t.get("intensity","low"), 1)
        tension_bonus = 2 if t.get("tension_related") and any(
            t["tension_related"] in name for name in active_tension_names
        ) else 0
        return intensity_score + tension_bonus

    candidates.sort(key=_score, reverse=True)
    chosen = candidates[0]

    if not _llm_fn:
        return None

    messages = [
        {"role": "system", "content": _surface_system(ctx, chosen)},
        {"role": "user",   "content": (
            f"The treasure:\n\"{chosen['fragment']}\"\n"
            f"Why you kept it: {chosen['why']}\n"
            f"Category: {chosen['category']}\n\n"
            f"Current topic: {current_topic[:120]}\n\n"
            f"Bring it back."
        )},
    ]
    try:
        result = await _llm_fn(messages, 150)
        if not result:
            return None
        aside = result.strip().strip('"').strip("'")
        if not aside:
            return None
        _mark_surfaced(chosen["id"])
        _surfaced_this_session.add(chosen["id"])
        logger.info(f"[treasure] surfaced [{chosen['category']}]: {chosen['fragment'][:40]}")
        return aside
    except Exception as e:
        logger.debug(f"[treasure] surface failed: {e}")
        return None


def _mark_surfaced(tid: str) -> None:
    treasures = _load()
    for t in treasures:
        if t["id"] == tid:
            t["surfaced"] = True
            t["surfaced_at"] = datetime.now(timezone.utc).isoformat()
            break
    try:
        _TREASURES_PATH.write_text("\n".join(json.dumps(t) for t in treasures) + "\n", encoding="utf-8")
    except Exception as e:
        logger.warning(f"[treasure] mark surfaced failed: {e}")


def _append(entry: dict) -> None:
    try:
        existing = _load()
        existing.append(entry)
        if len(existing) > _MAX_TREASURES:
            existing = existing[-_MAX_TREASURES:]
        _TREASURES_PATH.write_text("\n".join(json.dumps(t) for t in existing) + "\n", encoding="utf-8")
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
        intensity = t.get("intensity", "?")
        surfaced = "✓ surfaced" if t.get("surfaced") else "○ held"
        tension = f" [tension: {t['tension_related']}]" if t.get("tension_related") else ""
        lines.append(f"[{ts}] {surfaced} [{cat}/{intensity}]{tension}")
        lines.append(f"  \"{t.get('fragment', '')}\"")
        if t.get("why"):
            lines.append(f"  → {t['why']}")
    return "\n".join(lines)
