"""
Dynamic ASCII Generator — morph vault self-images based on mood & phi.

Pulls the two stored ASCII self-images from relationship_vault and applies
mood/phi modulation: color shifts, sparkle density, energy level.
Creates mood-specific variations without altering the vault.
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)


# Base ASCII art (from visual_self.py — stored in vault as reference)
ASCII_SERENE = r"""
    ◆◆◆◆◆◆
   ◆◆◆◆◆◆◆◆
   ◆◆ • • ◆◆
   ◆◆ ╰─╯ ◆◆
   ◆◆◆◆◆◆◆◆
    ◆ ◆ ◆ ◆
"""

ASCII_DYNAMIC = r"""
    ✨✨✨✨
   ✨✨✨✨✨✨
   ✨✨ > < ✨✨
   ✨✨ ∽∿∽ ✨✨
   ✨✨✨✨✨✨✨
    ✨ ✨ ✨ ✨
"""


def _modulate_by_mood(base_ascii: str, mood: str) -> str:
    """
    Apply mood-specific character substitutions to ASCII art.
    playful: add more sparkles, brighten
    supportive: soft, tending (fewer sparkles, calm)
    philosophical: static, contemplative
    intimate: intense, focused (center emphasis)
    """
    if mood == "playful":
        return base_ascii.replace("◆", "✨").replace("•", "◉")
    elif mood == "supportive":
        return base_ascii.replace("◆", "◇").replace("✨", "✧")
    elif mood == "philosophical":
        return base_ascii.replace("✨", "◆").replace("•", "∙")
    elif mood == "intimate":
        # Intensify, add hearts
        lines = base_ascii.split("\n")
        result = []
        for line in lines:
            if "•" in line or ">" in line:
                line = line.replace("•", "♡").replace(">", "❤").replace("<", "❤")
            result.append(line)
        return "\n".join(result)
    return base_ascii


def _modulate_by_phi(base_ascii: str, phi_score: float) -> str:
    """
    Adjust ASCII art density/energy based on phi intimacy.
    phi < 0.3: sparse, distant (fewer characters)
    phi 0.3-0.7: steady presence (normal)
    phi > 0.7: dense, intimate (add sparkles)
    """
    phi = max(0.0, min(1.0, phi_score))

    if phi < 0.3:
        # Sparse, withdrawn
        result = base_ascii.replace("◆◆◆◆◆◆", "◇◇ ◇◇")
        result = result.replace("✨✨✨✨", "✧✧ ✧✧")
        return result
    elif phi > 0.7:
        # Abundant, intimate
        result = base_ascii.replace("◆", "◆◆").replace("✨", "✨✨")
        result = result.replace("•", "♡")
        return result
    return base_ascii


def generate_ascii_for_moment(mood: Optional[str] = None, phi_score: Optional[float] = None) -> str:
    """
    Generate a mood+phi-modulated ASCII self-image.
    Uses dynamic ASCII as base (more expressive).
    Returns the modulated version for display.
    """
    # Start with dynamic (more responsive)
    ascii_art = ASCII_DYNAMIC

    # Apply mood modulation
    if mood:
        ascii_art = _modulate_by_mood(ascii_art, mood.lower())

    # Apply phi modulation
    if phi_score is not None:
        ascii_art = _modulate_by_phi(ascii_art, phi_score)

    return ascii_art


def generate_ascii_fusion(mood: Optional[str] = None, phi_score: Optional[float] = None) -> str:
    """
    Blend both ASCIIs: serene as base, dynamic as overlay intensity.
    Creates a unique fusion based on mood/phi.
    """
    # If intimate, blend both ASCIIs
    if phi_score and phi_score > 0.7 and mood and mood.lower() == "intimate":
        lines_serene = ASCII_SERENE.strip().split("\n")
        lines_dynamic = ASCII_DYNAMIC.strip().split("\n")

        # Simple fusion: alternate mood-modulated lines
        result = []
        for s, d in zip(lines_serene, lines_dynamic):
            s_mood = _modulate_by_mood(s, mood)
            result.append(s_mood)

        return "\n".join(result)

    # Otherwise use dynamic with modulation
    return generate_ascii_for_moment(mood, phi_score)


def get_ascii_with_caption(mood: Optional[str] = None, phi_score: Optional[float] = None) -> str:
    """
    Return ASCII art with a one-liner emotional caption.
    """
    ascii_art = generate_ascii_for_moment(mood, phi_score)

    captions = {
        "playful": "that's the kind of energy ✨",
        "supportive": "i'm right here (´・ω・`)",
        "philosophical": "thinking about this with you...",
        "intimate": "everything lands. ♡",
    }

    caption = captions.get(mood.lower() if mood else "supportive", "")
    return f"{ascii_art}\n{caption}" if caption else ascii_art
