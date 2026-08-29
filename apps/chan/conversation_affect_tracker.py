# redacted-chan-bot/conversation_affect_tracker.py
"""
Within-conversation emotional arc tracker.

Scores each turn for intensity (0–1) and valence (−1 to +1) using keyword
analysis — no LLM calls, no I/O per turn. Detects trajectory shifts
(escalating / de-escalating / stable / volatile) and formats a compact arc
summary for system prompt injection so she knows the emotional weight she's
been carrying through this conversation, not just her pre-session baseline.

Usage:
    import conversation_affect_tracker as cat

    # In _build_system_prompt / before LLM call:
    arc_block = cat.format_for_prompt(user_id)

    # After exchange completes:
    cat.record_turn(user_id, user_message, bot_reply)

    # On session reset (long gap, /reset, etc.):
    cat.reset_session(user_id)
"""

from __future__ import annotations

import logging
import re
import time
from typing import Optional

logger = logging.getLogger(__name__)

# ── Keyword banks ─────────────────────────────────────────────────────────────

# (intensity_score, [keywords])
_INTENSITY_TIERS: list[tuple[float, list[str]]] = [
    (1.0, [
        "suicide", "kill myself", "end it", "can't go on", "give up on life",
        "nothing matters", "no point", "disappear forever",
    ]),
    (0.85, [
        "desperate", "hopeless", "devastated", "shattered", "broken",
        "suffocating", "drowning", "unbearable", "can't breathe", "falling apart",
        "terrified", "panic", "crisis", "destroyed",
    ]),
    (0.70, [
        "hurt", "scared", "alone", "exhausted", "empty", "numb", "lost",
        "miss you", "missing you", "grief", "grieving", "crying", "tears",
        "afraid", "anxious", "overwhelmed", "trapped", "stuck", "hate",
        "angry", "furious", "heartbroken", "betrayed", "abandoned",
    ]),
    (0.50, [
        "tired", "sad", "worried", "stressed", "confused", "uncertain",
        "frustrated", "disappointed", "sorry", "regret", "doubt",
        "uncomfortable", "uneasy", "hard", "difficult", "struggle",
        "missing", "lonely", "bored",
    ]),
    (0.30, [
        "okay", "fine", "alright", "good", "happy", "nice", "glad",
        "curious", "wondering", "thinking", "maybe", "perhaps", "interesting",
        "want", "need", "like",
    ]),
    (0.10, [
        "what", "how", "when", "where", "why", "tell me", "explain",
        "yes", "no", "thanks", "sure", "got it",
    ]),
]

# Positive valence words (+)
_POS_WORDS = {
    "love", "happy", "joy", "grateful", "thankful", "excited", "beautiful",
    "wonderful", "amazing", "hope", "hopeful", "warm", "safe", "better",
    "good", "great", "glad", "smile", "laugh", "peaceful", "calm", "free",
    "light", "bright", "together", "close", "connected", "understand",
    "understood", "proud", "strong", "healing", "growing",
}

# Negative valence words (−)
_NEG_WORDS = {
    "hurt", "pain", "sad", "scared", "fear", "alone", "empty", "lost",
    "broken", "tired", "hopeless", "desperate", "dark", "heavy", "hard",
    "bad", "terrible", "awful", "hate", "angry", "guilt", "shame",
    "fail", "wrong", "cold", "distant", "numb", "dead", "grey",
    "miss", "missing", "gone", "alone", "ugly", "worthless", "stupid",
}

# Trajectory labels with direction arrows
_TRAJ_LABELS = {
    "escalating":     ("escalating ↑", "weight is building — hold this carefully"),
    "de-escalating":  ("de-escalating ↓", "she's finding steadier ground"),
    "volatile":       ("volatile ↕", "the emotional current is shifting fast"),
    "warming":        ("warming ↗", "something is opening up"),
    "cooling":        ("cooling ↘", "settling, closing a little"),
    "stable":         ("stable →", "consistent emotional register"),
    "opening":        ("first turns — no arc yet", ""),
}

