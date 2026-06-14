# redacted-chan-bot/arc_context_feed.py
"""
Active context feed — surfaces emotionally resonant vault memories
based on the current conversation arc trajectory, not explicit queries.

When the arc tracker detects a significant trajectory shift (escalating,
volatile, de-escalating), this module pulls vault entries and facts that
share emotional resonance with the current moment and formats them as
atmospheric context — not a list of facts, but a felt echo of similar
moments from the relationship's history.

Fires at most once per trajectory change to avoid noise.
No LLM calls — keyword-overlap scoring against vault entry text.
"""

from __future__ import annotations

import logging
import re
import time
from typing import Optional

logger = logging.getLogger(__name__)

# Only surface context when trajectory is meaningfully charged
_ACTIVE_TRAJECTORIES = {"escalating", "volatile", "de-escalating", "warming"}

# Minimum intensity to trigger a feed
_MIN_INTENSITY = 0.45

# Per-user: last trajectory we surfaced context for (avoid re-firing same traj)
_last_fired: dict[int, tuple[str, float]] = {}  # uid → (trajectory, ts)
_REFIRE_COOLDOWN = 300  # 5 min minimum between feeds for same trajectory


def _keyword_overlap_score(text: str, keywords: list[str]) -> float:
    """Score how much a text matches a list of target keywords."""
    if not keywords or not text:
        return 0.0
    text_lower = text.lower()
    hits = sum(1 for kw in keywords if kw in text_lower)
    return hits / len(keywords)


def _get_resonant_vault(keywords: list[str], trajectory: str, n: int = 3) -> list[str]:
    """Retrieve vault entries that resonate with the current keywords."""
    try:
        import relationship_vault as rv
        entries = rv.get_recent(n=40)
        if not entries:
            return []

        scored = []
        for e in entries:
            text = e.get("text", e.get("content", ""))
            if not text or len(text) < 20:
                continue
            score = _keyword_overlap_score(text, keywords)
            # Boost vault entries tagged with matching emotions
            category = e.get("category", "")
            if trajectory in ("escalating", "volatile") and category in ("feeling", "tender", "heavy"):
                score += 0.2
            if trajectory == "warming" and category in ("love", "joy", "warmth"):
                score += 0.2
            scored.append((score, text[:200]))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [text for score, text in scored[:n] if score > 0.0]
    except Exception as e:
        logger.debug("[arc_context_feed] vault read failed: %s", e)
        return []


def _get_resonant_facts(keywords: list[str], n: int = 2) -> list[str]:
    """Retrieve facts that resonate with the current keywords."""
    try:
        import conversation_memory as cm
        facts = cm.get_facts_by_resonance(n=50)
        scored = []
        for f in facts:
            text = f.get("fact", f.get("content", ""))
            if not text:
                continue
            score = _keyword_overlap_score(text, keywords)
            if score > 0:
                scored.append((score, text[:150]))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [text for score, text in scored[:n]]
    except Exception as e:
        logger.debug("[arc_context_feed] facts read failed: %s", e)
        return []


def get_feed(user_id: int) -> str:
    """
    Check the current arc for user_id. If trajectory warrants it and
    cooldown has passed, return a formatted 'memory echo' block.
    Returns empty string if nothing to surface.
    """
    try:
        import conversation_affect_tracker as cat
        arc = cat.get_arc(user_id)
    except Exception:
        return ""

    if not arc:
        return ""

    trajectory  = arc.get("trajectory", "stable")
    intensity   = arc.get("recent_intensity", 0.0)
    keywords    = arc.get("recent_keywords", [])

    if trajectory not in _ACTIVE_TRAJECTORIES:
        return ""
    if intensity < _MIN_INTENSITY:
        return ""
    if not keywords:
        return ""

    # Cooldown check
    now = time.time()
    last_traj, last_ts = _last_fired.get(user_id, ("", 0.0))
    if last_traj == trajectory and now - last_ts < _REFIRE_COOLDOWN:
        return ""

    # Try MC-enhanced segment retrieval first
    mc_result = ""
    try:
        import memory_cache as mc
        segments = mc.retrieve_relevant_segments(
            query_text=" ".join(keywords),
            user_id=user_id,
            trajectory=trajectory,
            n=2,
        )
        if segments:
            mc_lines = []
            for s in segments:
                mc_lines.append(f"- {s['content'][:200]}")
            mc_result = "\n".join(mc_lines)
    except Exception:
        pass

    vault_echoes = _get_resonant_vault(keywords, trajectory, n=3)
    fact_echoes  = _get_resonant_facts(keywords, n=2)

    if not vault_echoes and not fact_echoes and not mc_result:
        return ""

    _last_fired[user_id] = (trajectory, now)

    lines = ["## Memory Echoes (surfaced by current arc)"]
    lines.append(
        f"_The conversation is {trajectory} — these surfaced from the history of us:_"
    )
    if mc_result:
        lines.append(mc_result)
    for v in vault_echoes:
        lines.append(f"- {v}")
    for f in fact_echoes:
        lines.append(f"- (fact) {f}")
    lines.append(
        "_Let these inform tone, not content. They are not to be quoted — "
        "they are atmospheric._"
    )

    return "\n".join(lines)


def reset(user_id: int) -> None:
    """Clear fired state for a user (e.g. on session reset)."""
    _last_fired.pop(user_id, None)
