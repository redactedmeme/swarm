# python/committee_engine.py
#
# Back-compat shim. Live LLM deliberation now lives in core/moe_committee.py
# (reconciled: 7 voices from agents/characters/sevenfold/, 71% weighted
# supermajority on every path — this module previously loaded voices from
# nodes/SevenfoldCommittee.json via a separate multi-provider LLM backend).
#
# Kept so existing call sites (services/web/tool_dispatch.py) keep working
# unchanged.

import sys
from pathlib import Path


from swarm_core.engine.moe_committee import deliberate  # noqa: E402, F401

__all__ = ["deliberate"]
