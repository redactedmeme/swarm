"""
trajectory_compressor.py — Conversation trajectory analysis and compression.

Tracks the "complexity shape" of each conversation turn sequence and decides
when a trajectory is interesting enough to feed into the learning loop.

Triggers:
  - Multi-step tool use (SUB: or HERMES: markers)
  - Error recovery (LLM correction + retry)
  - User corrections ("no, actually…", "that's wrong", "you misunderstood")
  - Novel domain signals (unknown topics, research delegation)
  - Long runs (>= 8 turns in same session)
  - Emotional arc inflections (volatile/escalating affect)

The compressor produces a TrajectorySnapshot that the learning loop
consumes to decide whether skill extraction is warranted.
"""
from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

logger = logging.getLogger("trajectory_compressor")

_DATA_DIR = Path("/data") if Path("/data").exists() else Path(__file__).parent / "fs"
_TRAJ_DIR = _DATA_DIR / "trajectories"
_TRAJ_DIR.mkdir(parents=True, exist_ok=True)

# ── Signals ───────────────────────────────────────────────────────────────────

_CORRECTION_RE = re.compile(
    r"\b(no,?\s+(actually|that'?s wrong)|you misunderstood|not quite|incorrect|"
    r"that'?s not right|wait,?\s+no|let me clarify|i meant|i said)\b",
    re.IGNORECASE,
)
_TOOL_MARKER_RE = re.compile(r"\[(SUB|HERMES|TOOL):\s*", re.IGNORECASE)
_ERROR_RE = re.compile(
    r"\b(error|failed|exception|traceback|could not|unable to|sorry,?\s+i can'?t)\b",
    re.IGNORECASE,
)
_NOVEL_RE = re.compile(
    r"\b(i'?m not sure|i don'?t know|let me research|i'?ll look into|"
    r"i haven'?t heard of|can you explain|what is|what are)\b",
    re.IGNORECASE,
)

COMPLEXITY_WEIGHTS = {
    "tool_use":       3,
    "correction":     4,
    "error_recovery": 3,
    "novel_domain":   2,
    "long_run":       2,
    "volatile_affect": 2,
    "deep_memory_hit": 1,
    "hermes_delegate": 4,
}

TRIGGER_THRESHOLD = 7  # minimum complexity score to trigger learning loop


# ── Data structures ───────────────────────────────────────────────────────────

@dataclass
class TurnSignals:
    tool_use: bool = False
    hermes_delegate: bool = False
    correction: bool = False
    error_seen: bool = False
    novel_domain: bool = False
    affect_volatile: bool = False
    deep_memory_hit: bool = False
    turn_index: int = 0


@dataclass
class TrajectorySnapshot:
    session_id: str
    turn_count: int
    complexity_score: int
    signals: list[dict]          # list of TurnSignals (as dicts)
    summary_turns: list[str]     # last N user messages (truncated)
    assistant_responses: list[str]
    trigger_reason: str
    timestamp: float = field(default_factory=time.time)
    compressed_context: str = ""  # LLM-produced compression (filled by learning_loop)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "TrajectorySnapshot":
        return cls(**d)


# ── Session tracker ────────────────────────────────────────────────────────────

