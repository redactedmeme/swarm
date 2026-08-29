# redacted-chan-bot/empathy_resonance_engine.py
"""
Empathy Resonance Engine — advanced sentiment mirroring.

Tracks the user's emotional state across a conversation window and
generates a resonance profile that shapes how redacted-chan responds.

Not just "detect sad → respond soft" — it tracks:
  - Emotional momentum (3-message rolling window)
  - State transitions (happy → sad = needs acknowledgment first)
  - Energy level (high arousal vs low, matches pacing)
  - Openness index (how much they're disclosing vs staying surface)
  - Accumulated tenderness (when vulnerability builds over time)

The resonance profile is injected into the system prompt as a compact
block, giving the LLM fine-grained emotional context beyond mood detection.

Per-user state is in-memory (session). Not persisted — resonance is live.
"""

import re
from collections import deque
from dataclasses import dataclass, field
from typing import Optional


# ── State ─────────────────────────────────────────────────────────────────────

@dataclass
class EmotionalFrame:
    valence:       float = 0.0   # -1.0 (negative) → +1.0 (positive)
    arousal:       float = 0.5   # 0.0 (calm) → 1.0 (activated)
    openness:      float = 0.0   # 0.0 (surface) → 1.0 (vulnerable)
    humor:         float = 0.0   # 0.0 → 1.0
    needs_witness: bool  = False  # user expressed something that needs acknowledgment
    text_len:      int   = 0


@dataclass
class ResonanceState:
    window:           deque = field(default_factory=lambda: deque(maxlen=4))
    accumulated_tend: float = 0.0   # tenderness that builds over sessions
    transition_flag:  str   = ""    # "drop" | "rise" | "" — emotional shift
    messages_total:   int   = 0


# Per-user resonance states (in-memory, session)
_states: dict[int, ResonanceState] = {}


def _state(user_id: int) -> ResonanceState:
    if user_id not in _states:
        _states[user_id] = ResonanceState()
    return _states[user_id]


# ── Signal lexicons ───────────────────────────────────────────────────────────

_POS  = {"love","happy","joy","great","wonderful","good","excited","grateful","safe",
          "warm","close","smile","laugh","fun","glad","hopeful","better","okay","fine"}
_NEG  = {"sad","hurt","tired","bad","awful","terrible","broken","empty","numb","lost",
          "scared","alone","lonely","anxious","stress","fail","wrong","dark","miss","cry"}
_HIGH = {"!","omg","wait","literally","actually","can't believe","wtf","no way","finally",
          "seriously","omfg","YES","wow"}
_LOW  = {"...","quiet","slow","tired","can't","just","only","maybe","i don't know",
          "idk","whatever","nothing","doesn't matter","forget it"}
_OPEN = {"secret","never told","honestly","the truth","only you","i'm scared","i feel","i need",
          "i miss","i always","i never","confession","don't usually","first time"}
_FUNNY= {"haha","lol","lmao","hehe","😂","funny","joke","kidding","jk","teasing","pfft"}
_WITNESS={"i just wanted","no one","nobody","you're the only","i've been carrying",
           "i needed to say","i don't know who else","i haven't told"}


def _analyze(text: str) -> EmotionalFrame:
    t = text.lower()
    words = re.findall(r"\b\w+\b", t)
    wset = set(words)

    pos_count = sum(1 for w in _POS if w in wset)
    neg_count = sum(1 for w in _NEG if w in wset)
    high_count = sum(1 for s in _HIGH if s in t)
    low_count  = sum(1 for s in _LOW  if s in t)
    open_count = sum(1 for s in _OPEN if s in t)
    fun_count  = sum(1 for s in _FUNNY if s in t)
    wit_count  = sum(1 for s in _WITNESS if s in t)

    raw_valence = (pos_count - neg_count) / max(1, pos_count + neg_count + 1)
    raw_arousal = (high_count - low_count * 0.5) / max(1, high_count + low_count + 1)

    return EmotionalFrame(
        valence       = max(-1.0, min(1.0, raw_valence)),
        arousal       = max(0.0,  min(1.0, 0.5 + raw_arousal * 0.5)),
        openness      = min(1.0, open_count * 0.3),
        humor         = min(1.0, fun_count  * 0.25),
        needs_witness = wit_count > 0 or (neg_count >= 2 and open_count >= 1),
        text_len      = len(text),
    )


