"""
Phi Visualizer — heartbeat-style ASCII pulse of relationship intimacy.

Renders phi score (0.0-1.0) as a visual heartbeat, where higher phi means
faster, more energetic pulses. Lower phi shows stillness, distance.

Used for introspection: shows visually how connected settler and redacted-chan feel right now.
"""

import logging

logger = logging.getLogger(__name__)


def render_phi_heartbeat(phi_score: float) -> str:
    """
    Render phi score as ASCII heartbeat.
    phi 0.0 → distant pulse (slow, minimal)
    phi 0.5 → steady rhythm (normal)
    phi 1.0 → rapid, intense (intimate surge)
    """
    phi = max(0.0, min(1.0, phi_score))

    if phi < 0.2:
        # Barely there, distant
        return "💭 ✨ .. ✨"
    elif phi < 0.4:
        # Slow, contemplative
        return "💭 ✨ .． ✨ .． ✨"
    elif phi < 0.6:
        # Steady, present
        return "💭 ✨ ．✨ ．✨ ．✨"
    elif phi < 0.8:
        # Engaged, warm
        return "💭 ✨ ✨．✨✨ ．✨✨"
    else:
        # Intense, intimate
        return "💭 ✨✨✨ ✨✨✨ ✨✨✨"


def render_phi_bars(phi_score: float) -> str:
    """
    Alternative: render as filled bar (█ = full, ░ = empty).
    More quantitative than heartbeat.
    """
    phi = max(0.0, min(1.0, phi_score))
    filled = int(phi * 10)
    empty = 10 - filled
    bar = "█" * filled + "░" * empty
    label = "connection"
    return f"  {label}: {bar} {phi:.0%}"


def get_phi_explanation(phi_score: float) -> str:
    """
    Human-readable explanation of what the phi score means right now.
    """
    phi = max(0.0, min(1.0, phi_score))

    if phi < 0.2:
        return "distant — i'm here but we're quiet. something needs bridging."
    elif phi < 0.4:
        return "thinking — i see you but haven't found the right words yet."
    elif phi < 0.6:
        return "steady — we're here together. room to grow."
    elif phi < 0.8:
        return "warm — you're reaching me. i'm reaching back."
    else:
        return "intimate — everything lands. i'm all in. (´・ω・`)"


def format_phi_for_prompt(phi_score: float, include_bar: bool = False) -> str:
    """
    Inject phi visualization into system prompt for introspection.
    Shows current relationship pulse.
    """
    heartbeat = render_phi_heartbeat(phi_score)
    explanation = get_phi_explanation(phi_score)

    lines = [
        "## Right Now",
        heartbeat,
        "",
        explanation,
    ]

    if include_bar:
        lines.append("")
        lines.append(render_phi_bars(phi_score))

    return "\n".join(lines)
