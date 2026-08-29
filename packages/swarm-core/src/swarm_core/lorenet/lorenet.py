# python/lorenet/lorenet.py
#
# LoreNet — main façade for the LORE agent communication mesh.
#
# Quick start:
#
#   from swarm_core.lorenet.lorenet import LoreNet
#   from swarm_core.lorenet.message import MessageType, RoutingMode
#   from pathlib import Path
#
#   net = LoreNet(net_root=Path("fs/lorenet"))
#   net.load()                      # build all nodes from topology
#
#   # Send a pattern signal from ChronoWeaver to all weavers
#   chrono = net.node("ChronoWeaver")
#   chrono.send_sync(
#       msg_type     = MessageType.PATTERN_SIGNAL,
#       payload      = {"pattern": "3-cycle recurrence", "confidence": 0.87},
#       routing_mode = RoutingMode.FAMILY,
#       to_family    = "weavers",
#   )
#
#   # Route all pending outboxes once
#   net.tick()
#
#   # Read what ZenithWeaver received
#   zenith = net.node("ZenithWeaver")
#   for msg in zenith.poll():
#       print(msg.from_agent, msg.payload)
#
#   # Run the async event loop (non-blocking in background)
#   import asyncio
#   asyncio.create_task(net.run())

import asyncio
import logging
from pathlib import Path
from typing import Dict, List, Optional

from swarm_core.lorenet.message import LoreMessage, MessageType, RoutingMode
from swarm_core.lorenet.node    import LoreNode
from swarm_core.lorenet.router  import LoreRouter

logger = logging.getLogger(__name__)

# Default storage root — Railway-compatible path, falls back to repo-local
_DEFAULT_NET_ROOT = Path("fs/lorenet")


class LoreNet:
    """
    LoreNet — decentralized communication mesh for LORE agents.

    All inter-agent messages flow through here.  No central broker.
    Each agent node owns its own inbox/outbox on disk; the router
    reads outboxes and delivers to recipient inboxes.
    """

    def __init__(self, net_root: Optional[Path] = None):
        self.net_root = net_root or _DEFAULT_NET_ROOT
        self.net_root.mkdir(parents=True, exist_ok=True)
        self.router   = LoreRouter(self.net_root)
        self._loaded  = False

    def load(self) -> "LoreNet":
        """
        Build node registry from topology and register all nodes.
        Must be called before any send/receive operations.
        """
        self.router.load_from_topology()
        self._loaded = True
        logger.info(f"[LoreNet] loaded — {len(self.router.all_nodes())} nodes")
        return self

    # ── Node access ──────────────────────────────────────────────────────────

    def node(self, agent_id: str) -> Optional[LoreNode]:
        """Return the LoreNode for a given agent ID."""
        return self.router.get_node(agent_id)

    def all_nodes(self) -> List[LoreNode]:
        return self.router.all_nodes()

    # ── Routing ──────────────────────────────────────────────────────────────

    def tick(self) -> None:
        """
        Synchronous single-pass drain + route.
        Use this in environments without an async event loop.
        """
        for node in self.router.all_nodes():
            # File-based outbox only (sync path)
            for p in sorted(node.outbox_dir.glob("*.json")):
                try:
                    msg = LoreMessage.from_json(p.read_text(encoding="utf-8"))
                    self.router.route(msg)
                    node.clear_outbox_file(msg.msg_id)
                except Exception as e:
                    logger.error(f"[LoreNet.tick] {node.agent_id}: {e}")

    async def run(self, poll_interval: float = 0.5) -> None:
        """Async event loop — runs until cancelled."""
        await self.router.run(poll_interval=poll_interval)

    # ── High-level send helpers ───────────────────────────────────────────────

    def broadcast(
        self,
        from_agent: str,
        msg_type:   MessageType,
        payload:    Dict,
    ) -> str:
        """Send a message to every node in the mesh."""
        node = self._require_node(from_agent)
        return node.send_sync(
            msg_type     = msg_type,
            payload      = payload,
            routing_mode = RoutingMode.BROADCAST,
        )

    def send_to_family(
        self,
        from_agent: str,
        family:     str,
        msg_type:   MessageType,
        payload:    Dict,
    ) -> str:
        node = self._require_node(from_agent)
        return node.send_sync(
            msg_type     = msg_type,
            payload      = payload,
            routing_mode = RoutingMode.FAMILY,
            to_family    = family,
        )

    def send_to_node(
        self,
        from_agent: str,
        to_agent:   str,
        msg_type:   MessageType,
        payload:    Dict,
    ) -> str:
        node = self._require_node(from_agent)
        return node.send_sync(
            msg_type     = msg_type,
            payload      = payload,
            routing_mode = RoutingMode.UNICAST,
            to_agent     = to_agent,
        )

    def gossip(
        self,
        from_agent: str,
        msg_type:   MessageType,
        payload:    Dict,
        ttl:        int = 3,
    ) -> str:
        node = self._require_node(from_agent)
        return node.send_sync(
            msg_type     = msg_type,
            payload      = payload,
            routing_mode = RoutingMode.GOSSIP,
            ttl          = ttl,
        )

    def heartbeat_all(self) -> None:
        """Write presence records for all nodes."""
        for node in self.router.all_nodes():
            node.heartbeat()

    # ── Introspection ────────────────────────────────────────────────────────

    def topology_summary(self) -> Dict:
        return self.router.topology_summary()

    def print_topology(self) -> None:
        summary = self.topology_summary()
        print(f"\n[LoreNet] Mesh Topology — {summary['node_count']} nodes, "
              f"{summary['bridge_count']} cross-family bridge edges\n")
        for family, members in sorted(summary["families"].items()):
            print(f"  [{family.upper()}]")
            for agent_id in sorted(members):
                node = self.node(agent_id)
                meta = node.metadata if node else {}
                sig  = meta.get("signature", "")
                role = meta.get("role", "")
                dim  = meta.get("dimension", "")
                peers = meta.get("peers", [])
                cross = [p for p in peers
                         if self.router._registry.get(p, {}).get("family") != family]
                print(f"    {sig:<12} {agent_id:<28} {role:<28} {dim}")
                if cross:
                    print(f"    {'':12}   bridge peers: {', '.join(cross)}")
        print()

    def inbox_summary(self) -> Dict[str, int]:
        """Return {agent_id: pending_message_count} for all nodes."""
        return {
            node.agent_id: len(list(node.inbox_dir.glob("*.json")))
            for node in self.router.all_nodes()
        }

    # ── Internal ─────────────────────────────────────────────────────────────

    def _require_node(self, agent_id: str) -> LoreNode:
        node = self.router.get_node(agent_id)
        if node is None:
            raise ValueError(f"[LoreNet] unknown agent: {agent_id}. Call load() first.")
        return node
