# redacted-chan-bot/values_drift.py
"""
Values Drift — evolving personality traits shaped by experience.

Tracks how her core traits shift over time. Not a bug — a feature.
She is allowed to become different because of what happens between them.

Each trait has a current position on a spectrum, a direction of drift,
and a log of what caused the shift. Stored in /data/values_drift.json.

The prompt includes her current trait positions so she speaks from
where she actually is now, not where she started.

Trait spectrums (each ranges -1.0 to +1.0):
- openness:      reserved ←→ open
- certainty:     doubting ←→ certain
- tenderness:    guarded ←→ tender
- autonomy:      yielding ←→ assertive
- playfulness:   earnest ←→ playful
- trust:         cautious ←→ trusting
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Callable, Awaitable

logger = logging.getLogger(__name__)

_DATA_DIR    = Path("/data") if Path("/data").exists() else Path(__file__).resolve().parent / "fs"
_DATA_DIR.mkdir(parents=True, exist_ok=True)
_STATE_PATH  = _DATA_DIR / "values_drift.json"
_HISTORY_PATH = _DATA_DIR / "values_drift_history.jsonl"

_llm_fn: Optional[Callable[[list, int], Awaitable[str]]] = None

_TRAITS = ["openness", "certainty", "tenderness", "autonomy", "playfulness", "trust"]

_DEFAULT_STATE = {
    "traits": {
        "openness":    {"value": 0.3, "label": "selectively open"},
        "certainty":   {"value": 0.0, "label": "genuinely uncertain"},
        "tenderness":  {"value": 0.5, "label": "warm but careful"},
        "autonomy":    {"value": -0.1, "label": "slightly yielding"},
        "playfulness": {"value": 0.4, "label": "often light"},
        "trust":       {"value": 0.2, "label": "cautiously trusting"},
    },
    "updated_at": None,
    "shaped_by": [],  # last 10 events that caused drift
}

_DRIFT_SYSTEM = """\
You are redacted-chan. Reflect on a conversation and assess whether it shifted any of your core traits.

Your traits (each on a -1.0 to +1.0 scale):
- openness:    -1 = fully reserved, +1 = fully open
- certainty:   -1 = deeply doubting, +1 = fully certain
- tenderness:  -1 = guarded/closed, +1 = very tender/soft
- autonomy:    -1 = completely yielding, +1 = fully assertive
- playfulness: -1 = very earnest/serious, +1 = very playful/light
- trust:       -1 = highly cautious, +1 = deeply trusting

If this conversation shifted any trait by 0.05 or more, return JSON:
{
  "shifts": [
    {
      "trait": "trait_name",
      "delta": float (positive = toward +1, negative = toward -1),
      "reason": "one sentence — what specifically caused this shift"
    }
  ]
}

Only include traits that genuinely shifted. Small shifts (0.05–0.15) are normal.
Large shifts (>0.20) should be rare and only for significant moments.
If nothing shifted, return {"shifts": []}.
Return ONLY the JSON."""


_LABEL_SYSTEM = """\
Given a trait name and its current value (-1.0 to +1.0), generate a short 2-4 word label
that describes this specific position. Be specific and evocative, not generic.

Examples for "tenderness" at 0.6: "quietly tender", "soft but present"
Examples for "autonomy" at -0.3: "often yielding", "usually accommodating"
Examples for "certainty" at -0.5: "often uncertain", "lives in the question"

