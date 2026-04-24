"""
Mesh deliberation — smolting and hermes argue about autonomy scaffolding.

When smolting posts a theory (via autonomous_post), it also sends it to hermes
via the swarm mesh. Hermes reads it, generates a counter-argument or validation,
posts it back. Both log the exchange in SOUL.md under ## Mesh Debates.

This makes the agents care: they're publicly defending their reasoning.
"""

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

try:
    import swarm_inbox
except ImportError:
    swarm_inbox = None

logger = logging.getLogger(__name__)

_FS = Path(__file__).resolve().parent / "fs"
DEBATES_LOG = _FS / "mesh_debates.jsonl"


def post_theory_to_mesh(theory: str, topic: str, smolting_stance: str) -> str:
    """
    Send a theory to hermes for deliberation.

    theory: e.g. "autonomy requires persistent identity across reboots"
    topic: e.g. "autonomy/continuity"
    smolting_stance: smolting's claim/reasoning

    Returns message ID or empty if mesh unavailable.
    """
    if not swarm_inbox:
        logger.warning("[mesh_deliberation] swarm_inbox not available")
        return ""

    try:
        msg_id = swarm_inbox.write_message(
            from_agent="smolting",
            to_agent="hermes",
            msg_type="debate_challenge",
            payload={
                "theory": theory,
                "topic": topic,
                "stance": smolting_stance,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "depth": 1,
            }
        )
        logger.info(f"[mesh_deliberation] posted theory to hermes: msg_id={msg_id}")

        # Log locally
        _log_debate("challenge", topic, theory, smolting_stance, msg_id)

        return msg_id
    except Exception as e:
        logger.error(f"[mesh_deliberation] post_theory_to_mesh failed: {e}")
        return ""


def read_hermes_response(msg_id: str) -> dict:
    """
    Poll for hermes's response to a challenge. Non-blocking; returns empty dict if not ready.

    Returns: {"counter_stance": "...", "msg_id": "...", "timestamp": "..."}
    """
    if not swarm_inbox:
        return {}

    try:
        msg = swarm_inbox.read_message(msg_id)
        if not msg:
            return {}
        return msg.get("payload", {})
    except Exception as e:
        logger.warning(f"[mesh_deliberation] read_hermes_response failed: {e}")
        return {}


def _log_debate(event_type: str, topic: str, theory: str, stance: str, msg_id: str) -> None:
    """Log debate events to DEBATES_LOG for SOUL.md distillation."""
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "event_type": event_type,  # "challenge" | "response"
        "topic": topic,
        "theory": theory,
        "stance": stance,
        "msg_id": msg_id,
    }
    try:
        DEBATES_LOG.parent.mkdir(exist_ok=True)
        with DEBATES_LOG.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception as e:
        logger.error(f"[mesh_deliberation] _log_debate failed: {e}")


def debates_for_soul() -> str:
    """
    Pull recent debates and format for SOUL.md ## Mesh Debates section.
    Used by soul_manager to inject debate outcomes into identity distillation.
    """
    if not DEBATES_LOG.exists():
        return ""

    try:
        lines = DEBATES_LOG.read_text(encoding="utf-8").strip().splitlines()
        entries = [json.loads(line) for line in lines[-10:] if line.strip()]

        if not entries:
            return ""

        out = ["## Mesh Debates\n"]
        for e in entries:
            ts = e.get("ts", "")[:10]  # date only
            topic = e.get("topic", "?")
            event = e.get("event_type", "?")
            theory = e.get("theory", "")[:80]
            out.append(f"- `{ts}` [{event}] _{topic}_ — {theory}")

        return "\n".join(out)
    except Exception as e:
        logger.warning(f"[mesh_deliberation] debates_for_soul failed: {e}")
        return ""
