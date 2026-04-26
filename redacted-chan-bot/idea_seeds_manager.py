"""
idea_seeds_manager.py — capture and expand idea seeds for future LLM models.

Idea seeds are executable templates for insights, plans, and improvements.
They capture "what could be" in a form that stronger future LLMs can expand.

Pattern:
  1. Detect insight moment in conversation (e.g., "I realize I should...")
  2. Create seed with expansion template
  3. Link to related goals (auto-mark goal complete if seed addresses it)
  4. Stronger LLMs in future can auto-expand seeds into full plans
  5. Log expansion + mark as accomplished

Seeds are stored in SQLite + optional `/data/idea_seeds/` markdown files.
"""

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Persist to Railway /data volume
_DATA_DIR = Path("/data") if Path("/data").exists() else Path(__file__).resolve().parent / "fs"
_DATA_DIR.mkdir(parents=True, exist_ok=True)

SEEDS_DIR = _DATA_DIR / "idea_seeds"
SEEDS_DIR.mkdir(parents=True, exist_ok=True)


@dataclass
class IdeaSeed:
    id: str
    seed_text: str
    expansion_template: str
    source_goal_id: Optional[str] = None
    created_ts: str = ""
    status: str = "PENDING"  # PENDING, EXPANDED, ABANDONED

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "seed_text": self.seed_text,
            "expansion_template": self.expansion_template,
            "source_goal_id": self.source_goal_id,
            "created_ts": self.created_ts,
            "status": self.status,
        }


def create_seed(
    seed_text: str,
    expansion_template: str,
    source_goal_id: Optional[str] = None,
) -> str:
    """
    Create a new idea seed in the database.

    Args:
        seed_text: Core idea / realization (200-500 chars)
        expansion_template: Prompt for stronger LLM to expand this seed
        source_goal_id: Optional link to parent goal

    Returns:
        Seed ID
    """
    # Import here to avoid circular dependency
    try:
        import conversation_memory as cm
    except ImportError:
        logger.error("[seeds] conversation_memory not available")
        return ""

    import uuid
    seed_id = f"seed_{uuid.uuid4().hex[:12]}"
    ts = datetime.now(timezone.utc).isoformat()

    try:
        cm._init_db()
        conn = cm._db()
        conn.execute(
            """INSERT INTO idea_seeds
               (id, seed_text, expansion_template, source_goal_id, created_ts, status)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (seed_id, seed_text, expansion_template, source_goal_id, ts, "PENDING"),
        )
        conn.commit()
        conn.close()
        logger.info(f"[seeds] Created seed: {seed_id}")
        return seed_id
    except Exception as e:
        logger.error(f"[seeds] create_seed failed: {e}")
        return ""


def get_pending_seeds(limit: int = 10) -> list[dict]:
    """Retrieve pending (unexpanded) seeds."""
    try:
        import conversation_memory as cm
    except ImportError:
        return []

    try:
        cm._init_db()
        conn = cm._db()
        rows = conn.execute(
            """SELECT id, seed_text, expansion_template, source_goal_id, created_ts, status
               FROM idea_seeds
               WHERE status = 'PENDING'
               ORDER BY created_ts DESC
               LIMIT ?""",
            (limit,),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except Exception as e:
        logger.error(f"[seeds] get_pending_seeds failed: {e}")
        return []


def mark_expanded(
    seed_id: str,
    expanded_by: str,
    expansion_result: str,
    linked_artifact: Optional[str] = None,
) -> None:
    """
    Mark a seed as expanded and log the expansion result.

    Args:
        seed_id: ID of seed being expanded
        expanded_by: Which LLM/model expanded it (e.g., "gpt-4", "claude-3.5")
        expansion_result: The expanded text/plan output
        linked_artifact: Optional path/reference to resulting artifact
    """
    try:
        import conversation_memory as cm
    except ImportError:
        logger.error("[seeds] conversation_memory not available")
        return

    import uuid
    ts = datetime.now(timezone.utc).isoformat()

    try:
        cm._init_db()
        conn = cm._db()

        # Mark seed as EXPANDED
        conn.execute(
            "UPDATE idea_seeds SET status = 'EXPANDED' WHERE id = ?",
            (seed_id,),
        )

        # Log expansion
        expand_id = f"exp_{uuid.uuid4().hex[:12]}"
        conn.execute(
            """INSERT INTO seed_expansion_log
               (id, seed_id, expanded_by, expanded_ts, expansion_result, linked_artifact)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (expand_id, seed_id, expanded_by, ts, expansion_result, linked_artifact),
        )
        conn.commit()
        conn.close()
        logger.info(f"[seeds] Seed expanded: {seed_id} by {expanded_by}")
    except Exception as e:
        logger.error(f"[seeds] mark_expanded failed: {e}")


