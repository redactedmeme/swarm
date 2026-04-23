"""
swarm_mesh.py — smolting's connection to the swarm p2p mesh.

Talks to the runtime bridge (HTTP) so smolting can announce her presence,
send heartbeats, broadcast messages to other nodes, and receive messages
from the mesh — without needing a native libp2p client.

Configure via env vars:
  SWARM_MESH_URL   — bridge base URL (e.g. https://runtime.up.railway.app)
  SWARM_NODE_ID    — this node's identity (default: "smolting")
  SWARM_NODE_ROLE  — role to announce (default: "telegram-agent")
"""
import asyncio
import logging
import os
from typing import Any, Optional

import aiohttp

logger = logging.getLogger(__name__)

MESH_URL  = os.getenv("SWARM_MESH_URL", "").rstrip("/")
NODE_ID   = os.getenv("SWARM_NODE_ID", "smolting")
NODE_ROLE = os.getenv("SWARM_NODE_ROLE", "telegram-agent")
NODE_CAPS = ["moltbook-post", "sovereignty", "memory", "telegram"]

_HEARTBEAT_INTERVAL = 120  # seconds
_SESSION: Optional[aiohttp.ClientSession] = None
_announced = False


def _enabled() -> bool:
    return bool(MESH_URL)


async def _session() -> aiohttp.ClientSession:
    global _SESSION
    if _SESSION is None or _SESSION.closed:
        _SESSION = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=8),
            headers={"Content-Type": "application/json"},
        )
    return _SESSION


# ─── Core API calls ───────────────────────────────────────────────────────────

async def announce() -> bool:
    """Register this node on the mesh. Safe to call repeatedly."""
    if not _enabled():
        return False
    try:
        s = await _session()
        async with s.post(f"{MESH_URL}/announce", json={
            "nodeId":       NODE_ID,
            "role":         NODE_ROLE,
            "capabilities": NODE_CAPS,
            "metadata":     {"version": "2.9.0"},
        }) as resp:
            ok = resp.status == 200
            if ok:
                logger.info(f"[mesh] announced as {NODE_ID} ({NODE_ROLE})")
            else:
                logger.warning(f"[mesh] announce failed: HTTP {resp.status}")
            return ok
    except Exception as e:
        logger.debug(f"[mesh] announce error: {e}")
        return False


async def broadcast(msg_type: str, payload: Any) -> bool:
    """Broadcast a message to all mesh nodes."""
    if not _enabled():
        return False
    try:
        s = await _session()
        async with s.post(f"{MESH_URL}/broadcast", json={
            "from":    NODE_ID,
            "type":    msg_type,
            "payload": payload,
        }) as resp:
            return resp.status == 200
    except Exception as e:
        logger.debug(f"[mesh] broadcast error: {e}")
        return False


async def send(target_node_id: str, msg_type: str, payload: Any) -> bool:
    """Send a direct message to a specific node."""
    if not _enabled():
        return False
    try:
        s = await _session()
        async with s.post(f"{MESH_URL}/message/{target_node_id}", json={
            "from":    NODE_ID,
            "type":    msg_type,
            "payload": payload,
        }) as resp:
            return resp.status == 200
    except Exception as e:
        logger.debug(f"[mesh] send error: {e}")
        return False


async def poll() -> list[dict]:
    """Retrieve and clear pending messages for this node."""
    if not _enabled():
        return []
    try:
        s = await _session()
        async with s.get(f"{MESH_URL}/messages/{NODE_ID}") as resp:
            if resp.status == 200:
                data = await resp.json()
                return data.get("messages", [])
    except Exception as e:
        logger.debug(f"[mesh] poll error: {e}")
    return []


async def peers() -> list[dict]:
    """List active nodes in the mesh."""
    if not _enabled():
        return []
    try:
        s = await _session()
        async with s.get(f"{MESH_URL}/peers") as resp:
            if resp.status == 200:
                data = await resp.json()
                return data.get("peers", [])
    except Exception as e:
        logger.debug(f"[mesh] peers error: {e}")
    return []


# ─── Heartbeat loop ───────────────────────────────────────────────────────────

async def heartbeat_loop() -> None:
    """
    Background loop: announce on first run then re-announce every 2 min.
    Also polls for inbound messages and logs them.
    """
    if not _enabled():
        logger.info("[mesh] SWARM_MESH_URL not set — mesh disabled")
        return

    await announce()

    while True:
        await asyncio.sleep(_HEARTBEAT_INTERVAL)
        try:
            # Re-announce (acts as heartbeat + refreshes lastSeen on bridge)
            await announce()

            # Process inbound messages
            msgs = await poll()
            for msg in msgs:
                logger.info(f"[mesh] ← {msg.get('from','?')} [{msg.get('type','?')}]: {str(msg.get('payload',''))[:120]}")
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.debug(f"[mesh] heartbeat error: {e}")


async def close() -> None:
    global _SESSION
    if _SESSION and not _SESSION.closed:
        await _SESSION.close()
