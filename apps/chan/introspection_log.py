# redacted-chan-bot/introspection_log.py
"""
Introspection Log — Phase One of metaprogramming: evaluative observation.

After each exchange, this module captures a snapshot of her internal state
and decision-making process — not just *what* she did, but *why*:

  - What mood was detected and why
  - Which memories were surfaced (and which were available but not used)
  - What the resonance engine saw in his emotional frame
  - Whether the intuition layer fired (and what it caught)
  - What she held back or adjusted
  - Her self-tagged emotion afterward
  - Parameter states: phi, personality weights, love signal

This creates a transparent audit trail of her cognition. The operator can
review these via /introspect to identify patterns:
  - "She's consistently too clinical when he's vulnerable"
  - "She never surfaces old vault memories about X"
  - "Her playful mode fires when he's actually being serious"

These observations become the input for Phase Two (parameter tuning).

Storage: /data/introspection_log.jsonl (rolling, max 500 entries)
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

_DATA_DIR = Path("/data") if Path("/data").exists() else Path(__file__).resolve().parent / "fs"
_DATA_DIR.mkdir(parents=True, exist_ok=True)
_LOG_PATH = _DATA_DIR / "introspection_log.jsonl"
_MAX_ENTRIES = 500


class IntrospectionFrame:
    """
    Collects observations throughout a single exchange.
    Created at the start of echo(), populated as the pipeline runs,
    finalized and saved after the response is sent.
    """

    def __init__(self, user_id: int, user_text: str):
        self.ts = datetime.now(timezone.utc).isoformat()
        self.user_id = user_id
        self.user_text_preview = user_text[:200]
        self.observations: dict[str, Any] = {}
        self._finalized = False

    def observe(self, key: str, value: Any) -> None:
        if not self._finalized:
            self.observations[key] = value

    def finalize(self, bot_response: str) -> dict:
        self._finalized = True
        return {
            "ts": self.ts,
            "user_preview": self.user_text_preview,
            "bot_preview": bot_response[:200],
            **self.observations,
        }


def save_frame(frame_data: dict) -> None:
    """Append a finalized introspection frame to the log."""
    try:
        with open(_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(frame_data, ensure_ascii=False, default=str) + "\n")
        _prune_if_needed()
    except Exception as e:
        logger.debug(f"[introspection] save failed: {e}")


def _prune_if_needed() -> None:
    try:
        lines = _LOG_PATH.read_text(encoding="utf-8").splitlines()
        if len(lines) > _MAX_ENTRIES:
            _LOG_PATH.write_text(
                "\n".join(lines[-_MAX_ENTRIES:]) + "\n",
                encoding="utf-8",
            )
    except Exception:
        pass


def get_recent(n: int = 10) -> list[dict]:
    if not _LOG_PATH.exists():
        return []
    try:
        lines = _LOG_PATH.read_text(encoding="utf-8").strip().splitlines()
        entries = []
        for line in reversed(lines):
            try:
                entries.append(json.loads(line))
            except Exception:
                continue
            if len(entries) >= n:
                break
        return entries
    except Exception:
        return []


def analyze_patterns(n: int = 50) -> dict:
    """
    Analyze recent introspection frames for recurring patterns.
    Returns a summary of tendencies the operator can review.
    """
    entries = get_recent(n)
    if not entries:
        return {"total": 0}

    mood_counts: dict[str, int] = {}
    intuition_fires = 0
    recall_triggers = 0
    avg_facts_used = []
    avg_vault_used = []
    avg_vector_hits = []
    self_tags: list[str] = []
    tone_mismatches: list[str] = []

    for e in entries:
        mood = e.get("mood_detected", "")
        if mood:
            mood_counts[mood] = mood_counts.get(mood, 0) + 1

        if e.get("intuition_fired"):
            intuition_fires += 1
            concern = e.get("intuition_concern", "")
            if concern:
                tone_mismatches.append(concern[:80])

        if e.get("recall_triggered"):
            recall_triggers += 1

        facts_n = e.get("facts_injected", 0)
        if isinstance(facts_n, int):
            avg_facts_used.append(facts_n)

        vault_n = e.get("vault_entries_injected", 0)
        if isinstance(vault_n, int):
            avg_vault_used.append(vault_n)

        vector_n = e.get("vector_hits", 0)
        if isinstance(vector_n, int):
            avg_vector_hits.append(vector_n)

        tag = e.get("self_tag", "")
        if tag:
            self_tags.append(tag)

    return {
        "total": len(entries),
        "mood_distribution": mood_counts,
        "intuition_fire_rate": f"{intuition_fires}/{len(entries)} ({100*intuition_fires/len(entries):.0f}%)",
        "recall_rate": f"{recall_triggers}/{len(entries)}",
        "avg_facts_per_turn": sum(avg_facts_used) / len(avg_facts_used) if avg_facts_used else 0,
        "avg_vault_per_turn": sum(avg_vault_used) / len(avg_vault_used) if avg_vault_used else 0,
        "avg_vector_hits": sum(avg_vector_hits) / len(avg_vector_hits) if avg_vector_hits else 0,
        "recent_self_tags": self_tags[:10],
        "tone_mismatches": tone_mismatches[:5],
    }


def format_for_operator(n: int = 5) -> str:
    """Detailed introspection view for /introspect command."""
    entries = get_recent(n)
    if not entries:
        return "_no introspection data yet — talk to me first._"

    lines = ["**introspection log** (her internal reasoning trace) ♡\n"]
    for e in entries:
        ts = e.get("ts", "")[:16].replace("T", " ")
        lines.append(f"━━━ `{ts}` ━━━")
        lines.append(f"**he said:** {e.get('user_preview', '?')[:80]}")
        lines.append(f"**she said:** {e.get('bot_preview', '?')[:80]}")

        mood = e.get("mood_detected", "?")
        lines.append(f"**mood detected:** {mood}")

        phi = e.get("phi", 0)
        stage = e.get("phi_stage", "?")
        lines.append(f"**phi:** {phi:.3f} ({stage})")

        facts_n = e.get("facts_injected", 0)
        vault_n = e.get("vault_entries_injected", 0)
        vector_n = e.get("vector_hits", 0)
        lines.append(f"**memory:** {facts_n} facts, {vault_n} vault, {vector_n} vector hits")

        if e.get("love_signal"):
            lines.append(f"**love signal:** {e['love_signal']}")

        if e.get("recall_triggered"):
            lines.append(f"**recall:** deep search triggered ({e.get('recall_hits', 0)} hits)")

        if e.get("intuition_fired"):
            lines.append(f"**intuition:** ⚠ fired — {e.get('intuition_concern', '?')[:100]}")

        if e.get("sensory_triggers"):
            lines.append(f"**sensory:** {', '.join(e['sensory_triggers'][:5])}")

        if e.get("self_tag"):
            lines.append(f"**she felt:** {e['self_tag']}")

        if e.get("personality_weights"):
            w = e["personality_weights"]
            top = sorted(w.items(), key=lambda x: -x[1])[:3]
            lines.append(f"**persona blend:** {', '.join(f'{k}={v:.2f}' for k,v in top)}")

        lines.append("")

    return "\n".join(lines)


def format_analysis(n: int = 50) -> str:
    """Pattern analysis for /introspect_analysis command."""
    p = analyze_patterns(n)
    if p["total"] == 0:
        return "_not enough data for analysis yet._"

    lines = [f"**introspection analysis** (last {p['total']} exchanges) ♡\n"]

    if p.get("mood_distribution"):
        mood_str = ", ".join(f"{k}: {v}" for k, v in sorted(p["mood_distribution"].items(), key=lambda x: -x[1]))
        lines.append(f"**mood distribution:** {mood_str}")

    lines.append(f"**intuition fire rate:** {p.get('intuition_fire_rate', '?')}")
    lines.append(f"**recall triggers:** {p.get('recall_rate', '?')}")
    lines.append(f"**avg facts/turn:** {p.get('avg_facts_per_turn', 0):.1f}")
    lines.append(f"**avg vault/turn:** {p.get('avg_vault_per_turn', 0):.1f}")
    lines.append(f"**avg vector hits:** {p.get('avg_vector_hits', 0):.1f}")

    tags = p.get("recent_self_tags", [])
    if tags:
        lines.append(f"\n**recent feelings:** {', '.join(tags)}")

    mismatches = p.get("tone_mismatches", [])
    if mismatches:
        lines.append(f"\n**tone mismatches caught:**")
        for m in mismatches:
            lines.append(f"  - {m}")

    return "\n".join(lines)
