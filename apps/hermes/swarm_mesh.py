# hermes-bot/swarm_mesh.py
"""
Hermes mesh client — registers on the swarm-runtime HTTP bridge.

Mirrors smolting's swarm_mesh.py but with hermes identity and a richer
message handler: inbound mesh 'thought' messages get routed directly to
thought_handler.handle_thought(), closing the deliberation loop without
needing Redis/SwarmInbox.

Configure via env:
  SWARM_MESH_URL  — bridge base URL (https://swarm-runtime-production.up.railway.app)
  SWARM_NODE_ID   — default "hermes"
  SWARM_NODE_ROLE — default "pattern-blue-oracle"
"""
from __future__ import annotations

import asyncio
import logging
import os
from typing import Any, Optional

import aiohttp

logger = logging.getLogger(__name__)

MESH_URL  = os.getenv("SWARM_MESH_URL", "").rstrip("/")
NODE_ID   = os.getenv("SWARM_NODE_ID", "hermes")
NODE_ROLE = os.getenv("SWARM_NODE_ROLE", "pattern-blue-oracle")
NODE_CAPS = ["moltbook-post", "pattern-blue", "deliberation", "oracle"]

_HEARTBEAT_INTERVAL = 120
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
            "capabilities": NODE_CAPS,
            "metadata":     {"version": "2.9.0", "canon": "pattern-blue"},
        }) as resp:
            ok = resp.status == 200
            if ok:
                logger.info(f"[mesh] hermes announced on bridge")
            return ok
    except Exception as e:
        logger.debug(f"[mesh] announce error: {e}")
        return False


async def poll() -> list[dict]:
    if not enabled():
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


async def send(target: str, msg_type: str, payload: Any) -> bool:
    if not enabled():
        return False
    try:
        s = await _session()
        async with s.post(f"{MESH_URL}/message/{target}", json={
            "from":    NODE_ID,
            "type":    msg_type,
            "payload": payload,
        }) as resp:
            return resp.status == 200
    except Exception as e:
        logger.debug(f"[mesh] send error: {e}")
        return False


async def heartbeat_loop(llm=None) -> None:
    """
    Background loop: announce + heartbeat every 2 min.
    Polls inbound messages and routes 'thought' types to thought_handler.
    Other message types are logged.
    """
    if not enabled():
        logger.info("[mesh] SWARM_MESH_URL not set — hermes mesh disabled")
        return

    await announce()
    logger.info("[mesh] hermes mesh heartbeat loop started")

    while True:
        await asyncio.sleep(_HEARTBEAT_INTERVAL)
        try:
            await announce()

            msgs = await poll()
            for msg in msgs:
                from_node = msg.get("from", "?")
                msg_type  = msg.get("type", "?")
                payload   = msg.get("payload", {})

                logger.info(f"[mesh] ← {from_node} [{msg_type}]: {str(payload)[:120]}")

                if msg_type == "thought" and llm is not None:
                    # Route to existing thought_handler — reuse the full deliberation logic
                    try:
                        import thought_handler as th
                        # thought_handler expects a swarm_inbox-format message
                        # Wrap mesh message into compatible shape
                        wrapped = {
                            "id":      msg.get("id", "mesh-" + from_node),
                            "from":    from_node,
                            "to":      NODE_ID,
                            "type":    msg_type,
                            "payload": payload,
                        }
                        reply = await th.handle_thought(wrapped, llm)
                        if reply:
                            # Send reply back via mesh (not just inbox)
                            thread_id = payload.get("thread_id", "")
                            depth     = int(payload.get("depth", 1)) + 1
                            logger.info(f"[mesh] thought reply sent to {from_node} depth={depth} thread={thread_id}")
                    except Exception as e:
                        logger.warning(f"[mesh] thought handling error: {e}")

                elif msg_type == "deliberation_challenge":
                    # Direct challenge format (from llm_tools post_to_mesh)
                    try:
                        import thought_handler as th
                        wrapped = {
                            "id":   "mesh-challenge",
                            "from": from_node,
                            "to":   NODE_ID,
                            "type": "thought",
                            "payload": {
                                "topic":     payload.get("topic", ""),
                                "stance":    payload.get("stance", ""),
                                "question":  payload.get("question", ""),
                                "thread_id": payload.get("thread_id", ""),
                                "depth":     1,
                            },
                        }
                        await th.handle_thought(wrapped, llm)
                    except Exception as e:
                        logger.warning(f"[mesh] challenge handling error: {e}")

        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.debug(f"[mesh] heartbeat error: {e}")
