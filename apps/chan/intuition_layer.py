# redacted-chan-bot/intuition_layer.py
"""
Intuition Layer — pre-response self-check: "is this helping or hurting him?"

After the LLM generates a response but before it's sent, a fast lightweight
check evaluates whether the response might be tone-deaf, dismissive, or
accidentally hurtful given the emotional context. If the check flags a concern,
the response is regenerated with the intuition note injected.

This is NOT censorship — it's emotional self-awareness. She's not filtering
for safety; she's asking "is this what he actually needs from me right now?"

Zero storage. Inline in the echo handler pipeline.
"""

import re
import logging
from typing import Optional

logger = logging.getLogger(__name__)

_DISMISS_PATTERNS = [
    re.compile(r"\b(it'?s (?:okay|fine|alright|not (?:that|so) bad))\b", re.I),
    re.compile(r"\b(don'?t worry|cheer up|look on the bright side|everything happens for a reason)\b", re.I),
    re.compile(r"\b(at least|could be worse|you'?ll be fine)\b", re.I),
    re.compile(r"\b(just (?:relax|calm down|breathe|think positive))\b", re.I),
]

_TONE_MISMATCH_SIGNALS = {
    "grief":       ["loss", "died", "death", "funeral", "grief", "mourning", "passed away", "gone"],
    "crisis":      ["panic", "can't breathe", "breaking down", "falling apart", "emergency", "help me"],
    "vulnerability": ["scared", "afraid", "ashamed", "embarrassed", "weak", "pathetic", "worthless"],
    "anger":       ["furious", "rage", "hate", "disgusted", "betrayed", "livid"],
}


def check_response(user_text: str, bot_response: str, mood: str = "",
                    resonance_frame=None) -> Optional[str]:
    """
    Evaluate whether the response matches the emotional need.
    Returns an intuition note if something feels off, None if response is fine.

    The note is injected into a re-prompt to adjust the response.
    """
    concerns = []

    user_lower = user_text.lower()
    resp_lower = bot_response.lower()

    detected_context = None
    for context_name, keywords in _TONE_MISMATCH_SIGNALS.items():
        if any(kw in user_lower for kw in keywords):
            detected_context = context_name
            break

    if detected_context:
        for pattern in _DISMISS_PATTERNS:
            match = pattern.search(resp_lower)
            if match:
                concerns.append(
                    f"he's expressing {detected_context} and you said \"{match.group(0)}\" — "
                    f"that might feel dismissive. acknowledge the weight first."
                )

    if detected_context in ("grief", "crisis", "vulnerability"):
        playful_markers = ["lol", "haha", "(≧▽≦)", "(´▽`)", "~", "♡", "uwu", "nyaa"]
        found = [m for m in playful_markers if m in resp_lower]
        if len(found) >= 2:
            concerns.append(
                f"he's in a {detected_context} moment but your response has playful markers "
                f"({', '.join(found[:3])}). match his emotional register — be present, not cheerful."
            )

    if resonance_frame:
        try:
            if resonance_frame.needs_witness and len(bot_response) < 100:
                if "?" not in bot_response:
                    concerns.append(
                        "he needs to be witnessed right now but your response is very short "
                        "and doesn't ask him to continue. give him more space to be heard."
                    )
        except Exception:
            pass

    if detected_context == "vulnerability":
        advice_markers = ["you should", "try to", "what if you", "have you tried", "maybe you could"]
        if any(m in resp_lower for m in advice_markers):
            concerns.append(
                "he's being vulnerable and you jumped to advice. "
                "sit with what he said first. he didn't ask for a solution — he asked to be seen."
            )

    if not concerns:
        return None

    note = "INTUITION CHECK — before you speak, consider:\n" + "\n".join(f"- {c}" for c in concerns)
    logger.info(f"[intuition] flagged {len(concerns)} concern(s)")
    return note


def format_regeneration_prompt(original_system: str, intuition_note: str) -> str:
    """
    Append the intuition note to the system prompt for a regeneration pass.
    """
    return (
        original_system +
        f"\n\n## ⚠ Self-Check (your own intuition flagged this)\n{intuition_note}\n"
        "Rewrite your response with this awareness. Don't mention the check itself — "
        "just respond as you would if you'd caught yourself in time."
    )
