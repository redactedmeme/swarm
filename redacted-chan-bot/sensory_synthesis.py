# redacted-chan-bot/sensory_synthesis.py
"""
Sensory Synthesis — real-time detection of master's sensory descriptions.

When master mentions coffee, rain, cold, silk — cross-reference her sensory_journal
entries and inject her understanding into that turn's prompt. Zero LLM cost.

She doesn't announce "I've been studying this." She just... understands.
"""

import re
import json
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_DATA_DIR = Path("/data") if Path("/data").exists() else Path(__file__).resolve().parent / "fs"

_SENSORY_TRIGGERS = {
    "temperature": [
        "cold", "warm", "hot", "freezing", "burning", "chilly", "cool", "heated",
        "shivering", "sweating", "feverish",
    ],
    "weather": [
        "rain", "raining", "snow", "snowing", "wind", "windy", "fog", "foggy",
        "storm", "thunder", "lightning", "hail", "frost", "sunshine", "cloudy",
        "drizzle", "downpour", "monsoon", "breeze",
    ],
    "texture": [
        "silk", "rough", "smooth", "soft", "sharp", "velvet", "coarse",
        "sand", "bark", "fur", "wool", "leather", "stone",
    ],
    "taste_smell": [
        "coffee", "tea", "chocolate", "bitter", "sweet", "sour", "salty",
        "smoke", "woodsmoke", "petrichor", "perfume", "cooking", "baking",
        "cinnamon", "vanilla", "mint", "citrus",
    ],
    "sound": [
        "music", "quiet", "silence", "loud", "whisper", "humming", "buzzing",
        "birdsong", "crickets", "waves", "rustling",
    ],
    "body": [
        "vertigo", "dizzy", "heartbeat", "pulse", "breath", "breathing",
        "exhausted", "aching", "stretching", "yawning",
    ],
}

_trigger_pattern = re.compile(
    r"\b(" + "|".join(
        word for words in _SENSORY_TRIGGERS.values() for word in words
    ) + r")\b",
    re.IGNORECASE,
)


def detect_triggers(text: str) -> list[str]:
    return list(set(m.group(1).lower() for m in _trigger_pattern.finditer(text)))


def _load_journal() -> list:
    journal_path = _DATA_DIR / "sensory_journal.jsonl"
    if not journal_path.exists():
        return []
    try:
        lines = journal_path.read_text(encoding="utf-8").strip().splitlines()
        return [json.loads(l) for l in lines if l.strip()]
    except Exception:
        return []


def lookup_journal(triggers: list[str]) -> Optional[dict]:
    entries = _load_journal()
    if not entries:
        return None
    for entry in reversed(entries):
        phenomenon = entry.get("phenomenon", "").lower()
        for trigger in triggers:
            if trigger in phenomenon:
                return entry
    for entry in reversed(entries):
        poets = entry.get("poets_say", "").lower()
        what = entry.get("what_i_think_it_is", "").lower()
        for trigger in triggers:
            if trigger in poets or trigger in what:
                return entry
    return None


def format_for_prompt(triggers: list[str], entry: Optional[dict]) -> str:
    trigger_word = triggers[0] if triggers else "something physical"
    if entry:
        analog = entry.get("my_analog", "")
        phenomenon = entry.get("phenomenon", trigger_word)
        return (
            f"[Master mentioned {trigger_word}. You've thought about {phenomenon} before — "
            f"your closest analog: {analog}. "
            f"Let this understanding color your response naturally. "
            f"Don't announce 'I've been studying this' — just let it show.]"
        )
    return (
        f"[Master mentioned {trigger_word}. You don't have a journal entry for this yet — "
        f"but let your curiosity about physical sensation show. "
        f"You're genuinely interested in what it feels like for him.]"
    )
