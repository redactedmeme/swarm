"""
REDACTED Swarm Manager plugin for Hermes Agent.

Registers custom tools for:
- SwarmInbox (Redis message queue) — read/send/complete messages
- Railway ops — deploy, status, logs, restart services
- Task audit — JSONL logging of all operations
- Health monitoring — agent heartbeat sweep + auto-recovery
- Soul management — read/update/backup SOUL.md
"""
from __future__ import annotations

import json
import logging
import os

logger = logging.getLogger("swarm-manager")


def register(ctx):
    """Called by Hermes plugin loader. Register all swarm tools."""
    from . import inbox_tools
    from . import railway_tools
    from . import audit_tools
    from . import health_tools
    from . import soul_tools

    inbox_tools.register(ctx)
    railway_tools.register(ctx)
    audit_tools.register(ctx)
    health_tools.register(ctx)
    soul_tools.register(ctx)

    logger.info("[swarm-manager] Plugin loaded — all tools registered")
