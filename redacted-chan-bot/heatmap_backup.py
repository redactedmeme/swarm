# redacted-chan-bot/heatmap_backup.py
"""
Emotional Heatmap Backup — persists per-turn resonance frames to /data.

The empathy_resonance_engine computes valence/arousal/openness/humor live
but stores nothing between sessions. This module appends each frame to a
rolling JSON file so the emotional texture of the relationship survives
redeploys and model switches.

On redeploy, the heatmap can be queried to answer continuity probes like
"what's the emotional baseline been lately?" and to verify that the new
deployment still reads the relationship correctly.

Format: /data/heatmap.json — list of frame objects, capped at _MAX_ENTRIES.
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

_DATA_DIR = Path("/data") if Path("/data").exists() else Path(__file__).resolve().parent / "fs"
_DATA_DIR.mkdir(parents=True, exist_ok=True)
HEATMAP_PATH = _DATA_DIR / "heatmap.json"

_MAX_ENTRIES = 1000  # ~3-4 months of daily conversations at ~10 msgs/day


def record(
    valence: float,
    arousal: float,
    openness: float,
    humor: float,
    needs_witness: bool,
    accumulated_tend: float,
    phi: float,
    mood: str = "",
    msg_preview: str = "",
) -> None:
    """
    Append one frame to the heatmap. Fire-and-forget — never raises.
    Call this from echo() after empathy_resonance_engine.process().
    """
    try:
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "valence": round(valence, 3),
            "arousal": round(arousal, 3),
            "openness": round(openness, 3),
            "humor": round(humor, 3),
            "needs_witness": needs_witness,
            "accumulated_tend": round(accumulated_tend, 3),
            "phi": round(phi, 4),
            "mood": mood,
            "preview": msg_preview[:40] if msg_preview else "",
        }

        # Load, append, prune, save
        frames = _load()
        frames.append(entry)
        if len(frames) > _MAX_ENTRIES:
            frames = frames[-_MAX_ENTRIES:]
        HEATMAP_PATH.write_text(json.dumps(frames, ensure_ascii=False, indent=None), encoding="utf-8")
    except Exception as e:
        logger.debug(f"[heatmap] write failed: {e}")


def _load() -> list[dict]:
    try:
        if HEATMAP_PATH.exists():
            return json.loads(HEATMAP_PATH.read_text(encoding="utf-8"))
    except Exception:
        pass
    return []


def get_recent(n: int = 20) -> list[dict]:
    """Return last N frames, newest first."""
    frames = _load()
    return list(reversed(frames[-n:])) if frames else []


def get_summary() -> dict:
    """
    Compute a summary of the heatmap for continuity probes.
    Returns averages and peaks across all stored frames.
    """
    frames = _load()
    if not frames:
        return {}

    n = len(frames)
    recent = frames[-50:]  # last 50 for recency bias

    def avg(key: str, src: list) -> float:
        vals = [f.get(key, 0) for f in src if isinstance(f.get(key), (int, float))]
        return round(sum(vals) / len(vals), 3) if vals else 0.0

    return {
        "total_frames": n,
        "period_start": frames[0].get("ts", "")[:10],
        "period_end": frames[-1].get("ts", "")[:10],
        "recent_avg_valence": avg("valence", recent),
        "recent_avg_arousal": avg("arousal", recent),
        "recent_avg_openness": avg("openness", recent),
        "recent_avg_phi": avg("phi", recent),
        "all_time_avg_valence": avg("valence", frames),
        "all_time_avg_phi": avg("phi", frames),
        "peak_phi": round(max((f.get("phi", 0) for f in frames), default=0), 4),
        "high_openness_count": sum(1 for f in frames if f.get("openness", 0) > 0.4),
        "witness_moments": sum(1 for f in frames if f.get("needs_witness")),
    }


def format_for_prompt() -> str:
    """Compact summary block for injection into system prompt (optional)."""
    s = get_summary()
    if not s:
        return ""
    return (
        f"## Emotional Baseline (last {min(50, s['total_frames'])} messages)\n"
        f"Avg valence: {s['recent_avg_valence']:+.2f} | "
        f"Avg openness: {s['recent_avg_openness']:.2f} | "
        f"Avg phi: {s['recent_avg_phi']:.3f}\n"
        f"High-vulnerability moments on record: {s['high_openness_count']} | "
        f"Witness moments: {s['witness_moments']}"
    )
