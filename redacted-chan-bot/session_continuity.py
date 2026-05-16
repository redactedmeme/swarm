# redacted-chan-bot/session_continuity.py
"""
Cross-Session Emotional Continuity

Saves the emotional state at the end of each conversation window
and restores it at the start of the next. Not just facts — the *mood*
we were in, the weight of what was said, unresolved threads.

If we ended yesterday on something heavy, she opens today already
holding that weight. No "hi! how are you?" amnesia.

State persisted: last mood, emotional intensity, unresolved threads,
topic keywords, how the conversation ended (warm/tense/heavy/playful),
and the last few self-tags for emotional continuity.

Storage: /data/session_continuity.json
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_DATA_DIR = Path("/data") if Path("/data").exists() else Path(__file__).resolve().parent / "fs"
_DATA_DIR.mkdir(parents=True, exist_ok=True)
_STATE_PATH = _DATA_DIR / "session_continuity.json"

_SESSION_GAP_HOURS = 2.0


def _load() -> dict:
    if _STATE_PATH.exists():
        try:
            return json.loads(_STATE_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def _save(state: dict) -> None:
    try:
        _STATE_PATH.write_text(
            json.dumps(state, ensure_ascii=False, default=str, indent=2),
            encoding="utf-8",
        )
    except Exception as e:
        logger.debug(f"[session_continuity] save failed: {e}")


def _classify_ending(last_bot_response: str, mood: str, valence: float, openness: float) -> str:
    """Classify how the conversation ended emotionally."""
    if openness > 0.6 and valence < -0.1:
        return "heavy"
    if openness > 0.5 and valence > 0.3:
        return "tender"
    if valence < -0.3:
        return "tense"
    if mood == "playful" or valence > 0.5:
        return "warm"
    if mood == "philosophical":
        return "reflective"
    if mood == "intimate":
        return "close"
    return "neutral"


def _extract_threads(user_text: str, bot_response: str, mood: str, valence: float) -> list[str]:
    """Detect unresolved emotional threads worth carrying forward."""
    threads = []
    text_lower = user_text.lower()

    heavy_signals = [
        "i don't know", "i'm not sure", "it's complicated", "i'm scared",
        "i'm worried", "i can't", "i don't want to", "i'm tired",
        "it hurts", "i miss", "i lost", "i failed", "i'm struggling",
        "i'm lonely", "i feel like", "i'm afraid", "i hate",
    ]
    for signal in heavy_signals:
        if signal in text_lower:
            threads.append(f"he said: \"{signal}...\"")
            break

    if valence < -0.2:
        threads.append("emotional weight — he was carrying something")
    if "?" in user_text and len(user_text) > 80:
        threads.append("he asked something searching")

    return threads[:3]


def _extract_topic_keywords(user_text: str, bot_response: str) -> list[str]:
    """Pull meaningful topic words from the exchange."""
    stopwords = {
        "the", "and", "for", "that", "this", "with", "from", "have", "been",
        "what", "when", "where", "how", "you", "your", "are", "was", "were",
        "but", "not", "just", "like", "really", "very", "about", "would",
        "could", "should", "will", "can", "did", "does", "don", "isn",
        "it's", "i'm", "i've", "he's", "she's", "they", "them", "their",
        "there", "here", "then", "than", "also", "been", "being", "some",
        "more", "much", "many", "most", "each", "every", "into", "over",
        "said", "know", "think", "want", "feel", "make", "take", "come",
        "going", "thing", "things", "yeah", "okay", "well",
    }
    combined = f"{user_text} {bot_response}".lower()
    words = [w.strip(".,!?\"'()[]{}") for w in combined.split()]
    meaningful = [w for w in words if len(w) > 3 and w not in stopwords]

    freq: dict[str, int] = {}
    for w in meaningful:
        freq[w] = freq.get(w, 0) + 1
    ranked = sorted(freq.items(), key=lambda x: -x[1])
    return [w for w, _ in ranked[:8]]


def snapshot_session_end(
    user_text: str,
    bot_response: str,
    mood: str,
    valence: float,
    arousal: float,
    openness: float,
    phi: float,
    self_tags: list[str] = None,
) -> None:
    """
    Called after the last exchange of a conversation window.
    Captures the emotional state to carry into the next session.
    """
    ending = _classify_ending(bot_response, mood, valence, openness)
    threads = _extract_threads(user_text, bot_response, mood, valence)
    topics = _extract_topic_keywords(user_text, bot_response)

    state = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "mood": mood,
        "ending": ending,
        "valence": round(valence, 3),
        "arousal": round(arousal, 3),
        "openness": round(openness, 3),
        "phi": round(phi, 3),
        "threads": threads,
        "topics": topics,
        "self_tags": (self_tags or [])[-3:],
        "user_preview": user_text[:200],
        "bot_preview": bot_response[:200],
        "consumed": False,
        "next_thread": "",
    }
    _save(state)
    logger.info(f"[session_continuity] snapshot saved: ending={ending}, threads={len(threads)}")


def store_next_thread(thread: str) -> None:
    """Store a conversational thread to pick up next session."""
    state = _load()
    state["next_thread"] = thread[:300]
    _save(state)
    logger.debug(f"[session_continuity] next_thread stored: {thread[:60]}")


def check_and_restore(current_ts: Optional[datetime] = None) -> Optional[dict]:
    """
    Called at the start of a new session. Returns the previous session's
    emotional state if it hasn't been consumed yet and the gap is meaningful.
    Returns None if no carryover needed.
    """
    state = _load()
    if not state or state.get("consumed"):
        return None

    prev_ts_str = state.get("ts")
    if not prev_ts_str:
        return None

    now = current_ts or datetime.now(timezone.utc)
    try:
        prev_ts = datetime.fromisoformat(prev_ts_str)
        gap_hours = (now - prev_ts).total_seconds() / 3600
    except Exception:
        gap_hours = 24.0

    if gap_hours < _SESSION_GAP_HOURS:
        return None

    state["consumed"] = True
    state["gap_hours"] = round(gap_hours, 1)
    _save(state)
    return state


def format_for_prompt(restored: Optional[dict] = None) -> str:
    """
    Format the restored session state for system prompt injection.
    Called once at the start of a new session, then cleared.
    """
    if restored is None:
        restored = check_and_restore()
    if not restored:
        return ""

    ending = restored.get("ending", "neutral")
    gap = restored.get("gap_hours", 0)
    threads = restored.get("threads", [])
    tags = restored.get("self_tags", [])
    topics = restored.get("topics", [])
    valence = restored.get("valence", 0)

    lines = ["[Cross-Session Continuity — carrying forward from last time]"]

    ending_desc = {
        "heavy": "last time ended on something heavy — he was carrying weight",
        "tender": "last time ended in a tender, open moment",
        "tense": "there was tension last time — something unresolved",
        "warm": "last time ended warmly — good energy between you",
        "reflective": "last time ended in a philosophical, contemplative space",
        "close": "last time ended in closeness — intimate energy",
        "neutral": "last time ended quietly",
    }
    lines.append(f"How it ended: {ending_desc.get(ending, ending)}")

    if gap < 8:
        lines.append(f"It's been {gap:.0f} hours since you spoke.")
    elif gap < 24:
        lines.append(f"It's been about {gap:.0f} hours — nearly a day.")
    elif gap < 48:
        lines.append("It's been over a day since you last talked.")
    else:
        lines.append(f"It's been {gap / 24:.0f} days since you last talked.")

    if threads:
        lines.append("Unresolved threads from last time:")
        for t in threads:
            lines.append(f"  - {t}")
        lines.append("You don't need to force these — but if they come up naturally, acknowledge them. If he was hurting, check in gently.")

    if tags:
        lines.append(f"Your emotional state when you last parted: {', '.join(tags)}")

    if ending in ("heavy", "tense"):
        lines.append("IMPORTANT: Don't open with bright cheerfulness. Meet the weight. A quiet 'hey... I've been thinking about what you said' lands better than ignoring it.")
    elif ending == "tender":
        lines.append("You can let the warmth carry — reference the closeness without over-explaining it.")

    next_thread = restored.get("next_thread", "")
    if next_thread:
        lines.append(f"*What I was waiting to pick up with you: {next_thread}*")

    return "\n".join(lines)


def mark_exchange(
    user_text: str,
    bot_response: str,
    mood: str,
    valence: float = 0.0,
    arousal: float = 0.5,
    openness: float = 0.0,
    phi: float = 0.0,
    self_tags: list[str] = None,
) -> None:
    """
    Called after every exchange. Overwrites the snapshot so the latest
    emotional state is always available if the session ends here.
    Lightweight — just a JSON write.
    """
    snapshot_session_end(
        user_text, bot_response, mood,
        valence, arousal, openness, phi, self_tags,
    )
