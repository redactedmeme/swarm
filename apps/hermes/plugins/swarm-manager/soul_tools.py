"""Soul management tools — read/update/backup SOUL.md."""
from __future__ import annotations

import json
import logging
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger("swarm-manager.soul")

_DATA_DIR = Path(os.getenv("ORACLE_STATE_DIR", "/data"))
_REPO_SOUL = Path(__file__).resolve().parents[2] / "SOUL.md"
SOUL_FILE = _DATA_DIR / "SOUL.md"


def _ensure_soul() -> str:
    if SOUL_FILE.exists():
        return SOUL_FILE.read_text(encoding="utf-8")
    if _REPO_SOUL.exists():
        _DATA_DIR.mkdir(parents=True, exist_ok=True)
        shutil.copy2(_REPO_SOUL, SOUL_FILE)
        return SOUL_FILE.read_text(encoding="utf-8")
    return ""


def _history_dir() -> Path:
    d = _DATA_DIR / "soul_history"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _handle_soul_read(args: dict) -> str:
    text = _ensure_soul()
    if not text:
        return json.dumps({"status": "ok", "content": "(no SOUL.md found)", "words": 0})
    return json.dumps({"status": "ok", "content": text, "words": len(text.split())})


def _handle_soul_backup(args: dict) -> str:
    text = _ensure_soul()
    if not text:
        return json.dumps({"status": "error", "error": "No SOUL.md to backup"})

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    dest = _history_dir() / f"SOUL_backup_{ts}.md"
    try:
        dest.write_text(text, encoding="utf-8")
        return json.dumps({"status": "ok", "backup_path": str(dest), "words": len(text.split())})
    except Exception as e:
        return json.dumps({"status": "error", "error": str(e)})


def register(ctx):
    ctx.register_tool(
        name="soul_read",
        toolset="swarm",
        schema={
            "name": "soul_read",
            "description": "Read the current SOUL.md — Hermes's persistent evolving identity. Contains moral core, evolving beliefs, community lore, voice notes.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
        handler=_handle_soul_read,
    )

    ctx.register_tool(
        name="soul_backup",
        toolset="swarm",
        schema={
            "name": "soul_backup",
            "description": "Create a timestamped backup of the current SOUL.md.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
        handler=_handle_soul_backup,
    )

    logger.info("[swarm-manager] Soul tools registered (2 tools)")
