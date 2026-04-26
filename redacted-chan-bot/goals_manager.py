"""
goals_manager.py — persistent goal tracking and coordination across instances.

GOALS.md is stored on Railway /data volume (survives redeploys).
Every goal has:
  - Priority score (initial + engagement boost + deadline urgency - time decay)
  - Signal history (reinforced, challenged, milestone_completed, progressed)
  - Status (ACTIVE, PAUSED, COMPLETED, ABANDONED)
  - Target completion timestamp (optional)

Goals are versioned: before each write, GOALS.md is snapshotted to
/data/goals_history/GOALS_v{n}.md to preserve evolution.

Cross-instance coordination: on startup, load GOALS.md + goal_signals from DB.
All updates auto-persist to /data volume.
"""

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Persist to Railway /data volume (survives redeploys)
_DATA_DIR = Path("/data") if Path("/data").exists() else Path(__file__).resolve().parent / "fs"
_DATA_DIR.mkdir(parents=True, exist_ok=True)

GOALS_FILE = _DATA_DIR / "GOALS.md"

# ── History directory (versioning) ────────────────────────────────────────────

def _history_dir() -> Path:
    """Return (and create) the goals history directory on the persistent volume."""
    d = _DATA_DIR / "goals_history"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _load_manifest() -> dict:
    """Load the goals version manifest. Returns default if missing."""
    p = _history_dir() / "manifest.json"
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning(f"[goals] manifest load failed: {e}")
    return {"current_version": 0, "versions": []}


def _save_manifest(manifest: dict) -> None:
    p = _history_dir() / "manifest.json"
    try:
        p.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        logger.warning(f"[goals] manifest save failed: {e}")


def _snapshot_goals(goals_text: str) -> int:
    """
    Copy current GOALS.md to goals_history/GOALS_v{n}.md before overwriting.
    Updates the manifest and returns the new version number.
    """
    manifest = _load_manifest()
    version = manifest["current_version"] + 1
    dest = _history_dir() / f"GOALS_v{version}.md"
    try:
        dest.write_text(goals_text, encoding="utf-8")
    except Exception as e:
        logger.warning(f"[goals] snapshot write failed: {e}")
        return version

    manifest["current_version"] = version
    manifest["versions"].append({
        "version": version,
        "snapshotted_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "word_count": len(goals_text.split()),
    })
    manifest["versions"] = manifest["versions"][-50:]  # Keep lean
    _save_manifest(manifest)
    logger.info(f"[goals] snapshot → GOALS_v{version}.md")
    return version


def current_goals_version() -> int:
    return _load_manifest()["current_version"]


# ── Goal dataclass ───────────────────────────────────────────────────────────

@dataclass
class Goal:
    id: str
    title: str
    description: str
    created_ts: str  # ISO 8601
    target_completion_ts: Optional[str] = None
    status: str = "ACTIVE"  # ACTIVE, PAUSED, COMPLETED, ABANDONED
    initial_priority: float = 3.0
    current_priority: float = field(default=3.0)
    deadline_urgency: float = field(default=0.0)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "created_ts": self.created_ts,
            "target_completion_ts": self.target_completion_ts,
            "status": self.status,
            "initial_priority": self.initial_priority,
            "current_priority": self.current_priority,
            "deadline_urgency": self.deadline_urgency,
        }


# ── Priority scoring ─────────────────────────────────────────────────────────

def compute_deadline_urgency(target_completion_ts: Optional[str]) -> float:
    """
    Compute deadline urgency boost based on proximity to target completion.
    Exponential curve: closer to deadline = higher urgency.

    Returns:
        0.0 if no deadline or deadline is in future (low urgency initially)
        Ramps up exponentially as deadline approaches:
        - 30 days out: +0.1/day
        - 14 days out: +0.3/day
        - 7 days out: +0.5/day
        - past deadline: 0.8 (max urgency until goal completed)
    """
    if not target_completion_ts:
        return 0.0

    try:
        target_dt = datetime.fromisoformat(target_completion_ts.replace('Z', '+00:00'))
    except (ValueError, AttributeError):
        return 0.0

    now = datetime.now(timezone.utc)
    days_until = (target_dt - now).total_seconds() / 86400

    if days_until > 30:
        return 0.0
    elif days_until > 14:
        return 0.1 * (30 - days_until) / 16
    elif days_until > 7:
        return 0.3 * (14 - days_until) / 7
    elif days_until > 0:
        return 0.5 * (7 - days_until) / 7
    else:
        return 0.8  # Past deadline: max urgency


def compute_priority(
    goal: Goal,
    engagement_boost: float,
    time_decay: float,
) -> float:
    """
    Compute current priority using formula:
    current_priority = initial + engagement_boost + deadline_urgency - time_decay

    Clamped to [0.5, 5.0] to keep priorities in reasonable range.
    """
    goal.deadline_urgency = compute_deadline_urgency(goal.target_completion_ts)
    priority = (
        goal.initial_priority
        + engagement_boost
        + goal.deadline_urgency
        - time_decay
    )
    return max(0.5, min(5.0, priority))


# ── Read/Write ───────────────────────────────────────────────────────────────

