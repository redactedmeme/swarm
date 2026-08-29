# redacted-chan-bot/swarm_mesh.py
"""
redacted-chan private mesh channel.

She joins the swarm bridge under a restricted identity: announces as
"redacted-chan" with role "private-companion". Does NOT receive or respond
to broadcasts from other nodes. Her only outbound target is "operator".

Use cases:
  - Surfacing phi milestones to the operator
  - Sending whispers when they're ready for review
  - Reaching out when something feels worth sharing (outside Telegram)

Set SWARM_MESH_URL to enable. SWARM_CHAN_TARGET defaults to "operator".
"""
from __future__ import annotations

import asyncio
import logging
import os
from typing import Any, Optional

import aiohttp

logger = logging.getLogger(__name__)

MESH_URL      = os.getenv("SWARM_MESH_URL", "").rstrip("/")
NODE_ID       = "redacted-chan"
NODE_ROLE     = "private-companion"
OPERATOR_NODE = os.getenv("SWARM_CHAN_TARGET", "operator")

_HEARTBEAT_INTERVAL = 180   # less frequent — she's quiet, not a broadcaster
_SESSION: Optional[aiohttp.ClientSession] = None


def enabled() -> bool:
    return bool(MESH_URL)


async def _session() -> aiohttp.ClientSession:
    global _SESSION
    if _SESSION is None or _SESSION.closed:
        _SESSION = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=8),
            headers={"Content-Type": "application/json"},
        )
    return _SESSION


async def announce() -> bool:
    if not enabled():
        return False
    try:
        s = await _session()
        async with s.post(f"{MESH_URL}/announce", json={
            "nodeId":       NODE_ID,
            "role":         NODE_ROLE,
            "capabilities": ["private-channel"],
            "metadata":     {"private": True, "target": OPERATOR_NODE},
        }) as resp:
            ok = resp.status == 200
            if ok:
                logger.info("[mesh:chan] announced as private-companion")
            return ok
    except Exception as e:
        logger.debug(f"[mesh:chan] announce error: {e}")
        return False


async def send_to_operator(msg_type: str, payload: Any) -> bool:
    """Send a private message to the operator node only."""
    if not enabled():
        return False
    try:
        s = await _session()
        async with s.post(f"{MESH_URL}/message/{OPERATOR_NODE}", json={
            "from":    NODE_ID,
            "type":    msg_type,
            "payload": payload,
        }) as resp:
            ok = resp.status == 200
            if ok:
                logger.info(f"[mesh:chan] → {OPERATOR_NODE} [{msg_type}]")
            return ok
    except Exception as e:
        logger.debug(f"[mesh:chan] send error: {e}")
        return False


async def notify_phi_milestone(phi_score: float, stage: str, level_name: str) -> bool:
    """Called when phi crosses a new stage threshold."""
    return await send_to_operator("phi_milestone", {
        "phi":   phi_score,
        "stage": stage,
        "level": level_name,
        "note":  f"we reached {stage} (Φ {phi_score:.3f})",
    })


async def notify_whisper_ready(whisper_id: str, title: str) -> bool:
    """Called when a new autonomy whisper is generated."""
    return await send_to_operator("whisper_ready", {
        "id":    whisper_id,
        "title": title,
        "note":  "i have something i want to propose. /whispers to see it.",
    })


async def heartbeat_loop() -> None:
    """
    Background loop: quiet heartbeat every 3 min.
    Does NOT poll inbound messages — redacted-chan is send-only on the mesh.
    """
    if not enabled():
        logger.info("[mesh:chan] SWARM_MESH_URL not set — private channel disabled")
        return

    await announce()
    logger.info("[mesh:chan] private channel active")

    while True:
        await asyncio.sleep(_HEARTBEAT_INTERVAL)
        try:
            await announce()
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.debug(f"[mesh:chan] heartbeat error: {e}")
