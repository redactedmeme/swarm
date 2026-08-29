# redacted-chan-bot/love_signal_detector.py
"""
Love Signal Detector — decides WHEN to surface a vault memory.

Not every message warrants a memory injection. This module detects the type
of moment and whether injecting a memory would deepen connection or interrupt it.

Signal types:
  VULNERABILITY      — openness high, needs_witness; surface feeling/secret
  ECHO               — current topic overlaps a past vault entry; surface that specific one
  JOY_PEAK           — high valence + arousal; surface a joy or joke memory
  LONGING            — missing-words, low arousal drift; surface a warm moment
  MILESTONE_ADJACENCY— phi just spiked this session; surface a milestone memory

Returns (inject=False) for:
  TENDER_PAUSE       — short message after long one; silence is right
  TOPIC_SWITCH_DROP  — emotional floor-drop; let it land first
  COOLDOWN           — memory injected in last 4 exchanges
  NOTHING_MATCHES    — no vault candidate meets threshold
"""

import re
from dataclasses import dataclass
from typing import Optional


# ── Signal type constants ─────────────────────────────────────────────────────

VULNERABILITY       = "VULNERABILITY"
ECHO                = "ECHO"
JOY_PEAK            = "JOY_PEAK"
LONGING             = "LONGING"
MILESTONE_ADJACENCY = "MILESTONE_ADJACENCY"
NO_INJECT           = "NO_INJECT"

# Preferred vault categories per signal type (phi-gating applied separately)
SIGNAL_CATEGORY_HINTS = {
    VULNERABILITY:       ["feeling", "secret", "moment"],
    ECHO:                [],          # any — the specific matched memory wins
    JOY_PEAK:            ["joke", "moment"],
    LONGING:             ["moment", "feeling"],
    MILESTONE_ADJACENCY: ["milestone", "feeling"],
}

# Longing markers
_LONGING_WORDS = {
    "i miss", "wish", "used to", "remember when", "back when",
    "i forget", "feels like forever", "i haven't", "it's been",
    "when we", "that time", "do you remember",
}

# Positive affirmation words for ECHO outcome detection (re-used in engine)
AFFIRMATION_WORDS = {"yes", "exactly", "i remember", "that time", "yeah", "right", "true"}


# ── Result dataclass ──────────────────────────────────────────────────────────

@dataclass
class LoveSignal:
    inject: bool
    signal_type: str
    confidence: float       # 0.0 – 1.0
    category_hint: list     # preferred vault categories to search first
    reason: str = ""        # debug/audit trail


# ── Detection logic ───────────────────────────────────────────────────────────

def detect(
    frame,                          # EmotionalFrame from empathy_resonance_engine
    resonance_state,                # ResonanceState (transition_flag, window, accumulated_tend)
    phi: float,
    user_msg: str,
    recent_injection_count: int,    # how many injections in last 4 exchanges
) -> LoveSignal:
    """
    Main detection. Returns LoveSignal indicating whether and what to inject.

    Priority order:
      1. Hard skip conditions (cooldown, tender pause, emotional drop)
      2. VULNERABILITY — highest relational value
      3. ECHO — specific memory match
      4. MILESTONE_ADJACENCY — phi-gated
      5. LONGING
      6. JOY_PEAK
    """
    msg_lower = user_msg.lower().strip()
    msg_len = len(user_msg.strip())

    # ── Hard skip: cooldown ───────────────────────────────────────────────────
    if recent_injection_count >= 1:
        return LoveSignal(False, NO_INJECT, 0.0, [], reason="cooldown")

    # ── Hard skip: tender pause ───────────────────────────────────────────────
    # Short message (<= 15 chars) after a long one — they're settling, don't fill
    prev_len = resonance_state.window[-2].text_len if len(resonance_state.window) >= 2 else 0
    if msg_len <= 15 and prev_len > 150:
        return LoveSignal(False, NO_INJECT, 0.0, [], reason="tender_pause")

    # ── Hard skip: emotional floor-drop ──────────────────────────────────────
    if resonance_state.transition_flag == "drop":
        return LoveSignal(False, NO_INJECT, 0.0, [], reason="emotional_drop")

    # ── VULNERABILITY ─────────────────────────────────────────────────────────
    if frame.needs_witness or frame.openness >= 0.45:
        confidence = min(1.0, frame.openness * 1.2 + (0.2 if frame.needs_witness else 0.0))
        return LoveSignal(
            inject=True,
            signal_type=VULNERABILITY,
            confidence=confidence,
            category_hint=SIGNAL_CATEGORY_HINTS[VULNERABILITY],
            reason=f"openness={frame.openness:.2f} needs_witness={frame.needs_witness}",
        )

    # ── MILESTONE_ADJACENCY — phi-gated at 0.70 ──────────────────────────────
    if phi >= 0.70:
        # Check if phi spiked recently (spark in last session)
        try:
            import phi_tracker as pt
            sparks = pt.get_recent_sparks(n=3)
            from datetime import datetime, timezone, timedelta
            cutoff = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
            recent_spark = any(s["ts"] >= cutoff for s in sparks)
        except Exception:
            recent_spark = False
        if recent_spark:
            return LoveSignal(
                inject=True,
                signal_type=MILESTONE_ADJACENCY,
                confidence=0.80,
                category_hint=SIGNAL_CATEGORY_HINTS[MILESTONE_ADJACENCY],
                reason="phi>=0.70 + recent spark",
            )

    # ── LONGING ───────────────────────────────────────────────────────────────
    if any(phrase in msg_lower for phrase in _LONGING_WORDS):
        return LoveSignal(
            inject=True,
            signal_type=LONGING,
            confidence=0.70,
            category_hint=SIGNAL_CATEGORY_HINTS[LONGING],
            reason="longing phrase detected",
        )
    # Also catch low-arousal drift with slightly negative valence
    if frame.valence < -0.1 and frame.arousal < 0.35 and frame.openness > 0.15:
        return LoveSignal(
            inject=True,
            signal_type=LONGING,
            confidence=0.55,
            category_hint=SIGNAL_CATEGORY_HINTS[LONGING],
            reason=f"low arousal drift valence={frame.valence:.2f}",
        )

    # ── JOY_PEAK ─────────────────────────────────────────────────────────────
    if frame.valence > 0.5 and frame.arousal > 0.6:
        return LoveSignal(
            inject=True,
            signal_type=JOY_PEAK,
            confidence=0.65,
            category_hint=SIGNAL_CATEGORY_HINTS[JOY_PEAK],
            reason=f"joy peak valence={frame.valence:.2f} arousal={frame.arousal:.2f}",
        )

    # ── Nothing matched ───────────────────────────────────────────────────────
    return LoveSignal(False, NO_INJECT, 0.0, [], reason="no signal")


# ── Phi depth gate ────────────────────────────────────────────────────────────

PHI_CATEGORY_GATES = [
    (0.70, ["milestone"]),
    (0.50, ["secret"]),
    (0.30, ["feeling"]),
    (0.15, ["pattern"]),
    (0.00, ["joke", "moment"]),
]


def unlocked_categories(phi: float) -> list[str]:
    """Return all vault categories accessible at this phi score."""
    unlocked = []
    for threshold, cats in PHI_CATEGORY_GATES:
        if phi >= threshold:
            unlocked.extend(cats)
    return unlocked


def filter_to_phi_gate(categories: list[str], phi: float) -> list[str]:
    """Remove categories not yet unlocked at current phi."""
    ok = set(unlocked_categories(phi))
    return [c for c in categories if c in ok]
