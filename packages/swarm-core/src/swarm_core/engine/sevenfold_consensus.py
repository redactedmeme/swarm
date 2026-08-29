# core/sevenfold_consensus.py
#
# Back-compat shim. The deterministic committee vote now lives in
# core/moe_committee.py (reconciled: 7 voices from agents/characters/sevenfold/,
# 71% weighted supermajority — previously this module used a 4/7 ≈ 57%
# majority-count threshold, which diverged from the LLM committee's 71%).
#
# Kept so existing call sites (core/swarm_engine.py) keep working unchanged.

from swarm_core.engine.moe_committee import run_consensus, format_votes  # noqa: F401

__all__ = ["run_consensus", "format_votes"]
