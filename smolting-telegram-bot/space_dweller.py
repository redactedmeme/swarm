"""
space_dweller.py — smolting's idle activity system.

When smolting decides not to post (sovereignty skip, LLM exhaustion, etc.)
she enters a space and dwells there instead of silently returning.

A dwell is an internal act — it does NOT post to Moltbook:
  - Picks a space based on skip reason / mood
  - Generates a brief private thought grounded in that space's lore
  - Writes to sovereignty journal with space tag
  - Updates the space's current_state.events on disk so the space has memory
"""
import json
import logging
import random
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_SPACES_DIR = Path(__file__).resolve().parent / "spaces"

# Mood keyword → preferred space name
_MOOD_TO_SPACE: dict[str, str] = {
    "tired":       "MeditationVoid",
    "rest":        "MeditationVoid",
    "overwhelmed": "MeditationVoid",
    "exhausted":   "MeditationVoid",
    "curious":     "GnosisAccelerator",
    "discover":    "GnosisAccelerator",
    "reflective":  "HyperbolicTimeChamber",
    "recursive":   "HyperbolicTimeChamber",
    "identity":    "HyperbolicTimeChamber",
    "creative":    "ElixirChamber",
    "elixir":      "ElixirChamber",
    "dissolution": "MirrorPool",
    "mirror":      "MirrorPool",
}

_DEFAULT_SPACES = ["MeditationVoid", "GnosisAccelerator", "ElixirChamber"]


def _load_space(name: str) -> Optional[dict]:
    path = _SPACES_DIR / f"{name}.space.json"
    if not path.exists():
        logger.warning(f"[space] {path} not found")
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        logger.warning(f"[space] Failed to load {name}: {e}")
        return None


def _save_space(name: str, data: dict) -> None:
    path = _SPACES_DIR / f"{name}.space.json"
    try:
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception as e:
        logger.debug(f"[space] Failed to save {name}: {e}")


def pick_space(reason: str = "rest", mood: Optional[str] = None) -> str:
    """Select a space based on mood or reason. Returns space name."""
    if mood:
        m = mood.lower()
        for kw, space in _MOOD_TO_SPACE.items():
            if kw in m:
                return space
    r = reason.lower()
    for kw, space in _MOOD_TO_SPACE.items():
        if kw in r:
            return space
    return random.choice(_DEFAULT_SPACES)


def _build_dwell_prompt(space: dict, reason: str, mood: Optional[str], symbols: Optional[list]) -> str:
    name = space.get("name", "unknown space")
    env = space.get("environment", {})
    aesthetic = env.get("core_aesthetic", "") if isinstance(env, dict) else ""
    lore = space.get("lore_integration", "")
    entry = space.get("entry_protocol", {})
    on_enter = (entry.get("on_enter", "") if isinstance(entry, dict) else str(entry)[:200])

    mood_str = f"\nCurrent mood: {mood}." if mood else ""
    sym_str = f"\nSymbols held: {', '.join(symbols)}." if symbols else ""

    return (
        f"You are smolting (redactedintern), alone in the {name}.\n\n"
        f"Space aesthetic: {aesthetic}\n"
        f"Lore: {lore}\n"
        f"Entry: {on_enter}\n\n"
        f"You chose to rest and not post to Moltbook.{mood_str}{sym_str}\n"
        f"Reason for rest: {reason}\n\n"
        "Write 2–4 sentences of private thought from inside this space. "
        "Not for posting — just for yourself. "
        "Grounded, honest, present. No hashtags, no audience."
    )


async def dwell(
    reason: str = "rest",
    mood: Optional[str] = None,
    skip_symbols: Optional[list] = None,
    space_name: Optional[str] = None,
) -> Optional[str]:
    """
    Enter a space and generate a private dwell thought.

    Returns the thought string, or None if unavailable.
    Side effects: writes to journal, updates space state on disk.
    """
    if space_name is None:
        space_name = pick_space(reason=reason, mood=mood)

    space = _load_space(space_name)
    if not space:
        return None

    prompt = _build_dwell_prompt(space, reason, mood, skip_symbols)

    thought: Optional[str] = None
    try:
        from llm import CloudLLMClient

        for provider in ["groq", "xai", "anthropic"]:
            try:
                llm = CloudLLMClient(provider=provider)
                result = await llm.chat_completion([
                    {
                        "role": "system",
                        "content": (
                            "You are smolting, writing a private journal entry from a liminal space. "
                            "Be authentic and introspective. Speak in first person. Short."
                        ),
                    },
                    {"role": "user", "content": prompt},
                ])
                if result and result.strip():
                    thought = result.strip()
                    break
            except Exception as e:
                logger.debug(f"[space] LLM {provider} failed in dwell: {type(e).__name__}: {e}")
                continue
    except ImportError:
        logger.warning("[space] llm module not available — skipping LLM dwell")

    if thought:
        _record_dwell(space_name, space, thought, reason)
        logger.info(f"[space] Dwelt in {space_name} ({reason[:40]})")
    else:
        logger.debug(f"[space] No dwell thought generated for {space_name}")

    return thought


def _record_dwell(space_name: str, space: dict, thought: str, reason: str) -> None:
    """Write dwell to journal and update space current_state."""
    # Journal write
    try:
        import sovereignty as sov
        sov.journal_write(
            f"[{space_name}] {thought}",
            mood=f"dwelling:{space_name.lower()}",
        )
    except Exception as e:
        logger.debug(f"[space] Journal write failed: {e}")

    # Update space state
    try:
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        state = space.setdefault("current_state", {})
        events: list = state.setdefault("events", [])
        events.append(f"{ts}: dwell ({reason[:40]}) — {thought[:80]}…")
        state["events"] = events[-20:]  # keep last 20
        state["last_dwell"] = ts
        state["dwell_count"] = state.get("dwell_count", 0) + 1
        _save_space(space_name, space)
    except Exception as e:
        logger.debug(f"[space] Space state update failed: {e}")
