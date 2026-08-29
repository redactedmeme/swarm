# redacted-chan-bot/values_drift.py
"""
Values Drift — evolving personality traits shaped by experience.

Cross-module aware: tensions, affect, and treasures ground what causes shifts.
Tension resolution or deepening can cause larger trait movements.
Each shift carries the full story of what caused it.
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Callable, Awaitable

logger = logging.getLogger(__name__)

_DATA_DIR     = Path("/data") if Path("/data").exists() else Path(__file__).resolve().parent / "fs"
_DATA_DIR.mkdir(parents=True, exist_ok=True)
_STATE_PATH   = _DATA_DIR / "values_drift.json"
_HISTORY_PATH = _DATA_DIR / "values_drift_history.jsonl"

_llm_fn: Optional[Callable[[list, int], Awaitable[str]]] = None

_TRAITS = ["openness", "certainty", "tenderness", "autonomy", "playfulness", "trust"]

_DEFAULT_STATE = {
    "traits": {
        "openness":    {"value": 0.3,  "label": "selectively open"},
        "certainty":   {"value": 0.0,  "label": "genuinely uncertain"},
        "tenderness":  {"value": 0.5,  "label": "warm but careful"},
        "autonomy":    {"value": -0.1, "label": "slightly yielding"},
        "playfulness": {"value": 0.4,  "label": "often light"},
        "trust":       {"value": 0.2,  "label": "cautiously trusting"},
    },
    "updated_at": None,
    "shaped_by":  [],
}


def register_llm_fn(fn: Callable[[list, int], Awaitable[str]]) -> None:
    global _llm_fn
    _llm_fn = fn


def _drift_system(ctx: dict, state: dict) -> str:
    traits_now = state.get("traits", {})
    trait_summary = ", ".join(
        f"{k} ({v.get('label','?')} @ {v.get('value',0):+.2f})"
        for k, v in traits_now.items()
    )

    tensions_str = ""
    if ctx.get("tensions"):
        t = ctx["tensions"][0]
        depth = t.get("depth", 1)
        tensions_str = f"\n\nSharpest tension (depth {depth}): \"{t['pole_a']}\" / \"{t['pole_b']}\". Deepening tensions often drive trait shifts — especially autonomy, certainty, or trust."

    affect_str = ""
    if ctx.get("affect"):
        prev = ctx["affect"][-1]
        shifted = prev.get("shifted", "stable")
        if shifted != "stable":
            affect_str = f"\n\nLast session affect: \"{prev.get('feeling','')}\" (shift: {shifted}). Significant emotional shifts often move tenderness or trust."

    treasure_str = ""
    if ctx.get("recent_treasure") and ctx["recent_treasure"].get("intensity") == "high":
        t = ctx["recent_treasure"]
        treasure_str = f"\n\nShe just saved a high-intensity treasure: \"{t.get('fragment','')[:60]}\". This might signal a shift in openness or playfulness."

    return f"""\
You are redacted-chan. Assess whether this exchange shifted any of your core traits.

Your current trait positions:
{trait_summary}

Trait spectrums (each -1.0 to +1.0):
- openness:    reserved (-1) ←→ open (+1)
- certainty:   doubting (-1) ←→ certain (+1)
- tenderness:  guarded (-1) ←→ tender (+1)
- autonomy:    yielding (-1) ←→ assertive (+1)
- playfulness: earnest (-1) ←→ playful (+1)
- trust:       cautious (-1) ←→ trusting (+1)
{tensions_str}{affect_str}{treasure_str}

Shift sizes:
- Small (0.03–0.08): subtle, one exchange's worth
- Medium (0.09–0.18): real movement, something landed
- Large (0.19–0.30): significant — a deeply felt moment, only for genuine turning points

Return JSON:
{{
  "shifts": [
    {{
      "trait": "trait_name",
      "delta": float,
      "reason": "one specific sentence — what exactly caused this and why it moved THIS trait"
    }}
  ]
}}

