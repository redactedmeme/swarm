# redacted-chan-bot/redis_state_cache.py
"""
Redis momentum cache — persistent emotional state across redeploys.

Snapshots her current emotional bundle to Redis every N minutes.
On startup, load_momentum() pre-warms in-memory modules from the snapshot
so she doesn't wake up cold — she already has her mood, arc, anticipation,
and phi score from before the restart.

Key: swarm:chan:momentum  (TTL: 72h)

Bundle contents:
  mood_state        — mood_drift output (mood, modifier, intensity)
  session_state     — session_continuity snapshot (gap_hours, next_thread, etc.)
  anticipation      — silence state + last_seen timestamp
  phi               — current phi score (0–1)
  arc_sessions      — last 10 turns per user_id from conversation_affect_tracker
  conviction        — latest formed conviction
  affect            — conversation_affect state
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_REDIS_KEY   = "swarm:chan:momentum"
_TTL_SEC     = 86400 * 3  # 72h — survives weekend deploys
_DATA_DIR    = Path("/data") if Path("/data").exists() else Path(__file__).parent / "fs"


def _get_redis():
    try:
        import swarm_inbox
        return swarm_inbox._get_redis()
    except Exception:
        return None


# ── Save ──────────────────────────────────────────────────────────────────────

def save_momentum() -> bool:
    """
    Snapshot current emotional state bundle to Redis.
    Safe to call frequently — each key is read independently and failures
    are silently ignored so one broken module never blocks the rest.
    """
    r = _get_redis()
    if not r:
        return False

    bundle: dict = {"saved_at": time.time()}

    # Mood state (mood_drift output)
    try:
        mood_path = _DATA_DIR / "mood_state.json"
        if mood_path.exists():
            bundle["mood_state"] = json.loads(mood_path.read_text(encoding="utf-8"))
    except Exception:
        pass

    # Session continuity
    try:
        import session_continuity as scon
        bundle["session_state"] = scon._load()
    except Exception:
        pass

    # Anticipation state
    try:
        import anticipation_state as ant
        bundle["anticipation"] = {
            "state":     ant.get_state(),
            "last_seen": getattr(ant, "_last_seen", None),
        }
    except Exception:
        pass

    # Phi score
    try:
        import phi_tracker as pt
        bundle["phi"] = pt.get_score()
    except Exception:
        pass

    # Latest conviction
    try:
        import conviction
        latest = conviction.get_latest()
        if latest:
            bundle["conviction"] = latest
    except Exception:
        pass

    # Conversation affect (cross-session baseline)
    try:
        import conversation_affect as caff
        state_path = _DATA_DIR / "conversation_affect.json"
        if state_path.exists():
            bundle["affect"] = json.loads(state_path.read_text(encoding="utf-8"))
    except Exception:
        pass

    # Within-conversation arc tracker (all active user sessions)
    try:
        import conversation_affect_tracker as cat
        arc_data = {}
        for uid, session in cat._sessions.items():
            # Only save if the session has recent turns (< 2h old)
            if session.turns and time.time() - session.turns[-1]["ts"] < 7200:
                arc_data[str(uid)] = session.turns[-10:]
        if arc_data:
            bundle["arc_sessions"] = arc_data
    except Exception:
        pass

    try:
        r.setex(_REDIS_KEY, _TTL_SEC, json.dumps(bundle, ensure_ascii=False))
        logger.debug("[redis_state_cache] momentum saved — %d keys", len(bundle))
        return True
    except Exception as e:
        logger.warning("[redis_state_cache] save failed: %s", e)
        return False


# ── Load ──────────────────────────────────────────────────────────────────────

def load_momentum() -> bool:
    """
    Pre-warm in-memory modules from Redis snapshot on startup.
    Returns True if a snapshot was found and applied, False otherwise.
    """
    r = _get_redis()
    if not r:
        return False

    try:
        raw = r.get(_REDIS_KEY)
    except Exception as e:
        logger.warning("[redis_state_cache] Redis read failed: %s", e)
        return False

    if not raw:
        logger.info("[redis_state_cache] no momentum snapshot found")
        return False

    try:
        bundle = json.loads(raw)
    except Exception:
        return False

    saved_at = bundle.get("saved_at", 0)
    age_min  = (time.time() - saved_at) / 60
    logger.info("[redis_state_cache] loading momentum snapshot (age: %.0f min)", age_min)

    restored = []

    # Mood state — write to file if missing or stale
    try:
        if "mood_state" in bundle:
            mood_path = _DATA_DIR / "mood_state.json"
            if not mood_path.exists():
                mood_path.write_text(json.dumps(bundle["mood_state"], ensure_ascii=False),
                                     encoding="utf-8")
                restored.append("mood_state")
    except Exception:
        pass

    # Anticipation — restore last_seen timestamp so silence clock is correct
    try:
        if "anticipation" in bundle:
            import anticipation_state as ant
            last_seen = bundle["anticipation"].get("last_seen")
            if last_seen and not getattr(ant, "_last_seen", None):
                ant._last_seen = last_seen
                restored.append("anticipation")
    except Exception:
        pass

    # Arc tracker — restore in-progress sessions
    try:
        if "arc_sessions" in bundle:
            import conversation_affect_tracker as cat
            for uid_str, turns in bundle["arc_sessions"].items():
                uid = int(uid_str)
                if uid not in cat._sessions:
                    s = cat._SessionState()
                    # Adjust timestamps so gap detection works correctly
                    # (turns happened before the restart — keep their original ts)
                    s.turns = turns
                    cat._sessions[uid] = s
            if bundle["arc_sessions"]:
                restored.append(f"arc({len(bundle['arc_sessions'])} users)")
    except Exception:
        pass

    # Session continuity — restore next_thread if missing from file
    try:
        if "session_state" in bundle:
            import session_continuity as scon
            current = scon._load()
            if not current.get("next_thread") and bundle["session_state"].get("next_thread"):
                current["next_thread"] = bundle["session_state"]["next_thread"]
                scon._save(current)
                restored.append("next_thread")
    except Exception:
        pass

    if restored:
        logger.info("[redis_state_cache] restored: %s", ", ".join(restored))
    return True


def get_snapshot_age_minutes() -> Optional[float]:
    """Return age of the cached snapshot in minutes, or None if no cache."""
    r = _get_redis()
    if not r:
        return None
    try:
        raw = r.get(_REDIS_KEY)
        if not raw:
            return None
        bundle = json.loads(raw)
        return (time.time() - bundle.get("saved_at", 0)) / 60
    except Exception:
        return None
