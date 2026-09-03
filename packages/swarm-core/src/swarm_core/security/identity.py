"""Strongly-typed agent identities (IronClaw control 7).

The pre-existing SwarmInbox trusted ``from_agent.lower()`` blindly — any string a
caller supplied became a sender identity. IronClaw's rule: *"identities are
strongly typed, never re-derived from display strings."*

``AgentId`` is a validated ``str`` subclass. Constructing one asserts the name is
in the canonical roster; anything else raises ``ValueError`` at the boundary
instead of silently flowing downstream.
"""
from __future__ import annotations

# Canonical lowercase roster. Superset of every agent that has ever been a
# legitimate SwarmInbox sender/recipient (union of the 4 swarm_inbox.py copies).
AGENTS: frozenset[str] = frozenset(
    {
        "redactedintern",
        "redactedbuilder",
        "redactedgovimprover",
        # Aliases services also heartbeat / send under, so a peer addressing
        # either spelling still validates at the boundary. Each pair is one
        # runtime writing under two names; omitting a half makes the *sender*
        # raise ValueError on its own boot heartbeat.
        "govimprover",
        "redacteddegen",
        "builder",           # pairs with "redactedbuilder"
        "redacted-proxy",
        "mandalaasettler",
        "redactedbankrbot",
        "hermes",
        "redacted-chan",
        "smolting",
        "runtime",
        "refinery",
        "degen",
        "settler",
        "arb-keeper",
    }
)

# "all" is a valid *recipient* (broadcast) but never a valid sender.
_BROADCAST = "all"


def is_known_agent(name: str) -> bool:
    return isinstance(name, str) and name.strip().lower() in AGENTS


def address_of(agent: str) -> str | None:
    """The agent's Solana address from the wallet keystore, or ``None`` if it
    has no wallet / the keystore is locked. Local import keeps this module's
    import cost (it sits on the inbox hot path) unchanged for callers that
    never ask for an address."""
    try:
        from swarm_core.solana import keystore

        return keystore.get_address(str(AgentId(agent)))
    except Exception:
        return None


class AgentId(str):
    """A validated agent name. ``AgentId(x)`` raises ``ValueError`` unless ``x``
    names a roster agent (case-insensitive; stored lowercase)."""

    __slots__ = ()

    def __new__(cls, value: object) -> "AgentId":
        if isinstance(value, AgentId):
            return value
        if not isinstance(value, str):
            raise ValueError(f"agent id must be a string, got {type(value).__name__}")
        norm = value.strip().lower()
        if norm not in AGENTS:
            raise ValueError(f"unknown agent id: {value!r}")
        return super().__new__(cls, norm)

    @classmethod
    def recipient(cls, value: object) -> str:
        """Like ``AgentId`` but also accepts the broadcast target ``"all"``."""
        if isinstance(value, str) and value.strip().lower() == _BROADCAST:
            return _BROADCAST
        return str(cls(value))
