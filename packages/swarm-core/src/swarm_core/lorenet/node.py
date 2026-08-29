# python/lorenet/node.py
#
# LoreNode — one agent's presence on the LoreNet mesh.
#
# Each node owns:
#   - An inbox directory where other nodes drop messages for it
#   - An outbox queue (in-memory; router drains it)
#   - A subscription set (message types + topics it cares about)
#   - A handler registry (msg_type → async callable)
#
# Storage layout (file-based, consistent with SwarmInbox):
#   {net_root}/{agent_id}/inbox/{msg_id}.json       — inbound, pending
#   {net_root}/{agent_id}/processed/{msg_id}.json   — completed
#   {net_root}/{agent_id}/outbox/{msg_id}.json      — queued for routing
#   {net_root}/heartbeat/{agent_id}.json            — last seen

import asyncio
import json
import logging
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set

from swarm_core.lorenet.message import LoreMessage, MessageType, RoutingMode

logger = logging.getLogger(__name__)


class LoreNode:
    """
    A single LORE agent's network node.

    Usage:
        node = LoreNode("ChronoWeaver", net_root=Path("fs/lorenet"))
        node.subscribe(MessageType.PATTERN_SIGNAL, my_handler)
        await node.send(
            msg_type     = MessageType.PATTERN_SIGNAL,
            payload      = {"pattern": "3-cycle recurrence detected"},
            routing_mode = RoutingMode.FAMILY,
            to_family    = "weavers",
        )
        msgs = node.poll()
    """

    def __init__(
        self,
        agent_id: str,
        net_root: Path,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        self.agent_id = agent_id
        self.net_root = net_root
        self.metadata = metadata or {}
        self._lock    = threading.Lock()

        # Subscription sets
        self._subscribed_types:      Set[MessageType] = set()
        self._subscribed_families:   Set[str]         = set()
        self._subscribed_roles:      Set[str]         = set()
        self._subscribed_dimensions: Set[str]         = set()
        self._accept_broadcast       = True
        self._accept_gossip          = True

        # Async handler registry: msg_type → coroutine callable
        self._handlers: Dict[MessageType, Callable] = {}

        # Outbound queue (in-memory; router drains this)
        self._outbox: asyncio.Queue = asyncio.Queue()

        # Ensure directories exist
        for subdir in ("inbox", "outbox", "processed"):
            (self.net_root / agent_id / subdir).mkdir(parents=True, exist_ok=True)
        (self.net_root / "heartbeat").mkdir(parents=True, exist_ok=True)

        logger.info(f"[LoreNode:{agent_id}] initialized at {net_root / agent_id}")

    # ── Directory helpers ────────────────────────────────────────────────────

    @property
    def inbox_dir(self) -> Path:
        return self.net_root / self.agent_id / "inbox"

    @property
    def outbox_dir(self) -> Path:
        return self.net_root / self.agent_id / "outbox"

    @property
    def processed_dir(self) -> Path:
        return self.net_root / self.agent_id / "processed"

    # ── Subscription API ─────────────────────────────────────────────────────

    def subscribe(
        self,
        msg_type:  Optional[MessageType] = None,
        family:    Optional[str]         = None,
        role:      Optional[str]         = None,
        dimension: Optional[str]         = None,
        handler:   Optional[Callable]    = None,
    ) -> "LoreNode":
        """Chain-able subscription builder."""
        if msg_type:
            self._subscribed_types.add(msg_type)
            if handler:
                self._handlers[msg_type] = handler
        if family:
            self._subscribed_families.add(family.lower())
        if role:
            self._subscribed_roles.add(role.lower())
        if dimension:
            self._subscribed_dimensions.add(dimension.lower())
        return self

    def accepts(self, msg: LoreMessage) -> bool:
        """Return True if this node should receive the given message."""
        mode = msg.routing_mode

        if mode == RoutingMode.BROADCAST:
            return self._accept_broadcast

        if mode == RoutingMode.GOSSIP:
            return self._accept_gossip

        if mode == RoutingMode.UNICAST:
            return msg.to_agent == self.agent_id

        if mode == RoutingMode.FAMILY:
            own_family = self.metadata.get("family", "")
            return msg.to_family and msg.to_family.lower() == own_family.lower()

        if mode == RoutingMode.ROLE:
            own_role = self.metadata.get("role", "")
            return (
                msg.to_role and
                (msg.to_role.lower() in own_role.lower() or
                 own_role.lower() in msg.to_role.lower())
            )

        if mode == RoutingMode.DIMENSION:
            own_dim = self.metadata.get("dimension", "")
            return msg.to_dimension and msg.to_dimension.lower() in own_dim.lower()

        return False

    # ── Send API ─────────────────────────────────────────────────────────────

    async def send(
        self,
        msg_type:     MessageType,
        payload:      Dict[str, Any],
        routing_mode: RoutingMode      = RoutingMode.BROADCAST,
        to_agent:     Optional[str]    = None,
        to_family:    Optional[str]    = None,
        to_role:      Optional[str]    = None,
        to_dimension: Optional[str]    = None,
        correlation_id: Optional[str]  = None,
        ttl:          int              = 5,
    ) -> str:
        """Queue a message for routing. Returns msg_id."""
        msg = LoreMessage.create(
            from_agent    = self.agent_id,
            msg_type      = msg_type,
            payload       = payload,
            routing_mode  = routing_mode,
            to_agent      = to_agent,
            to_family     = to_family,
            to_role       = to_role,
            to_dimension  = to_dimension,
            correlation_id = correlation_id,
            ttl           = ttl,
        )
        # Write to local outbox for durability, then enqueue in-memory
        outbox_file = self.outbox_dir / f"{msg.msg_id}.json"
        outbox_file.write_text(msg.to_json(), encoding="utf-8")
        await self._outbox.put(msg)
        logger.debug(f"[LoreNode:{self.agent_id}] queued {msg.msg_type.value} → {routing_mode.value}")
        return msg.msg_id

    def send_sync(self, msg_type: MessageType, payload: Dict[str, Any], **kwargs) -> str:
        """Synchronous wrapper for send() when no event loop is running."""
        msg = LoreMessage.create(
            from_agent = self.agent_id,
            msg_type   = msg_type,
            payload    = payload,
            **kwargs,
        )
        outbox_file = self.outbox_dir / f"{msg.msg_id}.json"
        outbox_file.write_text(msg.to_json(), encoding="utf-8")
        # Drop into persistent outbox only; router will pick it up on next drain
        logger.debug(f"[LoreNode:{self.agent_id}] sync-queued {msg.msg_type.value}")
        return msg.msg_id

    # ── Receive API ──────────────────────────────────────────────────────────

    def deliver(self, msg: LoreMessage) -> None:
        """
        Deliver a message to this node's inbox (called by the router).
        Writes to disk atomically.
        """
        if msg.from_agent == self.agent_id:
            return  # don't loop back to sender

        dest = self.inbox_dir / f"{msg.msg_id}.json"
        with self._lock:
            dest.write_text(msg.to_json(), encoding="utf-8")
        logger.debug(f"[LoreNode:{self.agent_id}] received {msg.msg_type.value} from {msg.from_agent}")

    def poll(self, limit: int = 50) -> List[LoreMessage]:
        """
        Read and return pending inbox messages (non-destructive).
        Messages stay in inbox until acknowledged.
        """
        msgs = []
        with self._lock:
            for p in sorted(self.inbox_dir.glob("*.json"))[:limit]:
                try:
                    msgs.append(LoreMessage.from_json(p.read_text(encoding="utf-8")))
                except Exception as e:
                    logger.warning(f"[LoreNode:{self.agent_id}] bad inbox file {p.name}: {e}")
        return msgs

    def acknowledge(self, msg_id: str, result: Optional[Dict] = None, error: Optional[str] = None) -> None:
        """Mark a message as processed; archive to processed/."""
        src = self.inbox_dir / f"{msg_id}.json"
        if not src.exists():
            return
        with self._lock:
            msg = LoreMessage.from_json(src.read_text(encoding="utf-8"))
            msg.status = "error" if error else "done"
            msg.result = result
            msg.error  = error
            dst = self.processed_dir / f"{msg_id}.json"
            dst.write_text(msg.to_json(), encoding="utf-8")
            src.unlink()

    # ── Handler dispatch ─────────────────────────────────────────────────────

    async def dispatch(self, msg: LoreMessage) -> None:
        """Invoke the registered handler for this message type, if any."""
        handler = self._handlers.get(msg.msg_type)
        if handler:
            try:
                result = await handler(msg)
                self.acknowledge(msg.msg_id, result=result)
            except Exception as e:
                logger.error(f"[LoreNode:{self.agent_id}] handler error for {msg.msg_type.value}: {e}")
                self.acknowledge(msg.msg_id, error=str(e))

    # ── Heartbeat ────────────────────────────────────────────────────────────

    def heartbeat(self) -> None:
        """Write presence record to heartbeat directory."""
        hb_file = self.net_root / "heartbeat" / f"{self.agent_id}.json"
        hb_file.write_text(json.dumps({
            "agent_id":  self.agent_id,
            "family":    self.metadata.get("family", ""),
            "role":      self.metadata.get("role", ""),
            "dimension": self.metadata.get("dimension", ""),
            "last_seen": datetime.utcnow().isoformat(),
            "peers":     self.metadata.get("peers", []),
        }, indent=2), encoding="utf-8")

    # ── Outbox drain (used by router) ────────────────────────────────────────

    async def drain_outbox(self) -> List[LoreMessage]:
        """Drain in-memory outbox queue. Returns all queued messages."""
        msgs = []
        while not self._outbox.empty():
            try:
                msgs.append(self._outbox.get_nowait())
            except asyncio.QueueEmpty:
                break

        # Also pick up any file-based outbox entries (from send_sync)
        for p in sorted(self.outbox_dir.glob("*.json")):
            try:
                msg = LoreMessage.from_json(p.read_text(encoding="utf-8"))
                if not any(m.msg_id == msg.msg_id for m in msgs):
                    msgs.append(msg)
            except Exception:
                pass
        return msgs

    def clear_outbox_file(self, msg_id: str) -> None:
        """Remove a message from the file-based outbox after routing."""
        f = self.outbox_dir / f"{msg_id}.json"
        if f.exists():
            f.unlink()

    def __repr__(self) -> str:
        family = self.metadata.get("family", "?")
        role   = self.metadata.get("role", "?")
        return f"<LoreNode {self.agent_id} [{family}/{role}]>"
