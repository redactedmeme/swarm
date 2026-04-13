# smolting-telegram-bot/hermes_bridge.py
"""
Hermes file-queue integration for smolting-telegram-bot.

- Polls fs/swarm_messages/smolting-telegram-bot/ for Pattern Blue directives (from Hermes executor
  or SwarmMessageBridge), processes them, and writes responses to fs/swarm_messages/hermes-executor/.
- Optionally runs HermesDelegationExecutor (clawtask manifest → fs/clawtask_dispatch_results.json).

Set HERMES_FS_ROOT to override the fs/ directory (default: ./fs under bot dir, or ../fs from monorepo).
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


def hermes_fs_dir() -> Path:
    """Resolved .../fs used for swarm_messages, clawtasks manifest, dispatch results."""
    override = os.environ.get("HERMES_FS_ROOT", "").strip()
    if override:
        p = Path(override).expanduser().resolve()
        p.mkdir(parents=True, exist_ok=True)
        return p
    bot = Path(__file__).resolve().parent
    parent_fs = bot.parent / "fs"
    if parent_fs.is_dir():
        return parent_fs.resolve()
    cand = bot / "fs"
    cand.mkdir(parents=True, exist_ok=True)
    return cand.resolve()


def swarm_messages_base() -> Path:
    base = hermes_fs_dir() / "swarm_messages"
    base.mkdir(parents=True, exist_ok=True)
    for sub in (
        "smolting-telegram-bot",
        "hermes-executor",
        "redactedbuilder-bot",
        "redacted-terminal",
    ):
        (base / sub).mkdir(parents=True, exist_ok=True)
        proc = base / sub / "processed"
        proc.mkdir(exist_ok=True)
    return base


def clawtasks_manifest_path() -> Path:
    custom = os.environ.get("HERMES_CLAWTASK_MANIFEST", "").strip()
    if custom:
        return Path(custom).expanduser().resolve()
    return hermes_fs_dir() / "clawtasks_v1.json"


def clawtask_results_path() -> Path:
    custom = os.environ.get("HERMES_DISPATCH_OUTPUT", "").strip()
    if custom:
        return Path(custom).expanduser().resolve()
    return hermes_fs_dir() / "clawtask_dispatch_results.json"


def poll_directives_once() -> int:
    """Process pending directives; returns count processed."""
    from swarm_directive_consumer import SmoltingDirectiveConsumer

    base = str(swarm_messages_base())
    consumer = SmoltingDirectiveConsumer(queue_base=base)
    return consumer.consume_all()


def run_delegation_dispatch_sync() -> bool:
    """
    Load clawtasks manifest, dispatch_all, save JSON. Returns False if skipped or failed.
    """
    manifest = clawtasks_manifest_path()
    if not manifest.is_file():
        logger.debug("[hermes_bridge] No clawtask manifest at %s — skip delegation", manifest)
        return False

    repo_python = Path(__file__).resolve().parent.parent / "python"
    bot_python = Path(__file__).resolve().parent / "python"
    for p in (repo_python, bot_python):
        if p.is_dir() and str(p) not in sys.path:
            sys.path.insert(0, str(p))

    try:
        from hermes_delegation_executor import HermesDelegationExecutor
    except ImportError as e:
        logger.warning("[hermes_bridge] hermes_delegation_executor unavailable: %s", e)
        return False

    executor = HermesDelegationExecutor(str(manifest))
    if not executor.load_manifest():
        return False

    asyncio.run(executor.dispatch_all())
    executor.print_summary()
    out = clawtask_results_path()
    out.parent.mkdir(parents=True, exist_ok=True)
    return executor.save_results(str(out))


async def poll_directives_async() -> int:
    return await asyncio.to_thread(poll_directives_once)


async def run_delegation_async() -> bool:
    return await asyncio.to_thread(run_delegation_dispatch_sync)
