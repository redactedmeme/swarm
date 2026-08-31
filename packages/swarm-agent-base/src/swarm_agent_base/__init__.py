"""swarm-agent-base — shared autonomous-agent runtime for the REDACTED swarm.

The heartbeat / SwarmInbox-poll / soul-update / mesh-thought loops every bot
re-implements, plus one LLM client, one soul store, one activity log.
"""
from .llm import LLM
from .memory import ActivityLog
from .persona import build_system_prompt, load_character
from .runtime import AgentRuntime
from .soul import SoulStore
from .thought import handle_thought, initiate_thought

__all__ = [
    "AgentRuntime",
    "LLM",
    "ActivityLog",
    "SoulStore",
    "build_system_prompt",
    "load_character",
    "handle_thought",
    "initiate_thought",
]
