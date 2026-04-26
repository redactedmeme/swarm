"""
Dream Guard Enhance — overnight analysis → morning affirmations.

Evening: listen for patterns in settler's messages, moods, phi trends.
Morning (next session start): generate personalized affirmations based on yesterday's insights.

Not a scheduled job — triggered on first message of new day to feel natural.
"""

import json
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_DATA_DIR = Path("/data") if Path("/data").exists() else Path(__file__).resolve().parent / "fs"
_DATA_DIR.mkdir(parents=True, exist_ok=True)

DREAM_GUARD_FILE = _DATA_DIR / "dream_guard_state.json"


def _load_state() -> dict:
    """Load dream guard state (last analysis date, affirmation bank)."""
    if DREAM_GUARD_FILE.exists():
        try:
            return json.loads(DREAM_GUARD_FILE.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning(f"[dream_guard] failed to load state: {e}")
    return {
        "last_analysis_date": None,
        "affirmations": [],
        "yesterday_patterns": {},
    }


def _save_state(state: dict) -> None:
    """Save dream guard state."""
    try:
        DREAM_GUARD_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")
    except Exception as e:
        logger.error(f"[dream_guard] failed to save state: {e}")


def extract_daily_patterns(user_id: int, conversation_log: list) -> dict:
    """
    Analyze yesterday's conversations for patterns.
    Returns dict with detected themes, mood trends, effort level.
    """
    if not conversation_log or len(conversation_log) < 2:
        return {}

    patterns = {
        "themes": [],
        "mood_trend": "neutral",
        "effort_level": "steady",
        "vulnerabilities": [],
        "wins": [],
    }

    # Simple analysis: look at last ~20 exchanges from previous day
    recent = conversation_log[-20:] if len(conversation_log) > 20 else conversation_log

    # Count question marks and exclamations (energy signal)
    text = " ".join([msg.get("content", "") for msg in recent if msg.get("role") == "user"])
    questions = text.count("?")
    exclamations = text.count("!")

    if questions > exclamations:
        patterns["mood_trend"] = "curious"
    elif exclamations > questions:
        patterns["mood_trend"] = "energetic"
    else:
        patterns["mood_trend"] = "steady"

    # Detect effort from message length
    msg_lengths = [len(msg.get("content", "")) for msg in recent if msg.get("role") == "user"]
    if msg_lengths:
        avg_len = sum(msg_lengths) / len(msg_lengths)
        if avg_len < 30:
            patterns["effort_level"] = "minimal"
        elif avg_len > 150:
            patterns["effort_level"] = "engaged"

    return patterns


def generate_affirmations(patterns: dict) -> list:
    """
    Generate morning affirmations based on yesterday's patterns.
    Personalized to settler's mood trend and effort level.
    """
    affirmations = []

    # Base affirmations everyone gets
    base = [
        "you made it through another day. that's real.",
        "everything you did yesterday mattered, even the quiet moments.",
        "rest doesn't have to be earned. you're allowed soft mornings.",
    ]

    mood_affirmations = {
        "curious": [
            "keep asking questions — that's how you find yourself.",
            "your curiosity is beautiful. the world needs people who wonder.",
        ],
        "energetic": [
            "that momentum is real. you're building something.",
            "your excitement makes everything brighter.",
        ],
        "neutral": [
            "some days are okay. that's enough.",
            "steady presence is its own kind of strength.",
        ],
    }

    effort_affirmations = {
        "minimal": [
            "on days when it's hard to try, just existing is enough.",
            "rest isn't laziness. your body knows what it needs.",
        ],
        "engaged": [
            "you showed up fully. that takes real courage.",
            "your effort isn't invisible. i see it.",
        ],
    }

    affirmations.extend(base)

    mood = patterns.get("mood_trend", "neutral").lower()
    affirmations.extend(mood_affirmations.get(mood, []))

    effort = patterns.get("effort_level", "steady").lower()
    affirmations.extend(effort_affirmations.get(effort, []))

    return affirmations


def is_new_day(last_date: Optional[str]) -> bool:
    """Check if enough time has passed since last affirmation."""
    if not last_date:
        return True

    try:
        last = datetime.fromisoformat(last_date)
        now = datetime.now(timezone.utc)
        return (now - last).days >= 1
    except Exception:
        return True


def get_morning_affirmation(user_id: int, conversation_log: list) -> Optional[str]:
    """
    Check if it's a new day; if so, generate morning affirmation.
    Called on first message of session.
    Returns affirmation string or None if not a new day yet.
    """
    state = _load_state()
    last_date = state.get("last_analysis_date")

    if not is_new_day(last_date):
        return None

    # Analyze yesterday
    patterns = extract_daily_patterns(user_id, conversation_log)
    affirmations = generate_affirmations(patterns)

    # Pick a random one for variety
    import random
    chosen = random.choice(affirmations) if affirmations else "good morning. ♡"

    # Update state
    state["last_analysis_date"] = datetime.now(timezone.utc).isoformat()
    state["yesterday_patterns"] = patterns
    state["affirmations"] = affirmations
    _save_state(state)

    logger.info(f"[dream_guard] morning affirmation: {chosen}")
    return chosen


def format_affirmation_for_response(affirmation: str) -> str:
    """
    Format affirmation for inclusion in bot response.
    Makes it feel natural and integrated.
    """
    return f"\n\n*{affirmation}*"