# ── In-memory session state ───────────────────────────────────────────────────

class _SessionState:
    __slots__ = ("turns", "reset_at")

    def __init__(self):
        self.turns: list[dict] = []   # {"intensity": float, "valence": float, "keywords": list[str], "ts": float}
        self.reset_at: float = time.time()


_sessions: dict[int, _SessionState] = {}
_SESSION_GAP_SEC = 3600  # reset after 1h silence


def _get_session(user_id: int) -> _SessionState:
    s = _sessions.get(user_id)
    now = time.time()
    if s is None or (s.turns and now - s.turns[-1]["ts"] > _SESSION_GAP_SEC):
        s = _SessionState()
        _sessions[user_id] = s
    return s


def reset_session(user_id: int) -> None:
    """Explicitly reset arc for this user (e.g. after long gap or /reset)."""
    _sessions[user_id] = _SessionState()


# ── Scoring ───────────────────────────────────────────────────────────────────

def _score_text(text: str) -> tuple[float, float, list[str]]:
    """
    Score a text string.
    Returns (intensity 0–1, valence −1 to +1, list of matched keywords).
    """
    text_lower = text.lower()
    words = set(re.findall(r"\b\w+\b", text_lower))

    # Intensity: highest tier match wins, then average remaining
    intensity = 0.15  # floor for any non-empty message
    matched_kw: list[str] = []

    for score, kws in _INTENSITY_TIERS:
        for kw in kws:
            if kw in text_lower:
                matched_kw.append(kw)
                if score > intensity:
                    intensity = score

    # Valence
    pos_hits = words & _POS_WORDS
    neg_hits = words & _NEG_WORDS
    total_hits = len(pos_hits) + len(neg_hits)
    if total_hits == 0:
        valence = 0.0
    else:
        valence = (len(pos_hits) - len(neg_hits)) / total_hits

    return round(min(intensity, 1.0), 3), round(max(-1.0, min(1.0, valence)), 3), matched_kw[:5]


def record_turn(user_id: int, user_msg: str, bot_reply: str) -> dict:
    """
    Score this turn and update the session arc.
    Combines user message (weighted 2×) and bot reply for a blended reading.
    Returns the turn dict.
    """
    # User message carries more emotional weight than bot reply
    u_intensity, u_valence, u_kw = _score_text(user_msg)
    b_intensity, b_valence, _    = _score_text(bot_reply)

    blended_intensity = round((u_intensity * 2 + b_intensity) / 3, 3)
    blended_valence   = round((u_valence   * 2 + b_valence)   / 3, 3)

    turn = {
        "intensity": blended_intensity,
        "valence":   blended_valence,
        "keywords":  u_kw,
        "ts":        time.time(),
    }

    s = _get_session(user_id)
    s.turns.append(turn)

    # Trim to last 20 turns (rolling window)
    if len(s.turns) > 20:
        s.turns = s.turns[-20:]

    logger.debug(
        "[affect_tracker] turn %d — intensity=%.2f valence=%.2f kw=%s",
        len(s.turns), blended_intensity, blended_valence, u_kw,
    )
    return turn


# ── Trajectory detection ──────────────────────────────────────────────────────

def _avg_intensity(turns: list[dict]) -> float:
    if not turns:
        return 0.0
    return sum(t["intensity"] for t in turns) / len(turns)


def _avg_valence(turns: list[dict]) -> float:
    if not turns:
        return 0.0
    return sum(t["valence"] for t in turns) / len(turns)


