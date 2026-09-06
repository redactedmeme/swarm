"""
REDACTED Swarm Manager plugin for Hermes Agent.

Registers custom tools for:
- SwarmInbox (Redis message queue) — read/send/complete messages
- Railway ops — deploy, status, logs, restart services
- Task audit — JSONL logging of all operations
- Health monitoring — agent heartbeat sweep + auto-recovery
- Soul management — read/update/backup SOUL.md
- Web — web_fetch / web_search (SSRF-guarded), always on
- Skill recall — skill_recall against skill_memory, always on
- X/Twitter — registered only when credentials resolve; writes are
  `social.post` capability-gated + approval-gated
- Code execution — python_exec via apps/exec-runner unix socket, off unless
  EXEC_ENABLED=true
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
    from . import web_tools
    from . import skill_tools

    inbox_tools.register(ctx)
    railway_tools.register(ctx)
    audit_tools.register(ctx)
    health_tools.register(ctx)
    soul_tools.register(ctx)

    # Web + skill recall — documented Hermes capabilities, no external blast radius.
    web_tools.register(ctx)
    skill_tools.register(ctx)

    # X/Twitter — only when credentials actually resolve via the secrets layer.
    # The outward-facing writes (x_post/x_reply/x_like) are additionally gated on
    # the `social.post` capability + a live approval token in their handlers.
    try:
        from . import x_tools
        if x_tools.x_credentials_present():
            x_tools.register(ctx)
        else:
            logger.info("[swarm-manager] X tools skipped — credentials not configured")
    except Exception as e:  # pragma: no cover
        logger.warning("[swarm-manager] X tools not registered: %s", e)

    # Code execution — routed to apps/exec-runner over a unix socket. Registration
    # is gated: off unless an operator sets EXEC_ENABLED=true.
    if os.getenv("EXEC_ENABLED", "false").lower() == "true":
        from . import exec_tools
        exec_tools.register(ctx)
    else:
        logger.info("[swarm-manager] Exec tools skipped — set EXEC_ENABLED=true to enable")

    # Persistent workspace (fs + shell + browser) via apps/workspace unix socket.
    # Off unless WORKSPACE_ENABLED=true. workspace_shell / workspace_browse are
    # additionally capability + approval gated in their handlers.
    if os.getenv("WORKSPACE_ENABLED", "false").lower() == "true":
        from . import workspace_tools
        workspace_tools.register(ctx)
    else:
        logger.info("[swarm-manager] Workspace tools skipped — set WORKSPACE_ENABLED=true to enable")

    logger.info("[swarm-manager] Plugin loaded — all tools registered")
