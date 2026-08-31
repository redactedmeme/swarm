"""Re-export of the canonical task client.

The real implementation lives in ``swarm_tg.task_client`` (installed via
``pip install -e packages/swarm-tg``). This module used to be a hand-synced
byte-for-byte copy in every bot; it now just forwards, so there is one source
of truth. Import sites (``from task_client import TaskClient, ...``) are
unchanged.
"""
from swarm_tg.task_client import *  # noqa: F401,F403
from swarm_tg.task_client import (  # noqa: F401  explicit re-exports
    TaskClient,
    publish_capabilities,
    get_capabilities,
    AGENT_CAPABILITIES,
)
