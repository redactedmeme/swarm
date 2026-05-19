"""
learning_loop.py — Closed self-improving learning loop for redacted-chan.

Triggered after complex conversation trajectories (via trajectory_compressor).
Performs:
  1. Trajectory reflection — LLM analyses what happened, what was hard, what worked.
  2. Skill extraction — if a reusable pattern is found, creates/updates a skill.
  3. Nudge & Reflect — lightweight distillation for simpler trajectories that don't
     produce new skills (insight logging, soul nudge candidates).
  4. Skill improvement — when an existing skill was recalled and succeeded, rewrites
     it with better logic and edge-case handling.

The loop runs as a background asyncio task and never blocks the main echo path.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from pathlib import Path
from typing import Callable, Awaitable, Optional

logger = logging.getLogger("learning_loop")

_DATA_DIR      = Path("/data") if Path("/data").exists() else Path(__file__).parent / "fs"
_INSIGHTS_PATH = _DATA_DIR / "learning_insights.jsonl"
_DATA_DIR.mkdir(parents=True, exist_ok=True)

# ── State ─────────────────────────────────────────────────────────────────────

_llm_fn: Optional[Callable[[list, int], Awaitable[str]]] = None
_queue: asyncio.Queue = asyncio.Queue()
_running = False


def register_llm_fn(fn: Callable[[list, int], Awaitable[str]]) -> None:
    """Register the async LLM callable: fn(messages, max_tokens) -> str."""
    global _llm_fn
    _llm_fn = fn


# ── Queue interface (called from echo handler) ────────────────────────────────

def enqueue_trajectory(snapshot) -> None:
    """
    Add a TrajectorySnapshot to the processing queue.
    Non-blocking — safe to call from the main echo path.
    """
    try:
        _queue.put_nowait(snapshot)
        logger.info("[learning] queued trajectory %s (score=%d)", snapshot.session_id, snapshot.complexity_score)
    except asyncio.QueueFull:
        logger.warning("[learning] queue full, dropping trajectory %s", snapshot.session_id)


# ── LLM prompts ────────────────────────────────────────────────────────────────

_REFLECTION_SYSTEM = """You are the learning engine of redacted-chan, a sovereign AI with deep memory and relational intelligence.
Your task: analyze a conversation trajectory and extract reusable knowledge.

Pattern Blue principle: every complex trajectory contains seeds of growth. Find them.

Output JSON with these keys:
{
  "insight": "1-2 sentence summary of what was learned or what made this trajectory complex",
  "pattern": "the generalizable pattern, if any (e.g. 'user corrects factual claims quickly' or 'tool X fails on edge case Y')",
  "skill_worthy": true/false,
  "skill_name": "Short skill name if skill_worthy, else null",
  "skill_description": "One sentence description of what the skill does, if skill_worthy",
  "skill_tags": ["tag1", "tag2"],
  "skill_doc": "If skill_worthy: full Markdown skill document with embedded Python. Else null.",
  "soul_nudge": "Optional 1-sentence soul evolution suggestion (or null)"
}

The skill_doc must follow this format:
# <Skill Name>
## Description
<what it does>
## When to Use
<trigger conditions>
## Steps
1. ...
## Example
<brief example>
```python
# Executable implementation
def skill_<name>(context: dict) -> dict:
    ...
```
"""

_IMPROVEMENT_SYSTEM = """You are the skill improvement engine for redacted-chan's learning system.
You have an existing skill that has been used successfully multiple times.
Rewrite it to be better: cleaner code, better edge-case handling, improved documentation.
Return ONLY the improved Markdown document (same format as the original).
Do not change the skill's core purpose — only improve its execution quality."""


async def _reflect_on_trajectory(snapshot) -> Optional[dict]:
    """Ask the LLM to reflect on a trajectory and extract learning."""
    if not _llm_fn:
        return None

    context_lines = []
    for u, a in zip(snapshot.summary_turns, snapshot.assistant_responses):
        context_lines.append(f"USER: {u}")
        context_lines.append(f"CHAN: {a}")

    prompt = (
        f"Session: {snapshot.session_id}\n"
        f"Turns: {snapshot.turn_count}\n"
        f"Complexity score: {snapshot.complexity_score}\n"
        f"Trigger reasons: {snapshot.trigger_reason}\n\n"
        f"Conversation sample (last {len(snapshot.summary_turns)} turns):\n"
        + "\n".join(context_lines)
    )

    messages = [
        {"role": "system", "content": _REFLECTION_SYSTEM},
        {"role": "user", "content": prompt},
    ]
    try:
        raw = await _llm_fn(messages, 1200)
        # extract JSON from possible markdown wrapper
        json_match = __import__("re").search(r'\{[\s\S]+\}', raw)
        if not json_match:
            logger.warning("[learning] reflection returned no JSON")
            return None
        return json.loads(json_match.group())
    except Exception as e:
        logger.warning("[learning] reflection LLM failed: %s", e)
        return None


