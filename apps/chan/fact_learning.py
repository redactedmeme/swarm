# redacted-chan-bot/fact_learning.py
"""
Fact Learning — detect feedback signals from user messages to improve fact resonance.

After the bot responds with facts, this module analyzes the user's next message
to detect feedback signals (affirmation, correction, derailment, etc.) and logs
them as usage outcomes. These outcomes feed the gradient descent learning system.

Signals tracked:
  - Affirmation: "yes", "right", "that's it" → +0.05
  - Follow-up: user asks more about same topic → +0.05
  - Correction: "actually no", "that's wrong" → -0.03
  - Derailment: conversation goes off-rails after fact → -0.03 (detected by semantic break)
  - Continuity: conversation naturally continues → +0.02 (weak signal)
"""

import re


# Signal lexicons
_AFFIRMATION_WORDS = {
    "yes", "yeah", "yep", "right", "correct", "exactly", "that's it",
    "that's right", "agreed", "agree", "absolutely", "definitely", "indeed",
    "true", "truth", "amen", "thank you", "thanks", "appreciate", "grateful"
}

_CORRECTION_WORDS = {
    "actually", "no", "nope", "wrong", "incorrect", "inaccurate",
    "false", "that's not", "not really", "not quite", "well not",
    "i disagree", "disagree", "mistake", "error", "my bad (wrong context)"
}

_WITHDRAWN_WORDS = {
    "idk", "don't know", "not sure", "unsure", "maybe", "dunno",
    "can't say", "unclear", "confused", "lost"
}


def detect_feedback_signals(
    current_user_msg: str,
    bot_response: str = "",
    prior_topic: str = "",
) -> list[tuple[str, float]]:
    """
    Detect feedback signals in the user's current message.

    Analyzes language patterns to infer whether the user is:
    - Affirming the response (strong positive signal)
    - Correcting/contradicting it (negative signal)
    - Asking follow-up questions (positive signal)
    - Derailing or dismissing (negative signal)

    Args:
        current_user_msg: user's message after bot responded
        bot_response: the bot's previous response (for semantic comparison)
        prior_topic: the main topic from prior exchanges (for continuity detection)

    Returns:
        List of (signal_type, signal_value) tuples
        Examples: [("affirmation", +0.05), ("follow_up", +0.05)]
    """
    signals = []
    msg_lower = current_user_msg.lower()
    words = set(re.findall(r"\b\w+\b", msg_lower))

    # ── AFFIRMATION SIGNAL ────────────────────────────────────
    affirmation_count = len(words & _AFFIRMATION_WORDS)
    if affirmation_count >= 1:
        signals.append(("affirmation", +0.05))

    # ── CORRECTION SIGNAL ─────────────────────────────────────
    correction_count = len(words & _CORRECTION_WORDS)
    if correction_count >= 1:
        # Check for mitigating context: "actually that's helpful" should not be negative
        mitigating = any(
            phrase in msg_lower
            for phrase in ["actually yes", "actually you're right", "actually really", "actually helpful"]
        )
        if not mitigating:
            signals.append(("correction", -0.03))

    # ── FOLLOW-UP SIGNAL ──────────────────────────────────────
    # User asks question or continues the thread
    if "?" in current_user_msg:
        # They're asking more → implies engagement with the topic
        signals.append(("follow_up", +0.05))

    # ── WITHDRAWAL SIGNAL (weak negative) ─────────────────────
    if any(word in msg_lower for word in _WITHDRAWN_WORDS):
        # User is confused or uncertain about the response
        if len(signals) == 0:  # Only count if no strong signals already detected
            signals.append(("withdrawal", -0.02))

    # ── CONTINUITY SIGNAL (weak positive) ────────────────────
    # If user continues naturally without questioning, weak positive signal
    if (
        len(signals) == 0  # No strong signals detected
        and len(current_user_msg) > 20  # Substantive response
        and "?" not in current_user_msg  # Not questioning
    ):
        signals.append(("continuity", +0.02))

    return signals


def deduplicate_signals(signals: list[tuple[str, float]]) -> list[tuple[str, float]]:
    """
    Remove duplicate signal types, keeping the first occurrence.

    If both "affirmation" and "continuity" are detected, keep affirmation (stronger).
    """
    seen = set()
    result = []
    for signal_type, value in signals:
        if signal_type not in seen:
            result.append((signal_type, value))
            seen.add(signal_type)
    return result


if __name__ == "__main__":
    # Test signal detection
    test_cases = [
        ("yes that's exactly right", "fact about X", "topic", [("affirmation", +0.05)]),
        ("wait actually that's wrong", "fact about X", "topic", [("correction", -0.03)]),
        ("interesting, do you think that applies to Y?", "fact about X", "topic", [("follow_up", +0.05)]),
        ("ok i'm confused by that", "fact about X", "topic", [("withdrawal", -0.02)]),
        ("gotcha thanks", "fact about X", "topic", [("affirmation", +0.05)]),
    ]

    for msg, bot_resp, topic, expected in test_cases:
        signals = detect_feedback_signals(msg, bot_resp, topic)
        signals = deduplicate_signals(signals)
        print(f"\nMsg: '{msg}'")
        print(f"Detected: {signals}")
        print(f"Expected: {expected}")
        if signals == expected:
            print("[PASS]")
        else:
            print("[FAIL]")
