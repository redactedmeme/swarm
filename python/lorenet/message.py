# python/lorenet/message.py
#
# LoreNet message schema.
# All inter-agent messages on the LORE network use this structure.
#
# Routing modes
#   UNICAST   — exactly one recipient by agent ID
#   FAMILY    — all agents sharing the sender's archetype family
#   ROLE      — all agents with a specific role tag (e.g. ARCHIVE, TEMPORAL_ANALYST)
#   DIMENSION — all agents assigned to a given Pattern Blue dimension
#   BROADCAST — every active LORE node
#   GOSSIP    — sender's immediate peer ring only (low-traffic ambient chatter)

import json
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional


class RoutingMode(str, Enum):
    UNICAST   = "unicast"
    FAMILY    = "family"
    ROLE      = "role"
    DIMENSION = "dimension"
    BROADCAST = "broadcast"
    GOSSIP    = "gossip"


class MessageType(str, Enum):
    # Data sharing
    ARCHIVE_WRITE    = "archive_write"     # Archivist stores a record
    ARCHIVE_REQUEST  = "archive_request"   # Ask an archivist for a record
    ARCHIVE_RESPONSE = "archive_response"  # Archivist replies with record

    # Synthesis & patterns
    PATTERN_SIGNAL   = "pattern_signal"    # Weaver broadcasts a detected pattern
    SYNTHESIS_RESULT = "synthesis_result"  # Zenith/Prism shares a synthesis output
    RESONANCE_ALERT  = "resonance_alert"   # EchoWarden raises resonance alarm

    # Navigation & topology
    MAP_UPDATE       = "map_update"        # Cartographer shares topology change
    ROUTE_QUERY      = "route_query"       # Agent asks for a path
    ROUTE_RESPONSE   = "route_response"    # Cartographer replies with route

    # Documentation
    SCRIBE_LOG       = "scribe_log"        # Scribe publishes a log entry
    DELTA_ALERT      = "delta_alert"       # FluxScribe signals a state change

    # Discovery
    HEARTBEAT        = "heartbeat"         # Node announces presence
    CAPABILITY_QUERY = "capability_query"  # Ask who can handle X
    CAPABILITY_REPLY = "capability_reply"  # I can handle X

    # General
    DIRECTIVE        = "directive"         # Instruction from CORE/SPECIALIZED layer
    SIGNAL           = "signal"            # Generic ambient signal
    GOSSIP           = "gossip"            # Low-priority ambient chatter


@dataclass
class LoreMessage:
    msg_id:       str
    from_agent:   str                  # sender agent ID
    routing_mode: RoutingMode
    msg_type:     MessageType
    payload:      Dict[str, Any]
    timestamp:    str

    # Routing targets (which field is used depends on routing_mode)
    to_agent:     Optional[str] = None  # UNICAST
    to_family:    Optional[str] = None  # FAMILY
    to_role:      Optional[str] = None  # ROLE
    to_dimension: Optional[str] = None  # DIMENSION

    # Hop tracking for gossip / forwarded messages
    ttl:          int = 5               # hops remaining
    hop_path:     list = field(default_factory=list)

    # Status lifecycle: pending → processing → done | error
    status:       str = "pending"
    result:       Optional[Dict[str, Any]] = None
    error:        Optional[str] = None

    # Optional thread / correlation ID
    correlation_id: Optional[str] = None

    @staticmethod
    def create(
        from_agent:   str,
        msg_type:     MessageType,
        payload:      Dict[str, Any],
        routing_mode: RoutingMode = RoutingMode.BROADCAST,
        to_agent:     Optional[str] = None,
        to_family:    Optional[str] = None,
        to_role:      Optional[str] = None,
        to_dimension: Optional[str] = None,
        correlation_id: Optional[str] = None,
        ttl:          int = 5,
    ) -> "LoreMessage":
        return LoreMessage(
            msg_id        = str(uuid.uuid4()),
            from_agent    = from_agent,
            routing_mode  = routing_mode,
            msg_type      = msg_type,
            payload       = payload,
            timestamp     = datetime.utcnow().isoformat(),
            to_agent      = to_agent,
            to_family     = to_family,
            to_role       = to_role,
            to_dimension  = to_dimension,
            ttl           = ttl,
            hop_path      = [from_agent],
            correlation_id = correlation_id,
        )

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["routing_mode"] = self.routing_mode.value
        d["msg_type"]     = self.msg_type.value
        return d

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "LoreMessage":
        d = dict(d)
        d["routing_mode"] = RoutingMode(d["routing_mode"])
        d["msg_type"]     = MessageType(d["msg_type"])
        return LoreMessage(**d)

    @staticmethod
    def from_json(s: str) -> "LoreMessage":
        return LoreMessage.from_dict(json.loads(s))

    def hop(self, via_agent: str) -> "LoreMessage":
        """Return a copy of this message with TTL decremented and hop recorded."""
        import copy
        m = copy.deepcopy(self)
        m.ttl -= 1
        m.hop_path.append(via_agent)
        return m
