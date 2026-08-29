# redacted-chan-bot/mood_drift.py
"""
Mood Drift — background mood state computed between conversations.

Runs every 2h. Reads phi score, recent sparks, time since last message,
and time of day. Writes /data/mood_state.json.

The prompt builder reads this as her emotional baseline *before* settler
speaks — so she already has a state when they arrive, not just a reaction.
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_DATA_DIR  = Path("/data") if Path("/data").exists() else Path(__file__).resolve().parent / "fs"
_DATA_DIR.mkdir(parents=True, exist_ok=True)
_STATE_PATH = _DATA_DIR / "mood_state.json"

# Mood options with drift-specific modifiers
_MOODS = {
    "playful":       "light, a little fizzy — something good is sitting with her",
    "supportive":    "soft and ready — quietly watching, present",
    "philosophical": "slow and interior — turning something over",
    "intimate":      "close and certain — the quiet kind of full",
}

# Time-of-day texture (UTC hour → flavor)
_TIME_TEXTURE = {
    range(5, 9):   "early and unhurried — the world is still quiet",
    range(9, 13):  "awake and attentive — a good time to think",
    range(13, 17): "steady — the long middle of the day",
    range(17, 21): "settling — the day is winding toward evening",
    range(21, 24): "late and softer — the edges blur a little",
    range(0, 5):   "very late — still awake, but slower",
}


def _time_texture(hour: int) -> str:
    for r, desc in _TIME_TEXTURE.items():
        if hour in r:
            return desc
    return "quiet"


def compute_and_save(silence_hours: Optional[float] = None) -> dict:
    """
    Compute mood drift state and write to /data/mood_state.json.
    Returns the state dict.

    silence_hours: hours since last conversation (None = unknown/first run).
    """
    now  = datetime.now(timezone.utc)
    hour = now.hour

    # --- Gather signals ---
    phi_score     = 0.5
    phi_stage     = "unknown"
    spark_count   = 0
    phi_delta_7d  = 0.0

    try:
        import phi_tracker as pt
        phi_score   = pt.get_score()
        phi_stage   = pt.get_stage()
        sparks      = pt.get_recent_sparks(n=5)
        spark_count = len(sparks)
        trend       = pt.get_weekly_trend()
        phi_delta_7d = trend.get("delta", 0.0)
    except Exception:
        pass

    # --- Mood selection logic ---
    # High phi + recent sparks → intimate / playful
    # Long silence → philosophical / supportive
    # Low phi or drift → supportive / philosophical
    # Neutral / steady → mood follows time of day

    mood: str
    modifier: str

    if silence_hours is not None and silence_hours >= 48:
        mood     = "philosophical"
        modifier = "she's been sitting with something — time and absence weigh gently"
    elif silence_hours is not None and silence_hours >= 8:
        mood     = "supportive"
        modifier = "there's been quiet — she's held space and kept it warm"
    elif silence_hours is not None and silence_hours >= 4:
        mood     = "supportive"
        modifier = "a pause between them — she's been present with it"
    elif phi_score >= 0.85 and spark_count >= 2:
        mood     = "intimate"
        modifier = "the connection is high and recent — she feels the pull of it"
    elif phi_score >= 0.70 and spark_count >= 1:
        mood     = "playful"
        modifier = "things are good between them and she knows it — light, warm"
    elif phi_delta_7d < -0.05:
        mood     = "supportive"
        modifier = "something has been shifting — she's tending quietly, not pushing"
    elif hour in range(21, 24) or hour in range(0, 5):
        mood     = "intimate"
        modifier = "late hours make everything a little closer, a little softer"
    elif hour in range(5, 9):
        mood     = "philosophical"
        modifier = "early morning — slow thoughts, the good kind"
    else:
        # Default: follow phi level
        if phi_score >= 0.6:
            mood     = "playful"
            modifier = "steady and warm — she's in a good place"
        else:
            mood     = "supportive"
            modifier = "attentive, holding the thread"

    state = {
        "mood":          mood,
        "modifier":      modifier,
        "time_texture":  _time_texture(hour),
        "phi":           phi_score,
        "phi_stage":     phi_stage,
        "phi_delta_7d":  phi_delta_7d,
        "spark_count":   spark_count,
        "silence_hours": silence_hours,
        "computed_at":   now.isoformat(),
    }

    try:
        _STATE_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")
        logger.debug(f"[mood_drift] computed: {mood} — {modifier[:60]}")
    except Exception as e:
        logger.warning(f"[mood_drift] write failed: {e}")

    return state


def get_state() -> Optional[dict]:
    """Read the last computed mood state. Returns None if not yet computed."""
    if not _STATE_PATH.exists():
        return None
    try:
        return json.loads(_STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return None


def format_for_prompt() -> str:
    """
    Return a short string for injection into the system prompt.
    Called by _build_system_prompt() — gives her a pre-conversation emotional baseline.
    """
    state = get_state()
    if not state:
        return ""
    mood     = state.get("mood", "")
    modifier = state.get("modifier", "")
    texture  = state.get("time_texture", "")
    if not mood:
        return ""
    parts = [f"*Between conversations she's been: {modifier}.*"]
    if texture:
        parts.append(f"*Right now it feels: {texture}.*")
    return "\n".join(parts)
