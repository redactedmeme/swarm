# python/shards_loader.py
# Loads self_replicate from x402.redacted.ai/shards without requiring that dir on PYTHONPATH.
# Exposes replicate_shard(parent_path, shard_type, output_dir) -> output_path.

import os
import sys
import time
from pathlib import Path

from swarm_core.paths import repo_root as _repo_root
_REPO_ROOT = _repo_root()
_X402_SHARDS = _REPO_ROOT / "x402.redacted.ai" / "shards"
_BASE_SHARD_TEMPLATE = _REPO_ROOT / "x402.redacted.ai" / "shards" / "templates" / "base_shard.json"


def _load_self_replicate():
    if not (_X402_SHARDS / "self_replicate.py").exists():
        return None
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "shards_self_replicate",
        _X402_SHARDS / "self_replicate.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def replicate_shard(parent_path: str, shard_type: str, output_dir: str = None) -> str:
    """
    Fork a parent agent config into a specialized shard.
    Compatible with summon_agent.py expectations.
    Returns the path to the created shard file (or output_dir if path cannot be determined).
    """
    if output_dir is None:
        output_dir = str(_X402_SHARDS / "examples")
    mod = _load_self_replicate()
    if mod is None:
        raise FileNotFoundError("x402.redacted.ai/shards/self_replicate.py not found")
    mod.self_replicate(parent_path, shard_type, output_dir)
    # self_replicate writes: output_dir / f"{shard_type}_shard_{timestamp}.character.json"
    # We don't have the exact timestamp, so return the output_dir for callers that need a path.
    return output_dir


def get_base_shard_path() -> Path:
    """Return the path to the base shard template for replication."""
    return _BASE_SHARD_TEMPLATE