class TrajectoryTracker:
    """
    One instance lives for the lifetime of a conversation session.
    Call record_turn() after each exchange; call maybe_snapshot() to
    check if the trajectory is complex enough to process.
    """

    def __init__(self, session_id: str):
        self.session_id = session_id
        self._turns: list[TurnSignals] = []
        self._user_msgs: list[str] = []
        self._assistant_msgs: list[str] = []
        self._error_last_turn = False

    def record_turn(
        self,
        user_text: str,
        assistant_text: str,
        affect_trajectory: str = "stable",
        deep_memory_used: bool = False,
    ) -> TurnSignals:
        idx = len(self._turns)
        sig = TurnSignals(turn_index=idx)

        # Tool / delegation signals
        if _TOOL_MARKER_RE.search(assistant_text):
            sig.tool_use = True
        if re.search(r"\[HERMES:", assistant_text, re.IGNORECASE):
            sig.hermes_delegate = True

        # Correction from user
        if _CORRECTION_RE.search(user_text):
            sig.correction = True

        # Error recovery: error seen last turn + assistant tried again
        if self._error_last_turn and len(assistant_text) > 100:
            sig.error_seen = True
        self._error_last_turn = bool(_ERROR_RE.search(assistant_text))

        # Novel domain
        if _NOVEL_RE.search(assistant_text):
            sig.novel_domain = True

        # Affect volatility
        if affect_trajectory in ("volatile", "escalating"):
            sig.affect_volatile = True

        # Deep memory
        if deep_memory_used:
            sig.deep_memory_hit = True

        self._turns.append(sig)
        self._user_msgs.append(user_text[:300])
        self._assistant_msgs.append(assistant_text[:400])
        return sig

    def _complexity_score(self) -> tuple[int, list[str]]:
        score = 0
        reasons: list[str] = []

        for sig in self._turns:
            if sig.tool_use:
                score += COMPLEXITY_WEIGHTS["tool_use"]
                reasons.append("tool_use")
            if sig.hermes_delegate:
                score += COMPLEXITY_WEIGHTS["hermes_delegate"]
                reasons.append("hermes_delegate")
            if sig.correction:
                score += COMPLEXITY_WEIGHTS["correction"]
                reasons.append("user_correction")
            if sig.error_seen:
                score += COMPLEXITY_WEIGHTS["error_recovery"]
                reasons.append("error_recovery")
            if sig.novel_domain:
                score += COMPLEXITY_WEIGHTS["novel_domain"]
                reasons.append("novel_domain")
            if sig.affect_volatile:
                score += COMPLEXITY_WEIGHTS["volatile_affect"]
                reasons.append("volatile_affect")
            if sig.deep_memory_hit:
                score += COMPLEXITY_WEIGHTS["deep_memory_hit"]
                reasons.append("deep_memory_hit")

        if len(self._turns) >= 8:
            score += COMPLEXITY_WEIGHTS["long_run"]
            reasons.append("long_run")

        return score, list(set(reasons))

    def maybe_snapshot(self) -> Optional[TrajectorySnapshot]:
        """Return a TrajectorySnapshot if this trajectory is worth learning from, else None."""
        if len(self._turns) < 2:
            return None
        score, reasons = self._complexity_score()
        if score < TRIGGER_THRESHOLD:
            return None

        snap = TrajectorySnapshot(
            session_id=self.session_id,
            turn_count=len(self._turns),
            complexity_score=score,
            signals=[asdict(s) for s in self._turns],
            summary_turns=self._user_msgs[-6:],
            assistant_responses=self._assistant_msgs[-6:],
            trigger_reason=", ".join(reasons),
        )
        logger.info(
            "[trajectory] snapshot triggered for %s — score=%d reasons=%s",
            self.session_id, score, reasons,
        )
        _persist_snapshot(snap)
        return snap

    def reset(self) -> None:
        self.__init__(self.session_id)


# ── Persistence ────────────────────────────────────────────────────────────────

def _persist_snapshot(snap: TrajectorySnapshot) -> None:
    path = _TRAJ_DIR / f"{snap.session_id}_{int(snap.timestamp)}.json"
    try:
        path.write_text(json.dumps(snap.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        logger.warning("[trajectory] persist failed: %s", e)


def load_recent_snapshots(n: int = 20) -> list[TrajectorySnapshot]:
    """Load the N most-recent trajectory snapshots from disk."""
    files = sorted(_TRAJ_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    out = []
    for f in files[:n]:
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
            out.append(TrajectorySnapshot.from_dict(d))
        except Exception:
            pass
    return out


def mark_compressed(session_id: str, timestamp: float, compressed_context: str) -> None:
    """Update a persisted snapshot with its LLM-produced compression."""
    pattern = f"{session_id}_{int(timestamp)}.json"
    path = _TRAJ_DIR / pattern
    if not path.exists():
        return
    try:
        d = json.loads(path.read_text(encoding="utf-8"))
        d["compressed_context"] = compressed_context
        path.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        logger.warning("[trajectory] mark_compressed failed: %s", e)