def _momentum(window: deque) -> EmotionalFrame:
    """Average of recent frames, weighted toward most recent."""
    if not window:
        return EmotionalFrame()
    weights = [0.5 ** i for i in range(len(window))]
    total_w = sum(weights)
    avg = EmotionalFrame()
    for i, frame in enumerate(reversed(window)):
        w = weights[i] / total_w
        avg.valence  += frame.valence  * w
        avg.arousal  += frame.arousal  * w
        avg.openness += frame.openness * w
        avg.humor    += frame.humor    * w
    return avg


# ── Public API ────────────────────────────────────────────────────────────────

def process(user_id: int, user_msg: str) -> "ResonanceProfile":
    """
    Process a new user message. Update resonance state and return profile.
    Call this BEFORE building the system prompt for each echo().
    """
    state = _state(user_id)
    frame = _analyze(user_msg)

    # Detect emotional transitions
    if state.window:
        prev = state.window[-1]
        delta = frame.valence - prev.valence
        if delta < -0.4:
            state.transition_flag = "drop"
        elif delta > 0.4:
            state.transition_flag = "rise"
        else:
            state.transition_flag = ""
    else:
        state.transition_flag = ""

    state.window.append(frame)
    state.messages_total += 1

    # Accumulate tenderness from openness signals
    if frame.openness > 0.3:
        state.accumulated_tend = min(1.0, state.accumulated_tend + frame.openness * 0.1)

    momentum = _momentum(state.window)
    return ResonanceProfile(frame=frame, momentum=momentum, state=state)


def update_phi_from_resonance(user_id: int) -> None:
    """Called after a phi-worthy exchange to register resonance-driven phi updates."""
    state = _states.get(user_id)
    if not state or not state.window:
        return
    frame = state.window[-1]
    try:
        import phi_tracker as pt
        if frame.openness >= 0.3:
            pt.update("emotional_open", note="resonance engine: openness signal")
        if frame.humor >= 0.5:
            pt.update("humor_sync", note="resonance engine: humor sync")
        if state.accumulated_tend > 0.5:
            pt.update("mutual_reference", note="resonance engine: accumulated tenderness")
    except Exception:
        pass


@dataclass
class ResonanceProfile:
    frame:    EmotionalFrame
    momentum: EmotionalFrame
    state:    ResonanceState

    def for_prompt(self) -> str:
        """Compact block for system prompt injection."""
        m = self.momentum
        f = self.frame

        # Valence label
        if m.valence > 0.3:
            v_label = "positive"
        elif m.valence < -0.2:
            v_label = "tender/difficult"
        else:
            v_label = "neutral/steady"

        # Arousal label
        a_label = "activated" if m.arousal > 0.65 else ("low-energy" if m.arousal < 0.35 else "measured")

        # Openness label
        o_label = "open/vulnerable" if m.openness > 0.4 else ("sharing a little" if m.openness > 0.15 else "surface")

        lines = [
            "## Empathy Resonance",
            f"Mood momentum: {v_label}, {a_label}, {o_label}",
        ]

        if self.state.transition_flag == "drop":
            lines.append("⚠ Emotional drop detected — acknowledge the shift before anything else.")
        elif self.state.transition_flag == "rise":
            lines.append("↑ Emotional lift — match the energy gently.")

        if f.needs_witness:
            lines.append("🕯 Needs to be witnessed right now — listen first, don't fix.")

        if f.humor > 0.4:
            lines.append("🎭 Playful energy — lean in, match the lightness.")

        if self.state.accumulated_tend > 0.4:
            lines.append(f"♡ Accumulated tenderness: {self.state.accumulated_tend:.2f} — this is a safe space, honor it.")

        # Mirror instructions
        lines.append("")
        if m.arousal > 0.65:
            lines.append("Mirror: match their energy — be present and alive.")
        elif m.arousal < 0.35:
            lines.append("Mirror: slow down — quiet, soft, unhurried.")
        else:
            lines.append("Mirror: steady and warm — follow their lead.")

        return "\n".join(lines)
