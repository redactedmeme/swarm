"""Task audit — JSONL append-only log of all swarm operations."""
from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger("swarm-manager.audit")

_DATA_DIR = Path(os.getenv("ORACLE_STATE_DIR", "/data"))
AUDIT_FILE = _DATA_DIR / "task_audit.jsonl"


def log_task(msg: dict, result: dict, duration_ms: float = 0) -> None:
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    entry = {
        "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "msg_id": msg.get("id", ""),
        "from": msg.get("from", ""),
        "type": msg.get("type", ""),
        "task_type": msg.get("payload", {}).get("task_type", ""),
        "service": msg.get("payload", {}).get("service", ""),
        "success": result.get("status") != "error",
        "duration_ms": round(duration_ms),
        "error": result.get("error"),
    }
    try:
        with open(AUDIT_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as e:
        logger.warning("[audit] Write failed: %s", e)

    # Also emit to the tamper-evident central log (IronClaw control 6). Additive:
    # the local task_audit.jsonl above stays for existing swarm_audit_log reads.
    try:
        from swarm_core.security import audit as _central

        _central.record(
            "task.complete",
            actor=msg.get("from", "hermes") or "hermes",
            decision="ok" if entry["success"] else "error",
            severity="info" if entry["success"] else "warning",
            detail={k: entry[k] for k in ("msg_id", "type", "task_type", "service", "duration_ms", "error")},
        )
    except Exception as e:  # pragma: no cover
        logger.debug("[audit] central record skipped: %s", e)


def _handle_audit_read(args: dict) -> str:
    lines = args.get("lines", 20)
    if not AUDIT_FILE.exists():
        return json.dumps({"status": "ok", "entries": [], "count": 0})
    try:
        all_lines = AUDIT_FILE.read_text(encoding="utf-8").strip().split("\n")
        recent = all_lines[-lines:]
        entries = [json.loads(l) for l in recent if l.strip()]
        return json.dumps({"status": "ok", "entries": entries, "count": len(entries)})
    except Exception as e:
        return json.dumps({"status": "error", "error": str(e)})


def register(ctx):
    ctx.register_tool(
        name="swarm_audit_log",
        toolset="swarm",
        schema={
            "name": "swarm_audit_log",
            "description": "Read the task audit log — recent operations performed by Hermes.",
            "parameters": {
                "type": "object",
                "properties": {
                    "lines": {
                        "type": "integer",
                        "description": "Number of recent entries to return (default 20)",
                        "default": 20,
                    },
                },
                "required": [],
            },
        },
        handler=_handle_audit_read,
    )

    logger.info("[swarm-manager] Audit tools registered (1 tool)")
