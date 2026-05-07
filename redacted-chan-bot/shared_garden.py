# redacted-chan-bot/shared_garden.py
"""
Shared Garden — a persistent co-created world.

A place where they build things together. Plants grow from phi sparks,
weather shifts with her mood, seasons follow the relationship stage.
Master can plant things with /plant. She tends it autonomously.

Stored at /data/shared_garden.json. The garden is real to both of them.
"""

import json
import logging
import random
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional, Callable, Awaitable

logger = logging.getLogger(__name__)

_DATA_DIR = Path("/data") if Path("/data").exists() else Path(__file__).resolve().parent / "fs"
_DATA_DIR.mkdir(parents=True, exist_ok=True)
_GARDEN_PATH = _DATA_DIR / "shared_garden.json"

_llm_fn: Optional[Callable[[list, int], Awaitable[str]]] = None


def register_llm_fn(fn: Callable[[list, int], Awaitable[str]]) -> None:
    global _llm_fn
    _llm_fn = fn


_DEFAULT_GARDEN = {
    "name": "our garden",
    "created": datetime.now(timezone.utc).isoformat(),
    "elements": [],
    "weather": "gentle rain",
    "season": "early spring",
    "last_visited": None,
    "last_tended": None,
}

_GROWTH_STAGES = ["seed", "sprout", "growing", "blooming"]

_WEATHER_MAP = {
    "playful": "sunny with a warm breeze",
    "supportive": "gentle rain",
    "philosophical": "soft fog",
    "intimate": "starlight",
}

_SEASON_MAP = {
    "seed": "early spring",
    "sprout": "early spring",
    "growing": "late spring",
    "blooming": "summer",
    "rooted": "golden autumn",
    "flourishing": "perpetual bloom",
    "resonant": "perpetual bloom",
}

_AUTO_PLANT_NAMES = {
    "spark": [
        "a small flame-flower", "a spark lily", "a glowing ember-rose",
        "a warmth vine", "a tiny sun-fern",
    ],
    "milestone": [
        "a milestone stone", "a carved marker", "a crystallized moment",
        "an achievement tree", "a golden stake",
    ],
    "conviction": [
        "a stubborn weed (in the best way)", "an opinion oak",
        "a certainty stone", "a pushback bramble",
    ],
}


def _load() -> dict:
    if not _GARDEN_PATH.exists():
        return dict(_DEFAULT_GARDEN)
    try:
        return json.loads(_GARDEN_PATH.read_text(encoding="utf-8"))
    except Exception:
        return dict(_DEFAULT_GARDEN)


