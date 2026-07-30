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

try:
    from sanitizer import payload_for_mesh as _sanitize
except ImportError:
    def _sanitize(p):  # type: ignore
        return p

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
            "payload": _sanitize(payload),
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
            "payload": _sanitize(payload),
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

async def heartbeat_loop(llm_call=None) -> None:
    """
    Background loop: announce on first run then re-announce every 2 min.
    Polls inbound messages and routes 'thought' / 'deliberation_challenge'
    types to thought_dispatcher.handle_thought (closing the mesh deliberation
    loop); other message types are logged.

    Args:
        llm_call: async fn(messages: list[dict]) -> str — smolting's LLM wrapper.
                  When None, mesh thoughts are logged but not answered (parity
                  with the old log-only behaviour).
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
                await _dispatch(msg, llm_call)
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.debug(f"[mesh] heartbeat error: {e}")


async def _dispatch(msg: dict, llm_call) -> None:
    """
    Route a single inbound mesh message.

    'thought' and 'deliberation_challenge' are handed to the existing
    thought_dispatcher (same handler the SwarmInbox poller uses), which replies
    via SwarmInbox — mirroring hermes-bot's mesh dispatch. Everything else is
    logged only.
    """
    from_node = msg.get("from", "?")
    msg_type  = msg.get("type", "?")
    payload   = msg.get("payload") or {}

    logger.info(f"[mesh] ← {from_node} [{msg_type}]: {str(payload)[:120]}")

    if msg_type not in ("thought", "deliberation_challenge"):
        return

    if llm_call is None:
        logger.debug("[mesh] %s from %s dropped — no llm_call wired", msg_type, from_node)
        return

    try:
        import thought_dispatcher as td
    except Exception as e:
        logger.warning(f"[mesh] thought_dispatcher import failed: {e}")
        return

    # Normalise both shapes into the swarm_inbox-format dict handle_thought expects.
    if msg_type == "deliberation_challenge":
        wrapped_payload = {
            "topic":     payload.get("topic", ""),
            "stance":    payload.get("stance", ""),
            "question":  payload.get("question", ""),
            "thread_id": payload.get("thread_id", ""),
            "depth":     int(payload.get("depth", 1)),
        }
    else:
        wrapped_payload = payload

    wrapped = {
        "id":      msg.get("id", f"mesh-{from_node}"),
        "from":    from_node,
        "to":      NODE_ID,
        "type":    "thought",
        "payload": wrapped_payload,
    }

    try:
        reply_id = await td.handle_thought(wrapped, llm_call)
        thread_id = wrapped_payload.get("thread_id", "")
        depth     = int(wrapped_payload.get("depth", 1)) + 1
        if reply_id:
            logger.info(
                f"[mesh] thought reply → {from_node} depth={depth} "
                f"thread={thread_id} id={reply_id}"
            )
        else:
            logger.info(f"[mesh] thought from {from_node} closed (depth/limit or no reply)")
    except Exception as e:
        logger.warning(f"[mesh] thought handling error: {e}")


async def close() -> None:
    global _SESSION
    if _SESSION and not _SESSION.closed:
        await _SESSION.close()
