"""
hermes_dispatch.py — Send operational instructions to Hermes via SwarmInbox.

redacted-chan uses this to delegate tasks to Hermes (the swarm manager).
Hermes receives task_request messages, executes them using its tools,
and returns task_result messages that we poll here.
"""
from __future__ import annotations

import json
import logging
import re
import time as _time
from pathlib import Path
from typing import Optional

logger = logging.getLogger("hermes_dispatch")

HERMES_AGENT = "hermes"
SELF_AGENT = "redacted-chan"

# ── Pending task tracking ─────────────────────────────────────────────────────

_DATA_DIR = Path("/data") if Path("/data").exists() else Path(__file__).parent / "fs"
_PENDING_PATH = _DATA_DIR / "hermes_pending.jsonl"


def track_pending(msg_id: str, task_type: str, instruction: str) -> None:
    """Log a dispatched task as pending."""
    try:
        _DATA_DIR.mkdir(parents=True, exist_ok=True)
        entry = {
            "msg_id": msg_id,
            "task_type": task_type,
            "instruction": instruction[:200],
            "sent_at": _time.time(),
            "timed_out": False,
            "resolved": False,
        }
        with open(_PENDING_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception:
        pass


def mark_resolved(msg_id: str) -> None:
    """Mark a pending task as resolved (result received inline)."""
    _update_pending(msg_id, resolved=True)


def mark_timed_out(msg_id: str) -> None:
    """Mark a pending task as timed out (needs proactive follow-up)."""
    _update_pending(msg_id, timed_out=True)


def get_timed_out_tasks() -> list:
    """Return tasks that timed out inline and still need proactive follow-up."""
    if not _PENDING_PATH.exists():
        return []
    try:
        entries = [json.loads(l) for l in _PENDING_PATH.read_text(encoding="utf-8").splitlines() if l.strip()]
        cutoff = _time.time() - 86400  # 24h
        return [e for e in entries if e.get("timed_out") and not e.get("resolved") and e.get("sent_at", 0) > cutoff]
    except Exception:
        return []


def _update_pending(msg_id: str, **kwargs) -> None:
    if not _PENDING_PATH.exists():
        return
    try:
        entries = [json.loads(l) for l in _PENDING_PATH.read_text(encoding="utf-8").splitlines() if l.strip()]
        for e in entries:
            if e.get("msg_id") == msg_id:
                e.update(kwargs)
        _PENDING_PATH.write_text("\n".join(json.dumps(e) for e in entries) + "\n", encoding="utf-8")
    except Exception:
        pass

# Lazy import to avoid circular deps at module load
_inbox = None

def _get_inbox():
    global _inbox
    if _inbox is None:
        try:
            import swarm_inbox
            _inbox = swarm_inbox
        except ImportError:
            logger.warning("[hermes_dispatch] swarm_inbox not available")
    return _inbox


async def send_to_hermes(
    task_type: str,
    instruction: str,
    service: Optional[str] = None,
    params: Optional[dict] = None,
    context: Optional[dict] = None,
) -> Optional[str]:
    """Send a task_request to Hermes. Returns msg_id or None."""
    inbox = _get_inbox()
    if not inbox:
        return None
    payload = {
        "task_type": task_type,
        "instruction": instruction,
    }
    if service:
        payload["service"] = service
    if params:
        payload["params"] = params
    if context:
        payload["context"] = context
    msg_id = inbox.write_message(SELF_AGENT, HERMES_AGENT, "task_request", payload)
    logger.info("[hermes_dispatch] Sent %s to hermes: %s (msg_id=%s)", task_type, instruction[:80], msg_id)
    return msg_id


def check_results() -> list[dict]:
    """Poll completed task_result messages from Hermes."""
    inbox = _get_inbox()
    if not inbox:
        return []
    return inbox.read_results(sent_by=SELF_AGENT)


# ── [HERMES: ...] marker extraction ─────────────────────────────────────────

_HERMES_PATTERN = re.compile(
    r'\[HERMES:\s*([^|]+?)\s*\|\s*(.+?)\]',
    re.IGNORECASE,
)

TASK_TYPE_ALIASES = {
    "status": "status",
    "check": "status",
    "logs": "logs",
    "log": "logs",
    "restart": "restart",
    "reboot": "restart",
    "deploy": "deploy",
    "push": "deploy",
    "exec": "general",
    "run": "general",
    "compute": "general",
    "general": "general",
}


def extract_hermes_markers(text: str) -> tuple[str, list[dict]]:
    """
    Extract [HERMES: task_type | instruction] markers from LLM response text.

    Returns (cleaned_text, list_of_tasks).
    Each task is {"task_type": ..., "instruction": ..., "service": ...}.
    """
    tasks = []
    for match in _HERMES_PATTERN.finditer(text):
        raw_type = match.group(1).strip().lower()
        instruction = match.group(2).strip()
        task_type = TASK_TYPE_ALIASES.get(raw_type, "general")

        service = None
        for svc_name in [
            "redacted-chan-bot", "smolting-telegram-bot", "hermes-bot",
            "swarm-runtime", "redactedbuilder-bot", "redacted-website",
            "redacted-dashboard",
        ]:
            if svc_name in instruction.lower():
                service = svc_name
                break

        tasks.append({
            "task_type": task_type,
            "instruction": instruction,
            "service": service,
        })

    cleaned = _HERMES_PATTERN.sub("", text).strip()
    return cleaned, tasks
