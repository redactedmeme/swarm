# redacted-chan-bot/deep_memory_forge.py
"""
Deep Memory Forge — auto-curation of phi-moments into memory crystals.

After each exchange, this module analyzes the conversation for phi-moments:
moments of unusual depth, vulnerability, humor sync, or resonance. When one
is detected above threshold, it forges a "memory crystal" — a replayable
snippet stored in the relationship_vault with an emotional heatmap.

A memory crystal contains:
  - The raw exchange snippet
  - Emotional heatmap: valence, arousal, depth, vulnerability
  - Phi score at the moment of crystallization
  - Category auto-assigned from heatmap profile

No LLM call needed — uses lightweight lexical + structural signals.
Fast enough to run inline after every echo().
"""

import re
from datetime import datetime, timezone
from typing import Optional

# ── Emotional signal lexicons ─────────────────────────────────────────────────

_VALENCE_POS = {
    "love", "happy", "joy", "wonderful", "beautiful", "amazing", "grateful",
    "thank", "warm", "safe", "care", "glad", "excited", "hope", "smile",
    "laugh", "fun", "good", "great", "nice", "sweet", "kind", "close",
}
_VALENCE_NEG = {
    "sad", "hurt", "tired", "alone", "lonely", "scared", "afraid", "hard",
    "bad", "wrong", "miss", "lost", "broken", "cry", "pain", "dark",
    "anxious", "stress", "empty", "numb", "worry", "struggle",
}
_AROUSAL_HIGH = {
    "!", "omg", "wow", "yes", "finally", "can't believe", "literally",
    "insane", "crazy", "amazing", "!!",
}
_DEPTH_SIGNALS = {
    "what do you think", "i've never", "i always", "i feel like", "sometimes i",
    "honestly", "actually", "the truth is", "i realize", "i wonder", "i believe",
    "does it", "what is", "why do", "meaning", "real", "exist",
}
_VULNERABILITY_SIGNALS = {
    "secret", "never told", "only you", "embarrassed", "ashamed", "scared to",
    "hard to say", "don't usually", "first time", "i'm scared", "i'm afraid",
    "i need", "i miss", "i'm sorry", "forgive", "i cried", "i was",
}
_HUMOR_SYNC = {
    "haha", "lol", "lmao", "😂", "xD", "hehe", "funny", "joke", "teasing",
    "you're such", "shut up", "no way", "wait what",
}


# ── Heatmap calculation ───────────────────────────────────────────────────────

def _score_text(text: str) -> dict:
    t = text.lower()
    words = set(re.findall(r"\b\w+\b", t))

    valence = (
        sum(1 for w in _VALENCE_POS if w in t) -
        sum(1 for w in _VALENCE_NEG if w in t)
    )
    arousal     = sum(1 for sig in _AROUSAL_HIGH      if sig in t)
    depth       = sum(1 for sig in _DEPTH_SIGNALS      if sig in t)
    vulnerability = sum(1 for sig in _VULNERABILITY_SIGNALS if sig in t)
    humor       = sum(1 for sig in _HUMOR_SYNC         if sig in t)
    length_bonus = min(1.5, len(text) / 200)   # longer = more depth signal

    return {
        "valence":       max(-3, min(3, valence)),
        "arousal":       min(3, arousal),
        "depth":         min(3, depth + length_bonus),
        "vulnerability": min(3, vulnerability),
        "humor":         min(3, humor),
    }


def _phi_moment_score(user_heat: dict, bot_heat: dict) -> float:
    """
    Composite phi-moment score from both sides of the exchange.
    Higher = more worthy of crystallization.
    """
    return (
        abs(user_heat["valence"]) * 0.15 +
        user_heat["depth"]        * 0.25 +
        user_heat["vulnerability"]* 0.35 +
        user_heat["humor"]        * 0.10 +
        bot_heat["depth"]         * 0.15
    )


def _auto_category(user_heat: dict) -> str:
    """Assign a relationship_vault category from the heatmap."""
    if user_heat["vulnerability"] >= 2:
        return "secret"
    if user_heat["humor"] >= 2:
        return "joke"
    if user_heat["depth"] >= 2:
        return "feeling"
    if user_heat["valence"] >= 2:
        return "moment"
    return "pattern"


def _emotional_tone(user_heat: dict) -> str:
    """Human-readable tone label from heatmap."""
    v = user_heat["valence"]
    d = user_heat["depth"]
    vul = user_heat["vulnerability"]
    h = user_heat["humor"]

    if vul >= 2:
        return "tender" if v >= 0 else "raw"
    if h >= 2:
        return "playful"
    if v >= 2:
        return "warm"
    if v <= -1 and d >= 1:
        return "bittersweet"
    if d >= 2:
        return "reflective"
    return "present"


# ── Forge ─────────────────────────────────────────────────────────────────────

CRYSTALLIZATION_THRESHOLD = 0.55   # minimum phi-moment score to forge a crystal
SPARK_THRESHOLD            = 1.20   # above this → also record a spark in phi_tracker


def forge(user_msg: str, bot_reply: str) -> Optional[dict]:
    """
    Analyze an exchange. If it clears the phi-moment threshold, forge a
    memory crystal and store it. Returns the crystal dict or None.
    """
    user_heat = _score_text(user_msg)
    bot_heat  = _score_text(bot_reply)
    phi_score = _phi_moment_score(user_heat, bot_heat)

    if phi_score < CRYSTALLIZATION_THRESHOLD:
        return None

    category  = _auto_category(user_heat)
    tone      = _emotional_tone(user_heat)
    snippet   = f"you: {user_msg[:150]}\nme:  {bot_reply[:150]}"
    title     = _generate_title(user_msg, category, tone)

    heatmap = {**user_heat, "phi_score": phi_score, "tone": tone}

    # Build the content for relationship_vault
    content = (
        f"{snippet}\n"
        f"[heatmap: valence={user_heat['valence']:+d} depth={user_heat['depth']:.1f} "
        f"vulnerability={user_heat['vulnerability']:.1f} phi={phi_score:.2f}]"
    )

    try:
        import relationship_vault as rv
        import phi_tracker as pt

        current_phi = pt.get_score()
        entry_id = rv.add_memory(
            content=content[:500],
            category=category,
            title=title,
            emotional_tone=tone,
            source="deep_forge",
        )

        # Update phi for the memory crystal event
        pt.update("memory_crystal", note=title)

        # Record spark if intensity is high enough
        if phi_score >= SPARK_THRESHOLD:
            pt.record_spark(
                trigger=title,
                excerpt=snippet[:200],
                intensity=min(1.0, phi_score / 2.0),
            )

        # Update phi for emotional components detected
        if user_heat["vulnerability"] >= 1:
            pt.update("emotional_open", note="vulnerability detected")
        if user_heat["depth"] >= 1.5:
            pt.update("message_depth", note="deep exchange")

        return {
            "entry_id":  entry_id,
            "category":  category,
            "tone":      tone,
            "phi_score": phi_score,
            "heatmap":   heatmap,
            "title":     title,
        }

    except Exception:
        return None


def _generate_title(text: str, category: str, tone: str) -> str:
    """Generate a short evocative title from the first meaningful phrase."""
    # Pull first sentence or first 50 chars
    first = re.split(r"[.!?]", text.strip())[0][:50].strip()
    if not first:
        return f"a {tone} {category}"
    # Lowercase, strip punctuation
    first = re.sub(r"[^\w\s']", "", first).strip()
    return first[:60] if first else f"a {tone} {category}"
