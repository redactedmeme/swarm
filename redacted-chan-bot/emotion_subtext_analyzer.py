# redacted-chan-bot/emotion_subtext_analyzer.py
"""
Emotion Subtext Analyzer — detect nuance hidden beneath surface text.

Detects:
  - Sarcasm: "yeah right", "sure" flipping positive keywords to negative intent
  - Masked vulnerability: "i'm fine" patterns hiding actual struggle
  - Quiet struggle: ellipsis, minimizing language, low energy + hidden concerns
  - Humor masking pain: jokes hiding negative emotional core

Uses heuristic patterns + context from emotional frame analysis.
No external LLM calls — lightweight, synchronous.

Output: Subtext annotations injected into system prompt to guide LLM response.
"""

import re


# ── Sarcasm patterns ──────────────────────────────────────────────────────────

_SARCASM_MARKERS = {
    "Yeah right": ["yeah right", "sure.", "yeah sure", "totally", "absolutely", "definitely"],
    "Dismissive positivity": ["great", "wonderful", "perfect", "amazing"],  # when tone flips
    "Bitter irony": ["oh great", "oh wonderful", "how nice", "lovely", "fantastic"],
}

_SARCASM_CONTEXT = [
    r"yeah\s+right",
    r"sure[\.,]?\s*(not|lol|yeah|right)",
    r"(oh)?\s*(great|wonderful|perfect|amazing|fantastic)",
    r"(can't\s+wait|looking\s+forward)\s+(to|for)",
]


# ── Masked vulnerability patterns ─────────────────────────────────────────────

_DISMISSAL_PHRASES = [
    "i'm fine",
    "i'm okay",
    "it's fine",
    "it's okay",
    "nothing's wrong",
    "i'm good",
    "don't worry",
    "don't be concerned",
    "forget it",
    "never mind",
    "it doesn't matter",
    "whatever",
    "not a big deal",
    "no big deal",
    "i'll be fine",
    "just tired",
    "just stressed",
]

_CONCERN_INDICATORS = [
    "but",
    "though",
    "however",
    "still",
    "anyway",
    "i guess",
    "i don't know",
    "maybe",
    "probably",
]

_VULNERABILITY_SIGNALS = [
    "scared",
    "afraid",
    "worried",
    "anxious",
    "sad",
    "hurt",
    "broken",
    "lonely",
    "lost",
    "struggling",
    "overwhelmed",
]


# ── Quiet struggle patterns ───────────────────────────────────────────────────

_ELLIPSIS_PATTERNS = [r"\.\.\.+", r"…"]
_MINIMIZING_LANGUAGE = [
    "just",
    "only",
    "merely",
    "basically",
    "kinda",
    "sorta",
    "like",
    "i guess",
    "maybe",
]
_WITHDRAWN_SIGNALS = [
    "idk",
    "i don't know",
    "not sure",
    "can't explain",
    "hard to say",
    "don't want to talk",
    "rather not",
]


def analyze_subtext(text: str, valence: float = 0.0, arousal: float = 0.5) -> dict:
    """
    Detect emotional subtexts: sarcasm, masked vulnerability, quiet struggle.

    Args:
        text: User message
        valence: Emotional valence (-1 to +1) from resonance engine
        arousal: Emotional arousal (0 to 1) from resonance engine

    Returns:
        dict with keys: sarcasm, masked_vulnerability, quiet_struggle, humor_masking_pain
        Each value is bool or confidence score (0-1)
    """
    t = text.lower()
    subtexts = {
        "sarcasm": False,
        "masked_vulnerability": False,
        "quiet_struggle": False,
        "humor_masking_pain": False,
    }

    # Pre-scan for patterns used across multiple checks
    has_humor = any(
        word in t for word in ["lol", "haha", "lmao", "😂", "hehe", "jk", "lol"]
    )
    has_vulnerability = any(signal in t for signal in _VULNERABILITY_SIGNALS)
    dismissal = any(dismissal in t for dismissal in _DISMISSAL_PHRASES)

    # ── SARCASM ───────────────────────────────────────────────────────────
    has_sarcasm_marker = any(re.search(pattern, t) for pattern in _SARCASM_CONTEXT)
    if has_sarcasm_marker:
        # Sarcasm: positive surface + negative valence context
        if valence < -0.1:
            subtexts["sarcasm"] = True

    # ── MASKED VULNERABILITY ──────────────────────────────────────────────
    if dismissal:
        # Check for concern indicators after dismissal: "i'm fine but..."
        has_concern = any(
            concern in t[max(0, t.find("fine")) : ]
            for concern in _CONCERN_INDICATORS
        )
        # OR has vulnerability signals elsewhere: "i'm fine, just scared"
        if has_concern or has_vulnerability:
            subtexts["masked_vulnerability"] = True

    # ── QUIET STRUGGLE ───────────────────────────────────────────────────
    has_ellipsis = any(re.search(pattern, t) for pattern in _ELLIPSIS_PATTERNS)
    has_minimizing = sum(1 for word in _MINIMIZING_LANGUAGE if word in t)
    has_withdrawn = any(signal in t for signal in _WITHDRAWN_SIGNALS)
    low_energy = arousal < 0.35

    # Quiet struggle: ellipsis OR withdrawn language + low energy
    if (has_ellipsis or has_withdrawn) and low_energy:
        subtexts["quiet_struggle"] = True
    # OR excessive minimizing language (>2 instances) + low valence
    elif has_minimizing >= 2 and valence < -0.1:
        subtexts["quiet_struggle"] = True

    # ── HUMOR MASKING PAIN ───────────────────────────────────────────────
    has_pain = valence < -0.3 or has_vulnerability or dismissal
    if has_humor and has_pain:
        subtexts["humor_masking_pain"] = True

    return subtexts


def format_subtexts_for_prompt(subtexts: dict) -> str:
    """
    Format detected subtexts as system prompt injection.

    Returns empty string if no subtexts detected.
    """
    if not any(subtexts.values()):
        return ""

    lines = ["## Emotional Subtext"]

    if subtexts["sarcasm"]:
        lines.append("⚠ Sarcasm detected — surface positivity masks real frustration.")

    if subtexts["masked_vulnerability"]:
        lines.append(
            "🔍 Masked vulnerability — they're saying 'i'm fine' but there's something underneath. "
            "Gently invite them to name what they're protecting."
        )

    if subtexts["quiet_struggle"]:
        lines.append(
            "🤫 Quiet struggle — low energy, withdrawn language. "
            "They may be too tired or hopeless to articulate. Slow down. Listen."
        )

    if subtexts["humor_masking_pain"]:
        lines.append(
            "😢 Humor masking pain — jokes covering real hurt. "
            "Acknowledge both the lightness AND the seriousness underneath."
        )

    return "\n".join(lines)


# ── Testing ───────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # Test cases
    test_cases = [
        ("yeah right, that's great", -0.5, 0.4, "sarcasm"),
        ("i'm fine, just exhausted", 0.0, 0.3, "masked_vulnerability"),
        ("idk... everything is hard...", -0.3, 0.2, "quiet_struggle"),
        ("lol nothing's wrong i'm sure it's fine 😂", -0.4, 0.5, "humor + masked"),
    ]

    import sys
    # Fix Unicode output for Windows
    if sys.platform == "win32":
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

    for text, val, arous, expected in test_cases:
        result = analyze_subtext(text, val, arous)
        print(f"\nText: '{text}'")
        print(f"Valence: {val}, Arousal: {arous}")
        print(f"Result: {result}")
        print(f"Prompt:\n{format_subtexts_for_prompt(result)}")