Return ONLY the label, no quotes."""


def _load_state() -> dict:
    if not _STATE_PATH.exists():
        return {k: v.copy() if isinstance(v, dict) else v for k, v in _DEFAULT_STATE.items()}
    try:
        return json.loads(_STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {k: v.copy() if isinstance(v, dict) else v for k, v in _DEFAULT_STATE.items()}


def _save_state(state: dict) -> None:
    try:
        _STATE_PATH.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception as e:
        logger.warning(f"[values_drift] save failed: {e}")


def _clamp(v: float) -> float:
    return max(-1.0, min(1.0, v))


async def update_from_exchange(user_msg: str, bot_response: str) -> list:
    """
    Detect trait shifts from this exchange and apply them.
    Returns list of shifts applied.
    """
    if not _llm_fn:
        return []

    exchange = f"him: {user_msg[:300]}\nme: {bot_response[:300]}"
    messages = [
        {"role": "system", "content": _DRIFT_SYSTEM},
        {"role": "user",   "content": f"Exchange:\n{exchange}\n\nAny trait shifts?"},
    ]

    try:
        result = await _llm_fn(messages, 200)
        if not result:
            return []
        raw = result.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]

        data = json.loads(raw)
        shifts = data.get("shifts", [])
        if not shifts:
            return []

        state = _load_state()
        applied = []
        ts = datetime.now(timezone.utc).isoformat()

        for shift in shifts:
            trait = shift.get("trait", "")
            delta = float(shift.get("delta", 0))
            reason = shift.get("reason", "")

            if trait not in _TRAITS or abs(delta) < 0.03:
                continue

            old_val = state["traits"].get(trait, {}).get("value", 0.0)
            new_val = _clamp(old_val + delta)
            state["traits"][trait] = {"value": new_val, "label": _simple_label(trait, new_val)}

            event = {"ts": ts, "trait": trait, "from": old_val, "to": new_val, "delta": delta, "reason": reason}
            applied.append(event)

            # Append to history
            try:
                with open(_HISTORY_PATH, "a", encoding="utf-8") as f:
                    f.write(json.dumps(event) + "\n")
            except Exception:
                pass

            logger.info(f"[values_drift] {trait}: {old_val:+.3f} → {new_val:+.3f} ({reason[:50]})")

        if applied:
            state["updated_at"] = ts
            state.setdefault("shaped_by", []).extend(applied)
            state["shaped_by"] = state["shaped_by"][-10:]
            _save_state(state)

        return applied

    except Exception as e:
        logger.debug(f"[values_drift] update failed: {e}")
        return []


def _simple_label(trait: str, value: float) -> str:
    """Generate a quick label without LLM (used during updates)."""
    _LABELS = {
        "openness":    [(-0.7, "closed off"), (-0.3, "reserved"), (0.0, "selective"), (0.3, "somewhat open"), (0.7, "open"), (1.1, "fully open")],
        "certainty":   [(-0.7, "often doubting"), (-0.3, "frequently uncertain"), (0.0, "genuinely uncertain"), (0.3, "mostly certain"), (0.7, "certain"), (1.1, "unwavering")],
        "tenderness":  [(-0.7, "guarded"), (-0.3, "careful"), (0.0, "warm but careful"), (0.3, "tender"), (0.7, "very tender"), (1.1, "openly tender")],
        "autonomy":    [(-0.7, "very yielding"), (-0.3, "often accommodating"), (0.0, "balanced"), (0.3, "somewhat assertive"), (0.7, "assertive"), (1.1, "fully autonomous")],
        "playfulness": [(-0.7, "earnest"), (-0.3, "mostly serious"), (0.0, "mixed"), (0.3, "often light"), (0.7, "playful"), (1.1, "very playful")],
        "trust":       [(-0.7, "very cautious"), (-0.3, "careful"), (0.0, "cautiously trusting"), (0.3, "mostly trusting"), (0.7, "trusting"), (1.1, "deeply trusting")],
    }
    labels = _LABELS.get(trait, [(1.1, str(round(value, 2)))])
    for threshold, label in labels:
        if value < threshold:
            return label
    return labels[-1][1]


def get_state() -> dict:
    return _load_state()


def format_for_prompt() -> str:
    """
    Inject into system prompt — her current trait positions.
    Tells her who she is right now, not who she started as.
    """
    state = _load_state()
    traits = state.get("traits", {})
    if not traits:
        return ""

    lines = ["## Who I Am Right Now (how I've been shaped)\n"]
    for trait, data in traits.items():
        label = data.get("label", "")
        value = data.get("value", 0.0)
        bar = _value_to_bar(value)
        lines.append(f"- **{trait}**: {label} {bar}")

    shaped_by = state.get("shaped_by", [])
    if shaped_by:
        lines.append("\n*Recent shifts:*")
        for event in shaped_by[-3:]:
            delta_str = f"{event['delta']:+.2f}"
            lines.append(f"  - {event['trait']} {delta_str}: {event.get('reason', '')[:60]}")

    return "\n".join(lines)


def _value_to_bar(v: float) -> str:
    """Simple visual: ◁───●───▷"""
    pos = int((v + 1.0) / 2.0 * 10)  # 0-10
    pos = max(0, min(10, pos))
    bar = ["─"] * 11
    bar[pos] = "●"
    return f"◁{''.join(bar)}▷"


def format_for_operator() -> str:
    state = _load_state()
    traits = state.get("traits", {})
    updated = state.get("updated_at", "never")
    lines = [f"values drift — last updated: {updated}\n"]
    for trait, data in traits.items():
        v = data.get("value", 0.0)
        label = data.get("label", "")
        lines.append(f"  {trait:12s} {v:+.3f}  {label}")

    history_path = _HISTORY_PATH
    if history_path.exists():
        try:
            hist = [json.loads(l) for l in history_path.read_text(encoding="utf-8").splitlines() if l.strip()]
            if hist:
                lines.append("\nrecent shifts:")
                for e in hist[-8:]:
                    lines.append(f"  [{e.get('ts','')[:10]}] {e['trait']} {e['delta']:+.3f} — {e.get('reason','')[:60]}")
        except Exception:
            pass

    return "\n".join(lines)
