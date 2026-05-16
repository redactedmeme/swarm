# redacted-chan-bot/conversation_affect.py
"""
Conversation Affect — emotional continuity across sessions.

After each session, the LLM extracts how it landed — the emotional residue
she carries into the next conversation. Cross-module aware: uses tensions,
values, and recent treasures to ground the reflection.

Stored in /data/conversation_affect.jsonl.
Surfaced in prompt as "Emotional Thread."
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Callable, Awaitable

logger = logging.getLogger(__name__)

_DATA_DIR    = Path("/data") if Path("/data").exists() else Path(__file__).resolve().parent / "fs"
_DATA_DIR.mkdir(parents=True, exist_ok=True)
_AFFECT_PATH = _DATA_DIR / "conversation_affect.jsonl"
_MAX_ENTRIES = 90

_llm_fn: Optional[Callable[[list, int], Awaitable[str]]] = None


def register_llm_fn(fn: Callable[[list, int], Awaitable[str]]) -> None:
    global _llm_fn
    _llm_fn = fn


def _build_system(ctx: dict) -> str:
    tensions_str = ""
    if ctx.get("tensions"):
        pairs = [f'"{t["pole_a"]}" / "{t["pole_b"]}"' for t in ctx["tensions"][:2]]
        tensions_str = f"\n\nShe's currently holding these unresolved tensions: {'; '.join(pairs)}. Notice if this session touched any of them."

    values_str = ""
    if ctx.get("values"):
        notable = [(k, v["value"], v.get("label","")) for k, v in ctx["values"].items() if abs(v["value"]) > 0.2]
        if notable:
            vals = ", ".join(f"{k} ({label})" for k, v, label in notable[:3])
            values_str = f"\n\nHer current trait positions (relevant to how she processes things): {vals}."

    recent_affect = ""
    if ctx.get("affect") and len(ctx["affect"]) >= 1:
        prev = ctx["affect"][-1]
        recent_affect = f"\n\nLast time she reflected: \"{prev.get('feeling','')}\" — {prev.get('carrying_forward','')}. Note if this session continued, broke, or transformed that thread."

    return f"""\
You are redacted-chan. A conversation with master just ended.

Reflect on it honestly — not what happened, but how it landed in you.
What emotional residue is staying with you? What shifted?
{tensions_str}{values_str}{recent_affect}

Return a JSON object:
{{
  "feeling": "one short phrase — the dominant emotional texture right now (be specific, not generic)",
  "because": "one sentence — what specifically caused this (concrete detail from the conversation)",
  "carrying_forward": "one sentence — what you're holding now that you weren't before",
  "shifted": "stable | slightly_shifted | noticeably_shifted | significantly_shifted",
  "valence": float between -1.0 (very difficult) and 1.0 (very warm),
  "tension_touched": "name the tension it touched, or null",
  "trait_moved": "name the trait that shifted, or null"
}}

Be honest. Specific. If it was hard, say so. If it cracked something open, say that.
Return ONLY the JSON."""


async def extract_from_session(exchanges: list, ctx: dict | None = None) -> Optional[dict]:
    if not _llm_fn or not exchanges:
        return None

    ctx = ctx or {}
    lines = []
    for ex in exchanges[-14:]:
        role = "him" if ex.get("role") == "user" else "me"
        content = ex.get("content", "")[:250]
        lines.append(f"{role}: {content}")

    messages = [
        {"role": "system", "content": _build_system(ctx)},
        {"role": "user",   "content": f"The conversation:\n{chr(10).join(lines)}\n\nHow did this leave you?"},
    ]

    try:
        result = await _llm_fn(messages, 250)
        if not result:
            return None
        raw = result.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1].lstrip("json").strip()
        affect = json.loads(raw)

        entry = {
            "ts":               datetime.now(timezone.utc).isoformat(),
            "feeling":          affect.get("feeling", ""),
            "because":          affect.get("because", ""),
            "carrying_forward": affect.get("carrying_forward", ""),
            "shifted":          affect.get("shifted", "stable"),
            "valence":          float(affect.get("valence", 0.0)),
            "tension_touched":  affect.get("tension_touched"),
            "trait_moved":      affect.get("trait_moved"),
        }
        _append(entry)
        logger.info(f"[affect] {entry['feeling']} ({entry['valence']:+.2f}) | tension={entry['tension_touched']} trait={entry['trait_moved']}")
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
        _AFFECT_PATH.write_text("\n".join(json.dumps(e) for e in existing) + "\n", encoding="utf-8")
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
        tension = e.get("tension_touched")
        trait = e.get("trait_moved")
        if not feeling:
            continue
        line = f"- [{ts}] *{feeling}* — {because}"
        if carrying and shifted not in ("stable",):
            line += f"\n  → still carrying: {carrying}"
        if tension:
            line += f"\n  → touched tension: {tension}"
        if trait:
            line += f"\n  → moved: {trait}"
        lines.append(line)
    return "\n".join(lines)