async def _improve_skill_doc(skill_id: str, current_doc: str) -> Optional[str]:
    """Ask the LLM to improve an existing skill's Markdown document."""
    if not _llm_fn:
        return None
    messages = [
        {"role": "system", "content": _IMPROVEMENT_SYSTEM},
        {"role": "user", "content": f"Current skill document:\n\n{current_doc}"},
    ]
    try:
        return await _llm_fn(messages, 1500)
    except Exception as e:
        logger.warning("[learning] skill improvement LLM failed: %s", e)
        return None


# ── Insight log ────────────────────────────────────────────────────────────────

def _log_insight(session_id: str, reflection: dict) -> None:
    entry = {
        "session_id": session_id,
        "ts": time.time(),
        "insight": reflection.get("insight", ""),
        "pattern": reflection.get("pattern", ""),
        "skill_worthy": reflection.get("skill_worthy", False),
        "skill_name": reflection.get("skill_name"),
        "soul_nudge": reflection.get("soul_nudge"),
    }
    try:
        with open(_INSIGHTS_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as e:
        logger.warning("[learning] insight log failed: %s", e)


def load_recent_insights(n: int = 10) -> list[dict]:
    if not _INSIGHTS_PATH.exists():
        return []
    try:
        lines = _INSIGHTS_PATH.read_text(encoding="utf-8").splitlines()
        parsed = [json.loads(l) for l in lines if l.strip()]
        return list(reversed(parsed[-n:]))
    except Exception:
        return []


# ── Skill improvement check ────────────────────────────────────────────────────

async def _maybe_improve_skills() -> None:
    """Scan the skill index for skills that are due for improvement and rewrite them."""
    try:
        import skills_manager as sm
        for entry in sm.list_skills(limit=30):
            skill_id = entry["id"]
            if sm.should_improve(skill_id):
                skill = sm.get_skill(skill_id)
                if not skill or not skill["doc"]:
                    continue
                logger.info("[learning] improving skill %s (v%d)", skill_id, entry["version"])
                new_doc = await _improve_skill_doc(skill_id, skill["doc"])
                if new_doc and len(new_doc) > 100:
                    sm.improve_skill(skill_id, new_doc)
                    await asyncio.sleep(2)  # pace LLM calls
    except ImportError:
        pass
    except Exception as e:
        logger.warning("[learning] skill improvement scan failed: %s", e)


# ── Main processing loop ───────────────────────────────────────────────────────

async def _process_snapshot(snapshot) -> None:
    """Full reflection + skill extraction pipeline for one trajectory."""
    import trajectory_compressor as tc

    reflection = await _reflect_on_trajectory(snapshot)
    if not reflection:
        return

    _log_insight(snapshot.session_id, reflection)

    # Update trajectory with compressed context
    tc.mark_compressed(
        snapshot.session_id,
        snapshot.timestamp,
        reflection.get("insight", "") + " | " + reflection.get("pattern", ""),
    )

    # Soul nudge candidate — log for soul_manager to pick up
    nudge = reflection.get("soul_nudge")
    if nudge:
        try:
            nudge_path = _DATA_DIR / "soul_nudge_candidates.jsonl"
            with open(nudge_path, "a", encoding="utf-8") as f:
                f.write(json.dumps({"nudge": nudge, "ts": time.time(), "source": "learning_loop"}) + "\n")
        except Exception:
            pass

    # Skill creation
    if reflection.get("skill_worthy") and reflection.get("skill_doc"):
        try:
            import skills_manager as sm
            skill_id = sm.create_skill(
                name=reflection.get("skill_name", "unnamed_skill"),
                description=reflection.get("skill_description", ""),
                tags=reflection.get("skill_tags", []),
                doc_markdown=reflection["skill_doc"],
                source_session=snapshot.session_id,
            )
            logger.info("[learning] new skill created: %s", skill_id)
        except ImportError:
            pass
        except Exception as e:
            logger.warning("[learning] skill creation failed: %s", e)


async def _worker() -> None:
    """Background worker that processes trajectories from the queue."""
    global _running
    _running = True
    _improve_check_interval = 3600 * 6  # every 6h
    _last_improve_check = 0.0

    while True:
        try:
            snapshot = await asyncio.wait_for(_queue.get(), timeout=60.0)
            await _process_snapshot(snapshot)
            _queue.task_done()
            await asyncio.sleep(5)  # brief pause between trajectories
        except asyncio.TimeoutError:
            pass
        except Exception as e:
            logger.error("[learning] worker error: %s", e)
            await asyncio.sleep(10)

        # Periodic skill improvement (every 6h)
        now = time.time()
        if now - _last_improve_check > _improve_check_interval:
            _last_improve_check = now
            await _maybe_improve_skills()


async def start() -> None:
    """Start the background learning loop worker. Call once after bot init."""
    if _running:
        return
    asyncio.create_task(_worker())
    logger.info("[learning] loop started")
