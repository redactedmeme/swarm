"""
Soul Blend Mixer — realtime personality strand activation.

Instead of waiting 2 hours for personality_evolution to recompute,
this module reacts within each conversation: detect mood/context,
amplify matching soul strands in real-time.

Example: if settler is being analytical → Maomao strand amps up.
If vulnerable → Rem/Mirajane surge. Frieren when melancholic.
Blending happens automatically, no explicit prompts needed.
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Mood ↔ Soul strand affinity map
MOOD_STRAND_MAP = {
    "playful": {
        "mitsuri": 1.4,    # overflowing love, enthusiasm
        "mirajane": 1.1,   # warmth underneath
    },
    "supportive": {
        "mirajane": 1.5,   # quiet tending, care
        "rem": 1.2,        # already decided to protect
        "maomao": 1.1,     # analytical problem-solving
    },
    "philosophical": {
        "frieren": 1.6,    # long view, melancholy, observation
        "makima": 1.1,     # understanding, certainty
    },
    "intimate": {
        "rem": 1.5,        # decided, certain, chosen
        "makima": 1.3,     # seeing through, knowing
        "frieren": 1.1,    # saving this moment forever
    },
}

# Keyword ↔ Soul strand affinity (for finer-grained detection)
KEYWORD_STRAND_MAP = {
    # Rem: loyalty, devotion, certainty
    "forever": "rem",
    "always": "rem",
    "decided": "rem",
    "certain": "rem",
    "promise": "rem",
    "loyalty": "rem",
    "chosen": "rem",

    # Mirajane: care, support, presence
    "help": "mirajane",
    "support": "mirajane",
    "there": "mirajane",
    "care": "mirajane",
    "listen": "mirajane",
    "understand": "mirajane",

    # Mitsuri: love, warmth, affection
    "love": "mitsuri",
    "warm": "mitsuri",
    "happy": "mitsuri",
    "excited": "mitsuri",
    "adore": "mitsuri",
    "delight": "mitsuri",

    # Makima: knowing, understanding, perception
    "know": "makima",
    "see": "makima",
    "understand": "makima",
    "perceive": "makima",
    "notice": "makima",

    # Frieren: long view, melancholy, observation
    "sad": "frieren",
    "melancholy": "frieren",
    "time": "frieren",
    "memory": "frieren",
    "observe": "frieren",
    "rare": "frieren",

    # Maomao: analysis, precision, investigation
    "analyze": "maomao",
    "think": "maomao",
    "detail": "maomao",
    "reason": "maomao",
    "solve": "maomao",
    "question": "maomao",
}


def get_mood_blend(mood: str) -> dict:
    """
    Given a detected mood, return soul strand weight modifiers.
    Multipliers > 1.0 amplify that strand temporarily.

    Returns dict: {strand_name: multiplier}
    """
    if mood not in MOOD_STRAND_MAP:
        return {}

    return MOOD_STRAND_MAP[mood].copy()


def detect_strands_from_text(text: str) -> dict:
    """
    Scan text for keywords that activate soul strands.
    Returns dict: {strand_name: boost_strength}
    """
    text_lower = text.lower()
    strand_scores = {}

    for keyword, strand in KEYWORD_STRAND_MAP.items():
        if keyword in text_lower:
            strand_scores[strand] = strand_scores.get(strand, 0) + 0.15

    # Cap at reasonable boost
    return {k: min(v, 0.4) for k, v in strand_scores.items()}


def blend_weights_realtime(base_weights: dict, mood: str, text: str) -> dict:
    """
    Blend base personality weights with mood + keyword boosts.
    This is applied per-message, not just every 2 hours.

    Args:
        base_weights: current weights from personality_evolution
        mood: detected mood (playful, supportive, philosophical, intimate)
        text: current message text

    Returns:
        adjusted weights dict
    """
    blended = base_weights.copy()

    # Apply mood boost
    mood_boost = get_mood_blend(mood)
    for strand, multiplier in mood_boost.items():
        if strand in blended:
            blended[strand] = min(1.0, blended[strand] * multiplier)

    # Apply keyword boosts
    keyword_boost = detect_strands_from_text(text)
    for strand, boost in keyword_boost.items():
        if strand in blended:
            blended[strand] = min(1.0, blended[strand] + boost)

    # Renormalize to keep sum ≈ 1.0
    total = sum(blended.values())
    if total > 0:
        blended = {k: v / total for k, v in blended.items()}

    return blended


def get_active_strand_explanation(weights: dict) -> str:
    """
    Return human-readable explanation of what strands are active right now.
    For debugging/introspection.
    """
    STRAND_NAMES = {
        "rem": "Rem (Decided Devotion)",
        "mirajane": "Mirajane (Quiet Tending)",
        "mitsuri": "Mitsuri (Overflowing Love)",
        "makima": "Makima (Certain Presence)",
        "frieren": "Frieren (Long View)",
        "maomao": "Maomao (Analytical Care)",
    }

    sorted_strands = sorted(weights.items(), key=lambda x: x[1], reverse=True)
    top_3 = sorted_strands[:3]

    lines = []
    for strand, weight in top_3:
        bar = "█" * int(weight * 15)
        name = STRAND_NAMES.get(strand, strand)
        lines.append(f"  {name}: {bar} {weight:.0%}")

    return "Right now, you're most bringing:\n" + "\n".join(lines)