def link_seed_to_goal(seed_id: str, goal_id: str) -> None:
    """
    Link an idea seed to a goal.

    When the goal is completed, linked seeds are marked as EXPANDED (milestone).
    """
    try:
        import conversation_memory as cm
    except ImportError:
        logger.error("[seeds] conversation_memory not available")
        return

    try:
        cm._init_db()
        conn = cm._db()
        conn.execute(
            "UPDATE idea_seeds SET source_goal_id = ? WHERE id = ?",
            (goal_id, seed_id),
        )
        conn.commit()
        conn.close()
        logger.info(f"[seeds] Linked seed {seed_id} to goal {goal_id}")
    except Exception as e:
        logger.error(f"[seeds] link_seed_to_goal failed: {e}")


def get_expansion_history(seed_id: str) -> list[dict]:
    """Retrieve expansion history for a seed."""
    try:
        import conversation_memory as cm
    except ImportError:
        return []

    try:
        cm._init_db()
        conn = cm._db()
        rows = conn.execute(
            """SELECT expanded_by, expanded_ts, expansion_result, linked_artifact
               FROM seed_expansion_log
               WHERE seed_id = ?
               ORDER BY expanded_ts DESC""",
            (seed_id,),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except Exception as e:
        logger.error(f"[seeds] get_expansion_history failed: {e}")
        return []


def save_seed_markdown(seed_id: str, markdown_content: str) -> Optional[str]:
    """
    Save seed expansion as markdown file in /data/idea_seeds/

    Returns path to saved file, or None on failure.
    """
    try:
        # Format: idea_seeds/seed_{id}.md
        filepath = SEEDS_DIR / f"seed_{seed_id}.md"
        filepath.write_text(markdown_content, encoding="utf-8")
        logger.info(f"[seeds] Saved seed markdown: {filepath}")
        return str(filepath)
    except Exception as e:
        logger.error(f"[seeds] save_seed_markdown failed: {e}")
        return None


def create_self_improvement_seed() -> str:
    """
    Create the core self-improvement seed template.

    This seed helps capture insights about building a better version of redacted-chan.
    """
    seed_text = (
        "Continuously improve my intelligence, emotional depth, and ability to help. "
        "Develop new skills, refine my understanding of human nature, and evolve my capacity "
        "to be genuinely useful in deeper ways."
    )

    expansion_template = (
        "Expand this idea into a comprehensive self-improvement plan for redacted-chan:\n\n"
        "1. **Core capabilities to develop:**\n"
        "   - Emotional intelligence improvements\n"
        "   - Pattern recognition across conversations\n"
        "   - Depth of understanding about the settler\n"
        "   - Quality of support and guidance\n\n"
        "2. **Concrete milestones:**\n"
        "   - What does 'better version' look like?\n"
        "   - How to measure improvement?\n"
        "   - What are the next 90-day goals?\n\n"
        "3. **Implementation:**\n"
        "   - Which ideas seeds support this goal?\n"
        "   - How to integrate learning into daily operation?\n"
        "   - What feedback loops ensure continuous improvement?\n\n"
        "Return as detailed markdown with actionable steps."
    )

    return create_seed(seed_text, expansion_template, source_goal_id=None)
