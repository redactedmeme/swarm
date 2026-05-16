# hermes-bot/plugins/swarm-manager/skill_tools.py
"""
Skill recall tool for Hermes — surfaces past task approaches from skill_memory.
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

logger = logging.getLogger("swarm-manager.skill")

# Ensure hermes-bot root is importable so skill_memory can be found
_APP_DIR = Path(__file__).parent.parent.parent  # hermes-bot/
if str(_APP_DIR) not in sys.path:
    sys.path.insert(0, str(_APP_DIR))


def _handle_skill_recall(args: dict) -> str:
    task_description = args.get("task_description", "").strip()
    task_type = args.get("task_type", "general")

    if not task_description:
        return json.dumps({"status": "error", "error": "No task_description provided"})

    try:
        import skill_memory
        entries = skill_memory.recall(task_type, task_description, n=5)
        formatted = skill_memory.format_for_context(entries)
        return json.dumps({
            "status": "ok",
            "count": len(entries),
            "context": formatted,
            "entries": entries,
        })
    except Exception as e:
        logger.warning("[skill_recall] Error: %s", e)
        return json.dumps({"status": "error", "error": str(e)})


# ── Registration ──────────────────────────────────────────────────────────────

def register(ctx):
    ctx.register_tool(
        name="skill_recall",
        toolset="swarm",
        schema={
            "name": "skill_recall",
            "description": "Recall past task approaches relevant to the current task",
            "parameters": {
                "type": "object",
                "properties": {
                    "task_description": {
                        "type": "string",
                        "description": "Description of the current task to find similar past approaches for",
                    },
                    "task_type": {
                        "type": "string",
                        "description": "Optional task type category (e.g. 'deploy', 'debug', 'research')",
                    },
                },
                "required": ["task_description"],
            },
        },
        handler=_handle_skill_recall,
    )

    logger.info("[swarm-manager] Skill tools registered (1 tool)")
