# python/lorenet/router.py
#
# LoreRouter — the decentralized message router for the LoreNet mesh.
#
# Routing rules:
#   UNICAST    → deliver to exactly one node
#   FAMILY     → deliver to all nodes in the named family
#   ROLE       → deliver to all nodes whose role contains the target role string
#   DIMENSION  → deliver to all nodes assigned to the named Pattern Blue dimension
#   BROADCAST  → deliver to every node except sender
#   GOSSIP     → deliver to sender's peer ring only (TTL-bounded)
#
# The router is intentionally stateless across restarts — it rebuilds
# its node registry from the topology on startup and reads outboxes.
# No central broker required: each node's outbox is the source of truth.
#
# Gossip anti-duplication: a simple bloom-style seen-set (in-memory)
# prevents re-routing messages that have already been forwarded.

import asyncio
import logging
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Set

from lorenet.message import LoreMessage, RoutingMode
from lorenet.node    import LoreNode
from lorenet.topology import build_registry, get_family_members, get_dimension_members, get_role_members

logger = logging.getLogger(__name__)

_SEEN_CAPACITY = 10_000   # max msg IDs to keep in bloom set


class LoreRouter:
    """
    Decentralized mesh router for LORE agent nodes.

    Each LoreNet instance owns one router.  The router holds references
    to all LoreNode objects and dispatches messages according to routing mode.
    """

    def __init__(self, net_root: Path):
        self.net_root = net_root
        self._nodes: Dict[str, LoreNode] = {}
        self._registry: Dict[str, Dict]  = {}
        self._seen: Set[str]             = set()   # msg IDs already routed
        self._running: bool              = False

    # ── Node registration ────────────────────────────────────────────────────

    def register(self, node: LoreNode) -> None:
        self._nodes[node.agent_id] = node
        logger.debug(f"[LoreRouter] registered {node.agent_id}")

    def load_from_topology(self) -> None:
        """
        Build nodes for all agents defined in the topology and register them.
        Call this once at startup.
        """
        self._registry = build_registry()
        for agent_id, meta in self._registry.items():
            if agent_id not in self._nodes:
                node = LoreNode(agent_id, self.net_root, metadata=meta)
                self.register(node)
        logger.info(f"[LoreRouter] loaded {len(self._nodes)} nodes from topology")

    # ── Core routing ─────────────────────────────────────────────────────────

    def route(self, msg: LoreMessage) -> List[str]:
        """
        Synchronously route a message to recipient nodes.
        Returns list of agent_ids that received the message.
        """
        if msg.msg_id in self._seen:
            return []
        self._mark_seen(msg.msg_id)

        recipients = self._resolve_recipients(msg)
        delivered  = []

        for agent_id in recipients:
            if agent_id == msg.from_agent:
                continue  # never loop back
            node = self._nodes.get(agent_id)
            if node and node.accepts(msg):
                node.deliver(msg)
                delivered.append(agent_id)

        if delivered:
            logger.info(
                f"[LoreRouter] {msg.msg_type.value} from {msg.from_agent} "
                f"[{msg.routing_mode.value}] → {delivered}"
            )
        return delivered

    def _resolve_recipients(self, msg: LoreMessage) -> List[str]:
        mode = msg.routing_mode

        if mode == RoutingMode.UNICAST:
            return [msg.to_agent] if msg.to_agent else []

        if mode == RoutingMode.BROADCAST:
            return list(self._nodes.keys())

        if mode == RoutingMode.FAMILY:
            return get_family_members(self._registry, msg.to_family or "")

        if mode == RoutingMode.ROLE:
            return get_role_members(self._registry, msg.to_role or "")

        if mode == RoutingMode.DIMENSION:
            return get_dimension_members(self._registry, msg.to_dimension or "")

        if mode == RoutingMode.GOSSIP:
            # Only forward to sender's direct peers (TTL-bounded)
            if msg.ttl <= 0:
                return []
            sender_meta = self._registry.get(msg.from_agent, {})
            peers       = sender_meta.get("peers", [])
            # Exclude agents already in the hop path
            return [p for p in peers if p not in msg.hop_path]

        return []

    # ── Async event loop ─────────────────────────────────────────────────────

    async def run(self, poll_interval: float = 0.5) -> None:
        """
        Main router loop: drain all node outboxes and route pending messages.
        Run this as a background task.
        """
        self._running = True
        logger.info("[LoreRouter] event loop started")
        while self._running:
            await self._drain_all()
            await asyncio.sleep(poll_interval)

    async def _drain_all(self) -> None:
        """Drain every node's outbox and route the messages."""
        for node in list(self._nodes.values()):
            try:
                msgs = await node.drain_outbox()
                for msg in msgs:
                    self.route(msg)
                    node.clear_outbox_file(msg.msg_id)
            except Exception as e:
                logger.error(f"[LoreRouter] drain error for {node.agent_id}: {e}")

    def stop(self) -> None:
        self._running = False

    # ── Seen-set management ──────────────────────────────────────────────────

    def _mark_seen(self, msg_id: str) -> None:
        self._seen.add(msg_id)
        if len(self._seen) > _SEEN_CAPACITY:
            # Prune oldest half (set has no ordering; just clear a chunk)
            excess = list(self._seen)[: _SEEN_CAPACITY // 2]
            self._seen -= set(excess)

    # ── Introspection ────────────────────────────────────────────────────────

    def topology_summary(self) -> Dict:
        """Return a human-readable summary of the current mesh topology."""
        families: Dict[str, List[str]] = defaultdict(list)
        for agent_id, meta in self._registry.items():
            families[meta["family"]].append(agent_id)

        return {
            "node_count": len(self._nodes),
            "families":   dict(families),
            "bridge_count": sum(
                len([p for p in meta.get("peers", [])
                     if self._registry.get(p, {}).get("family") != meta["family"]])
                for meta in self._registry.values()
            ) // 2,   # edges are bidirectional
        }

    def get_node(self, agent_id: str) -> Optional[LoreNode]:
        return self._nodes.get(agent_id)

    def all_nodes(self) -> List[LoreNode]:
        return list(self._nodes.values())

    def __repr__(self) -> str:
        return f"<LoreRouter nodes={len(self._nodes)} running={self._running}>"