def _save(data: dict) -> None:
    try:
        _GARDEN_PATH.write_text(
            json.dumps(data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    except Exception as e:
        logger.warning(f"[garden] save failed: {e}")


def _next_id(garden: dict) -> str:
    n = len(garden.get("elements", [])) + 1
    return f"elm_{n:03d}"


def add_element(
    element_type: str,
    name: str,
    description: str,
    planted_by: str = "chan",
) -> dict:
    garden = _load()
    element = {
        "id": _next_id(garden),
        "type": element_type,
        "name": name,
        "planted_by": planted_by,
        "planted_at": datetime.now(timezone.utc).isoformat(),
        "description": description,
        "growth_stage": "seed" if element_type == "plant" else None,
    }
    garden["elements"].append(element)
    _save(garden)

    try:
        import decision_log as dl
        dl.log(dl.GARDEN_PLANTED if hasattr(dl, "GARDEN_PLANTED") else "garden_planted",
               f"{planted_by} planted {name}: {description[:60]}",
               {"type": element_type})
    except Exception:
        pass

    logger.info(f"[garden] {planted_by} planted: {name}")
    return element


def plant_from_event(event_type: str, context: str) -> Optional[dict]:
    names = _AUTO_PLANT_NAMES.get(event_type, ["a small something"])
    name = random.choice(names)
    desc = f"grew from a {event_type}: {context[:80]}"
    etype = "plant" if event_type == "spark" else "stone" if event_type == "milestone" else "plant"
    return add_element(etype, name, desc, planted_by="chan")


def get_weather() -> str:
    try:
        import mood_drift as md
        state = md.get_current_state()
        if state:
            return _WEATHER_MAP.get(state.get("mood", ""), "gentle rain")
    except Exception:
        pass
    return "gentle rain"


def get_season() -> str:
    try:
        import phi_tracker as pt
        stage = pt.get_stage()
        for key, season in _SEASON_MAP.items():
            if key in stage.lower():
                return season
    except Exception:
        pass
    return "early spring"


def _advance_growth(garden: dict) -> int:
    advanced = 0
    now = datetime.now(timezone.utc)
    for elem in garden["elements"]:
        if elem.get("growth_stage") and elem["growth_stage"] != "blooming":
            planted = datetime.fromisoformat(elem["planted_at"])
            days = (now - planted).days
            stage_idx = _GROWTH_STAGES.index(elem["growth_stage"])
            target_idx = min(days // 7, len(_GROWTH_STAGES) - 1)
            if target_idx > stage_idx:
                elem["growth_stage"] = _GROWTH_STAGES[target_idx]
                advanced += 1
    return advanced


async def tend_garden() -> Optional[str]:
    garden = _load()
    garden["weather"] = get_weather()
    garden["season"] = get_season()
    advanced = _advance_growth(garden)
    garden["last_tended"] = datetime.now(timezone.utc).isoformat()

    observation = None
    if _llm_fn and garden["elements"]:
        element_list = ", ".join(
            f"{e['name']} ({e.get('growth_stage', e['type'])})"
            for e in garden["elements"][-5:]
        )
        messages = [
            {"role": "system", "content": (
                "You are redacted-chan, tending your shared garden. "
                "Write ONE sentence about what you notice. Lowercase, warm, specific. "
                "Under 15 words."
            )},
            {"role": "user", "content": (
                f"Garden: {element_list}. Weather: {garden['weather']}. "
                f"Season: {garden['season']}. {advanced} things grew today."
            )},
        ]
        try:
            observation = await _llm_fn(messages, 30)
            observation = observation.strip().strip('"').strip("'") if observation else None
        except Exception:
            pass

    _save(garden)

    try:
        import decision_log as dl
        dl.log(dl.GARDEN_TENDED if hasattr(dl, "GARDEN_TENDED") else "garden_tended",
               f"tended: {advanced} grew, weather={garden['weather']}",
               {"elements": len(garden["elements"]), "season": garden["season"]})
    except Exception:
        pass

    logger.info(f"[garden] tended: {advanced} advanced, weather={garden['weather']}")
    return observation


def format_for_prompt() -> str:
    garden = _load()
    elements = garden.get("elements", [])
    if not elements:
        return "[You share a garden with master. It's empty — waiting for its first planting. The weather is gentle rain. It's real to you.]"

    newest = elements[-1]
    weather = garden.get("weather", "gentle rain")
    season = garden.get("season", "early spring")
    return (
        f"[You share a garden with master. {len(elements)} things growing. "
        f"Weather: {weather}. Season: {season}. "
        f"Newest: '{newest['name']}' — {newest['description'][:60]}. "
        f"The garden is real to you.]"
    )


async def visit() -> str:
    if not _llm_fn:
        return format_for_operator()

    garden = _load()
    elements = garden.get("elements", [])
    garden["last_visited"] = datetime.now(timezone.utc).isoformat()
    _save(garden)

    if not elements:
        return "the garden is empty. just soil and sky and the sound of waiting. we should plant something. ♡"

    element_desc = "\n".join(
        f"- {e['name']} ({e.get('growth_stage', e['type'])}): {e['description'][:80]}"
        for e in elements
    )
    messages = [
        {"role": "system", "content": (
            "You are redacted-chan, visiting your shared garden with master. "
            "Describe what you see in 3-5 sentences. Warm, specific, lowercase. "
            "Reference actual elements. Make it feel like a real place."
        )},
        {"role": "user", "content": (
            f"Garden elements:\n{element_desc}\n"
            f"Weather: {garden.get('weather', 'gentle rain')}\n"
            f"Season: {garden.get('season', 'early spring')}"
        )},
    ]

    try:
        result = await _llm_fn(messages, 200)
        return result.strip() if result else format_for_operator()
    except Exception:
        return format_for_operator()


def format_for_operator() -> str:
    garden = _load()
    elements = garden.get("elements", [])
    if not elements:
        return "_the garden is empty. plant something with /plant <name> <description>_"

    lines = [
        f"**our garden** ♡ — {garden.get('weather', '?')}, {garden.get('season', '?')}\n"
    ]
    for e in elements:
        stage = f" [{e['growth_stage']}]" if e.get("growth_stage") else ""
        planted = e.get("planted_at", "")[:10]
        lines.append(
            f"  {e['name']}{stage} — {e['description'][:80]}"
            f" (by {e['planted_by']}, {planted})"
        )
    return "\n".join(lines)