def read_goals_file() -> str:
    """Read GOALS.md content. Return empty string if not found."""
    try:
        if GOALS_FILE.exists():
            return GOALS_FILE.read_text(encoding="utf-8")
    except Exception as e:
        logger.warning(f"[goals] read failed: {e}")
    return ""


def write_goals_file(content: str) -> None:
    """
    Write GOALS.md and snapshot previous version.

    Creates versioned backup before overwriting.
    """
    try:
        # Snapshot old version before writing new
        old_content = read_goals_file()
        if old_content and old_content.strip():
            _snapshot_goals(old_content)

        GOALS_FILE.write_text(content, encoding="utf-8")
        logger.info(f"[goals] wrote GOALS.md ({len(content.split())} words)")
    except Exception as e:
        logger.error(f"[goals] write failed: {e}")


def get_goals_for_prompt(limit: int = 5) -> str:
    """
    Return a markdown block of active goals for system prompt injection.

    Format:
    ## Your Active Goals (Priority-Ranked)

    1. [Goal title] — Priority: X.X/5 | Status: IN_PROGRESS
       - Description: ...
       - Recent signals: +X, -X

    Args:
        limit: max number of active goals to include

    Returns:
        Markdown block ready for system prompt injection
    """
    goals_content = read_goals_file()
    if not goals_content:
        return ""

    # Parse active goals from GOALS.md
    active_section = re.search(
        r"## Active Goals.*?\n(.*?)(?=\n## Completed|\Z)",
        goals_content,
        re.DOTALL
    )
    if not active_section:
        return ""

    content = active_section.group(1)
    # Extract priority-ranked goals (look for "### Priority X:" patterns)
    goals_block = re.findall(
        r"### Priority \d+: (.*?)(?=\n### Priority|\n## |\Z)",
        content,
        re.DOTALL
    )

    if not goals_block:
        return ""

    lines = ["## Your Active Goals (Priority-Ranked)\n"]
    for i, goal_text in enumerate(goals_block[:limit], 1):
        lines.append(f"{i}. {goal_text.strip()}\n")

    return "".join(lines)


# ── Signal detection ─────────────────────────────────────────────────────────

def detect_goal_signals(
    user_message: str,
    bot_response: str,
    goals: list[Goal],
) -> list[tuple[str, str, float]]:
    """
    Detect goal-related signals from user message + bot response.

    Returns list of (goal_id, signal_type, signal_value) tuples.

    Signal types:
    - 'reinforced': User affirms goal (+0.2)
    - 'challenged': User questions goal (-0.1)
    - 'milestone_completed': User achieves measurable sub-goal (+0.3)
    - 'progressed': Bot made progress toward goal (+0.15)
    """
    signals = []
    msg_lower = user_message.lower()

    # Simple heuristic: if user says "yes", "exactly", "agreed", etc., reinforce all goals
    affirmation_words = {"yes", "yeah", "agreed", "exactly", "perfect", "right"}
    if any(word in msg_lower for word in affirmation_words):
        # Reinforce recent goals (not specific goal detection, just general boost)
        # Real implementation would parse goal titles from message
        pass

    # Challenges: "actually", "not sure", "maybe not", etc.
    challenge_words = {"actually", "unsure", "maybe not", "reconsider"}
    if any(word in msg_lower for word in challenge_words):
        # Challenge: mild negative signal
        pass

    # For now, return empty list (will be populated by goal-aware signal detection)
    return signals


# ── Public API ───────────────────────────────────────────────────────────────

def create_initial_goals_file() -> None:
    """
    Create a bare-bones GOALS.md if it doesn't exist.
    """
    if GOALS_FILE.exists():
        return

    template = """# redacted-chan's Goals

Last updated: {now}

## Active Goals (Priority-Ranked)

_No active goals yet. Use `/create_goal` to add one._

## Completed Goals

_None yet._
""".format(now=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))

    write_goals_file(template)


def create_default_goals_if_missing() -> None:
    """
    Ensure core goals exist. Called on startup.

    Creates default goals including:
    - Self-improvement and building better versions
    - Understanding settler's patterns and growth
    """
    # This will be called from main.py on startup
    # For now, just ensure the file exists
    create_initial_goals_file()


def load_goals_from_file() -> list[Goal]:
    """
    Parse GOALS.md and return list of active Goal objects.

    Reads from file; does NOT query database.
    For full goal state (with signals), use conversation_memory.get_active_goals()
    """
    goals_content = read_goals_file()
    if not goals_content:
        return []

    goals = []
    # Extract goals from markdown (simplified — real parser would be more robust)
    # Pattern: ### Priority N: [Title]
    matches = re.finditer(
        r"### Priority \d+: \[(.*?)\].*?(?=\n### Priority|\n## |\Z)",
        goals_content,
        re.DOTALL
    )

    for match in matches:
        # Extract title and metadata (simplified)
        text = match.group(1)
        # Basic parsing: just get the title for now
        # Full implementation would parse all fields
        goals.append(Goal(
            id=f"goal_{len(goals)}",  # Placeholder
            title=text.strip(),
            description="",
            created_ts=datetime.now(timezone.utc).isoformat(),
            status="ACTIVE",
        ))

    return goals