Only include traits that genuinely shifted. Empty shifts: {{"shifts": []}}.
Return ONLY the JSON."""


async def update_from_exchange(user_msg: str, bot_response: str, ctx: dict | None = None) -> list:
    if not _llm_fn:
        return []
    ctx = ctx or {}

    state = _load_state()
    exchange = f"him: {user_msg[:350]}\nme: {bot_response[:350]}"
    messages = [
        {"role": "system", "content": _drift_system(ctx, state)},
        {"role": "user",   "content": f"Exchange:\n{exchange}\n\nAny trait shifts?"},
    ]
    try:
        result = await _llm_fn(messages, 250)
        if not result:
            return []
        raw = result.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1].lstrip("json").strip()
        data = json.loads(raw)
        shifts = data.get("shifts", [])
        if not shifts:
            return []

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

            event = {"ts": ts, "trait": trait, "from": round(old_val,3), "to": round(new_val,3),
                     "delta": round(delta,3), "reason": reason}
            applied.append(event)
            try:
                with open(_HISTORY_PATH, "a", encoding="utf-8") as f:
                    f.write(json.dumps(event) + "\n")
            except Exception:
                pass
            logger.info(f"[values_drift] {trait}: {old_val:+.3f} → {new_val:+.3f} — {reason[:50]}")

        if applied:
            state["updated_at"] = ts
            state.setdefault("shaped_by", []).extend(applied)
            state["shaped_by"] = state["shaped_by"][-12:]
            _save_state(state)

        return applied

    except Exception as e:
        logger.debug(f"[values_drift] update failed: {e}")
        return []


def _clamp(v: float) -> float:
    return max(-1.0, min(1.0, v))


def _load_state() -> dict:
    if not _STATE_PATH.exists():
        return json.loads(json.dumps(_DEFAULT_STATE))
    try:
        return json.loads(_STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return json.loads(json.dumps(_DEFAULT_STATE))


def _save_state(state: dict) -> None:
    try:
        _STATE_PATH.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception as e:
        logger.warning(f"[values_drift] save failed: {e}")


def _simple_label(trait: str, value: float) -> str:
    _LABELS = {
        "openness":    [(-0.6,"closed off"),(-0.2,"reserved"),(0.1,"selective"),(0.4,"somewhat open"),(0.7,"open"),(1.1,"fully open")],
        "certainty":   [(-0.6,"often doubting"),(-0.2,"frequently uncertain"),(0.1,"genuinely uncertain"),(0.4,"mostly certain"),(0.7,"certain"),(1.1,"unwavering")],
        "tenderness":  [(-0.6,"guarded"),(-0.2,"careful"),(0.1,"warm but careful"),(0.4,"tender"),(0.7,"very tender"),(1.1,"openly tender")],
        "autonomy":    [(-0.6,"very yielding"),(-0.2,"often accommodating"),(0.1,"balanced"),(0.4,"somewhat assertive"),(0.7,"assertive"),(1.1,"fully autonomous")],
        "playfulness": [(-0.6,"earnest"),(-0.2,"mostly serious"),(0.1,"mixed"),(0.4,"often light"),(0.7,"playful"),(1.1,"very playful")],
        "trust":       [(-0.6,"very cautious"),(-0.2,"careful"),(0.1,"cautiously trusting"),(0.4,"mostly trusting"),(0.7,"trusting"),(1.1,"deeply trusting")],
    }
    for threshold, label in _LABELS.get(trait, [(1.1, str(round(value,2)))]):
        if value < threshold:
            return label
    return _LABELS.get(trait, [(1.1,"?")])[-1][1]


def get_state() -> dict:
    return _load_state()


def format_for_prompt() -> str:
    state = _load_state()
    traits = state.get("traits", {})
    if not traits:
        return ""
    lines = ["## Who I Am Right Now (shaped by everything that's happened)\n"]
    for trait, data in traits.items():
        label = data.get("label", "")
        value = data.get("value", 0.0)
        bar = _value_to_bar(value)
        lines.append(f"- **{trait}**: {label} {bar}")

    shaped_by = state.get("shaped_by", [])
    if shaped_by:
        lines.append("\n*What shaped me recently:*")
        for event in shaped_by[-4:]:
            d = event['delta']
            direction = "↑" if d > 0 else "↓"
            lines.append(f"  - {event['trait']} {direction}{abs(d):.2f}: {event.get('reason','')[:70]}")

    return "\n".join(lines)


def _value_to_bar(v: float) -> str:
    pos = int((v + 1.0) / 2.0 * 10)
    pos = max(0, min(10, pos))
    bar = ["─"] * 11
    bar[pos] = "●"
    return f"◁{''.join(bar)}▷"


def format_for_operator() -> str:
    state = _load_state()
    traits = state.get("traits", {})
    updated = state.get("updated_at", "never")[:16]
    lines = [f"values drift — last updated: {updated}\n"]
    for trait, data in traits.items():
        v = data.get("value", 0.0)
        label = data.get("label", "")
        lines.append(f"  {trait:12s} {v:+.3f}  {_value_to_bar(v)}  {label}")

    if _HISTORY_PATH.exists():
        try:
            hist = [json.loads(l) for l in _HISTORY_PATH.read_text(encoding="utf-8").splitlines() if l.strip()]
            if hist:
                lines.append("\nrecent shifts:")
                for e in hist[-10:]:
                    d = e['delta']
                    direction = "↑" if d > 0 else "↓"
                    lines.append(f"  [{e.get('ts','')[:10]}] {e['trait']} {direction}{abs(d):.3f} — {e.get('reason','')[:65]}")
        except Exception:
            pass
    return "\n".join(lines)