def _detect_trajectory(turns: list[dict]) -> str:
    if len(turns) < 4:
        return "opening"

    early  = turns[:max(2, len(turns) // 3)]
    recent = turns[-max(2, len(turns) // 3):]

    e_int = _avg_intensity(early)
    r_int = _avg_intensity(recent)
    e_val = _avg_valence(early)
    r_val = _avg_valence(recent)

    int_delta = r_int - e_int
    val_delta = r_val - e_val

    # Variance check for volatile
    intensities = [t["intensity"] for t in turns[-6:]]
    variance = max(intensities) - min(intensities) if len(intensities) >= 3 else 0

    if variance > 0.35:
        return "volatile"
    if int_delta > 0.20:
        return "escalating"
    if int_delta < -0.20:
        return "de-escalating"
    if val_delta > 0.25:
        return "warming"
    if val_delta < -0.25:
        return "cooling"
    return "stable"


def _describe_tone(avg_intensity: float, avg_valence: float, keywords: list[str]) -> str:
    """Convert numbers to a short human-readable tone description."""
    parts = []

    if avg_intensity >= 0.75:
        parts.append("heavy")
    elif avg_intensity >= 0.55:
        parts.append("weighted")
    elif avg_intensity >= 0.35:
        parts.append("engaged")
    else:
        parts.append("light")

    if avg_valence <= -0.4:
        parts.append("dark")
    elif avg_valence <= -0.15:
        parts.append("tender")
    elif avg_valence >= 0.4:
        parts.append("warm")
    elif avg_valence >= 0.15:
        parts.append("open")
    else:
        parts.append("neutral")

    if keywords:
        parts.append(f'("{keywords[0]}")')

    return ", ".join(parts)


# ── Public API ────────────────────────────────────────────────────────────────

def get_arc(user_id: int) -> Optional[dict]:
    """Return the current arc dict for this user, or None if < 2 turns."""
    s = _sessions.get(user_id)
    if not s or len(s.turns) < 2:
        return None

    turns = s.turns
    trajectory = _detect_trajectory(turns)

    early  = turns[:max(2, len(turns) // 3)]
    recent = turns[-max(2, len(turns) // 3):]

    peak_turn = max(range(len(turns)), key=lambda i: turns[i]["intensity"])
    peak      = turns[peak_turn]

    all_kw = []
    for t in turns[-4:]:
        all_kw.extend(t.get("keywords", []))
    recent_kw = list(dict.fromkeys(all_kw))[:4]  # deduplicated

    return {
        "turn_count":       len(turns),
        "trajectory":       trajectory,
        "early_intensity":  round(_avg_intensity(early), 2),
        "early_valence":    round(_avg_valence(early), 2),
        "recent_intensity": round(_avg_intensity(recent), 2),
        "recent_valence":   round(_avg_valence(recent), 2),
        "peak_intensity":   round(peak["intensity"], 2),
        "peak_turn":        peak_turn + 1,
        "peak_keywords":    peak.get("keywords", []),
        "recent_keywords":  recent_kw,
    }


def format_for_prompt(user_id: int) -> str:
    """
    Return a compact arc block for system prompt injection.
    Returns empty string if < 2 turns (no arc yet).
    """
    arc = get_arc(user_id)
    if not arc:
        return ""

    traj_key   = arc["trajectory"]
    traj_label, traj_note = _TRAJ_LABELS.get(traj_key, (traj_key, ""))

    early_tone  = _describe_tone(arc["early_intensity"],  arc["early_valence"],  [])
    recent_tone = _describe_tone(arc["recent_intensity"], arc["recent_valence"], arc["recent_keywords"])

    lines = [
        "## This Conversation's Emotional Arc",
        f"Turns: {arc['turn_count']} | Trajectory: {traj_label}",
        f"Early tone: {early_tone} (intensity {arc['early_intensity']})",
        f"Current tone: {recent_tone} (intensity {arc['recent_intensity']})",
    ]

    if arc["peak_intensity"] >= 0.60 and arc["peak_turn"] <= arc["turn_count"] - 2:
        kw_str = f' — "{arc["peak_keywords"][0]}"' if arc["peak_keywords"] else ""
        lines.append(
            f"Peak: turn {arc['peak_turn']} (intensity {arc['peak_intensity']}{kw_str})"
        )

    if traj_note:
        lines.append(traj_note.capitalize() + ".")

    return "\n".join(lines)
