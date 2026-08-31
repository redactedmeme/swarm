"""Compatibility shim — re-exports the canonical SwarmInbox.

The real implementation is ``swarm_core.security.inbox`` (HMAC-signed,
roster-validated, Redis + file fallback, ``SWARM_INBOX_ENFORCE`` staging).
This module used to be a hand-synced copy in every bot; the copies drifted.
Import sites (``import swarm_inbox`` / ``from swarm_inbox import ...``) are
unchanged.
"""
from swarm_core.security.inbox import *  # noqa: F401,F403
from swarm_core.security.inbox import (  # noqa: F401  keep names that * may skip
    AGENTS,
    MSG_TYPES,
    STATUS_PENDING,
    STATUS_PROCESSING,
    STATUS_DONE,
    STATUS_ERROR,
    RETENTION_DAYS,
    write_message,
    read_pending,
    read_results,
    get_message,
    claim_message,
    complete_message,
    deploy_request,
    request_countersign,
    submit_countersignature,
    governance_request,
    heartbeat,
    inbox_summary,
    format_inbox_status,
    recent_messages,
    prune_old_messages,
    verify_doc,
    sign_doc,
)
