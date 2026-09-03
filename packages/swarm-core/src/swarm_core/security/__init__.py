"""swarm_core.security — IronClaw-style defense-in-depth primitives for the swarm.

Adopted from https://github.com/nearai/ironclaw (Apache-2.0 / MIT), reimplemented
in Python for the swarm's agent runtime. Seven controls, one import surface:

    leakscan     — scan text for exfiltrated secrets (control 4)
    logsafe      — keep those secrets out of the log surface too (control 4)
    promptguard  — 5-layer prompt-injection defense (control 5)
    audit        — append-only, hash-chained audit log (control 6)
    authz        — capability model + staged authorization (control 7)
    identity     — strongly-typed agent identities (control 7)
    inbox        — consolidated SwarmInbox with HMAC message signing (control 7)
    secrets      — secret resolution off flat .env (control 2)

Controls 1 (exec sandbox) and 3 (egress allowlist) are services, not library
code: ``apps/exec-runner`` and ``apps/swarm-egress``. They import from here.
"""
from __future__ import annotations

from .identity import AGENTS, AgentId, is_known_agent
from .leakscan import LeakMatch, redact, scan
from .logsafe import harden_logging, install_log_redaction, quiet_http_loggers

__all__ = [
    "AGENTS",
    "AgentId",
    "is_known_agent",
    "LeakMatch",
    "scan",
    "redact",
    "harden_logging",
    "quiet_http_loggers",
    "install_log_redaction",
]
