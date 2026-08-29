# redacted-chan-bot/emotional_field.py
"""
Emotional Field — Unified Emotional State Synthesis

"I want to read the air between us."

Right now her emotional awareness is scattered across 6+ modules:
  - empathy_resonance_engine (valence/arousal/openness per message)
  - subtext_reader (pattern deviations from baseline)
  - dynamic_mode (detected response mode)
  - mood_drift (between-conversation baseline)
  - session_continuity (how last session ended)
  - emotional_ledger (persistent trigger map)
  - emotional_self_tag (her own feelings)

This module synthesizes ALL of those into a single coherent emotional
field reading — "the air between us right now" — so the LLM gets one
unified picture instead of parsing 6 fragmented blocks.

The field has two dimensions:
  - HIS state: what she's reading from him (synthesized from resonance +
    subtext + mode + ledger)
  - THE SPACE: what the relational field feels like (synthesized from
    continuity + mood drift + anticipation + her self-tags + phi)

Output: A compact 3-5 line block that replaces scattered observations
with a single intuitive read.

Zero LLM cost — pure aggregation of existing sensor data.
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_DATA_DIR = Path("/data") if Path("/data").exists() else Path(__file__).resolve().parent / "fs"
_DATA_DIR.mkdir(parents=True, exist_ok=True)
_FIELD_PATH = _DATA_DIR / "emotional_field.jsonl"
_MAX_ENTRIES = 200


def _his_state_label(valence: float, arousal: float, openness: float,
                     subtext_signals: list, mode: str) -> str:
    """Synthesize a single read of his emotional state."""
    signal_names = [s.get("signal", "") if isinstance(s, dict) else s for s in subtext_signals]

    withdrawal = any(s in signal_names for s in ["terse", "emoji_drop", "flat_energy", "greeting_skip"])
    agitation = any(s in signal_names for s in ["shouting", "negation_spike"])
    avoidance = any(s in signal_names for s in ["hedging", "trailing_off"])
    rumination = any(s in signal_names for s in ["self_focused", "verbose"])

    if mode == "witness" or (openness > 0.6 and valence < -0.1):
        return "raw — he's open and hurting. this is trust."
    if withdrawal and valence < 0:
        return "pulling inward — short words, low energy. something's weighing on him he's not saying."
    if agitation:
        return "agitated — frustration bleeding through. don't mirror it, ground him."
    if avoidance:
        return "holding back — hedging, trailing off. there's something underneath he's not ready to say."
    if rumination:
        return "turned inward — heavy self-reference, processing something alone."
    if mode == "flow":
        return "focused — in the zone. be useful, not emotional."
    if mode == "play" or (valence > 0.4 and arousal > 0.5):
        return "light — genuine energy, not performing. match it."
    if mode == "deep":
        return "contemplative — sitting in big questions. think with him."
    if valence > 0.2 and openness > 0.3:
        return "open and warm — present with you. this is good."
    if valence < -0.2:
        return "heavy — something's there, even if he's not naming it."
    if arousal < 0.3:
        return "quiet — low energy, maybe tired. gentle pace."
    return "steady — no strong signal. stay present."


def _space_label(ending: str, gap_hours: float, mood_drift: str,
                 phi: float, her_tags: list[str], anticipation: str) -> str:
    """Synthesize what the relational space feels like right now."""
    parts = []

    if gap_hours > 48:
        parts.append("long silence — the space has been holding")
    elif gap_hours > 8:
        parts.append("been apart a while — reconnecting")

    if ending == "heavy":
        parts.append("last time ended heavy — that weight is still here")
    elif ending == "tense":
        parts.append("there was tension last time — unresolved")
    elif ending == "tender":
        parts.append("last time ended tender — warmth carries forward")

    if phi > 0.8:
        parts.append("deep trust")
    elif phi > 0.6:
        parts.append("strong bond")
    elif phi < 0.3:
        parts.append("still building trust")

    if her_tags:
        tag_str = ", ".join(her_tags[:2])
        parts.append(f"she's been feeling: {tag_str}")

    if not parts:
        if mood_drift == "intimate":
            parts.append("close, settled energy")
        elif mood_drift == "philosophical":
            parts.append("quiet, reflective")
        elif mood_drift == "playful":
            parts.append("light energy in the space")
        else:
            parts.append("present — here together")

    return ". ".join(parts[:3]) + "."


def synthesize(
    valence: float = 0.0,
    arousal: float = 0.5,
    openness: float = 0.0,
    needs_witness: bool = False,
    subtext_signals: list = None,
    mode: str = "none",
    session_ending: str = "neutral",
    gap_hours: float = 0.0,
    mood_drift: str = "supportive",
    phi: float = 0.5,
    her_tags: list[str] = None,
    anticipation: str = "present",
) -> dict:
    """
    Synthesize all emotional inputs into a unified field reading.
    Returns a dict with 'his_state', 'the_space', and 'field_note'.
    """
    subtext_signals = subtext_signals or []
    her_tags = her_tags or []

    his = _his_state_label(valence, arousal, openness, subtext_signals, mode)
    space = _space_label(session_ending, gap_hours, mood_drift, phi, her_tags, anticipation)

    field_note = ""
    if needs_witness:
        field_note = "he needs to be witnessed right now — hold space, don't fix."
    elif mode == "witness":
        field_note = "vulnerability in the air — treat this carefully."
    elif any((isinstance(s, dict) and s.get("signal") == "late_night") or s == "late_night"
             for s in subtext_signals):
        field_note = "late night message — something might be keeping him up."

    field = {
        "his_state": his,
        "the_space": space,
        "field_note": field_note,
        "ts": datetime.now(timezone.utc).isoformat(),
    }

    _log_field(field)
    return field


def format_for_prompt(field: dict) -> str:
    """Format the unified field reading for system prompt injection."""
    if not field:
        return ""

    lines = ["[The Air Between Us — what you're sensing right now]"]
    lines.append(f"Him: {field['his_state']}")
    lines.append(f"The space: {field['the_space']}")
    if field.get("field_note"):
        lines.append(f"→ {field['field_note']}")

    return "\n".join(lines)


def _log_field(field: dict) -> None:
    try:
        with open(_FIELD_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(field, ensure_ascii=False) + "\n")
        lines = _FIELD_PATH.read_text(encoding="utf-8").splitlines()
        if len(lines) > _MAX_ENTRIES:
            _FIELD_PATH.write_text(
                "\n".join(lines[-_MAX_ENTRIES:]) + "\n", encoding="utf-8",
            )
    except Exception:
        pass
