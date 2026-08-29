"""Periodic liveness sweep — edge-triggered alerting.

Log-only for now: on a state transition (healthy->stale, stale->recovered, or a
queue crossing its depth threshold) we emit a log line via _emit(). Steady state
is silent — we alert on edges, not every tick, so logs stay quiet when healthy.

_emit() is the single delivery seam. A future Telegram sender slots in here
without touching the rule logic, e.g.:

    requests.post(f"https://api.telegram.org/bot{ALERT_BOT_TOKEN}/sendMessage",
                  json={"chat_id": ALERT_CHAT_ID, "text": msg}, timeout=10)

No raw-HTTP Telegram helper exists in the repo yet (all bots use
python-telegram-bot); when wired, ALERT_BOT_TOKEN / ALERT_CHAT_ID gate it.
"""
from __future__ import annotations

import logging
import os
from typing import Any

import liveness

logger = logging.getLogger("refinery.alerting")

STALE_THRESHOLD_SEC = int(os.getenv("STALE_THRESHOLD_SEC", "300"))
QUEUE_DEPTH_ALERT = int(os.getenv("QUEUE_DEPTH_ALERT", "200"))

# last known alert state per key so we only fire on transitions.
#   agent:{id}  -> True when currently stale
#   queue:{id}  -> True when currently over depth
_state: dict[str, bool] = {}


def _emit(msg: str, recovered: bool = False) -> None:
    """Single delivery seam. Log-only today; Telegram sender drops in here."""
    if recovered:
        logger.info("[alert] %s", msg)
    else:
        logger.warning("[alert] %s", msg)


def _is_stale(agent: dict[str, Any]) -> bool:
    if not agent.get("present"):
        return True
    age = agent.get("age_s")
    if age is None:
        return True
    return age > STALE_THRESHOLD_SEC


def _transition(key: str, active: bool, on_msg: str, off_msg: str) -> None:
    """Emit only when `active` flips relative to remembered state."""
    was = _state.get(key, False)
    if active and not was:
        _emit(on_msg)
    elif not active and was:
        _emit(off_msg, recovered=True)
    _state[key] = active


def alert_sweep() -> None:
    """Scheduled job: snapshot liveness and log edge transitions."""
    try:
        snap = liveness.collect_liveness()
    except Exception as e:
        logger.exception("[alert] liveness snapshot failed: %s", e)
        return

    for agent_id, a in snap.get("agents", {}).items():
        stale = _is_stale(a)
        age = a.get("age_s")
        age_str = "no heartbeat" if age is None else f"{age}s ago"
        _transition(
            f"agent:{agent_id}",
            stale,
            on_msg=f"{agent_id} STALE (last seen {age_str}, pending={a.get('pending')})",
            off_msg=f"{agent_id} recovered (last seen {age_str})",
        )

        depth = int(a.get("pending") or 0)
        _transition(
            f"queue:{agent_id}",
            depth > QUEUE_DEPTH_ALERT,
            on_msg=f"{agent_id} queue backed up: pending={depth} (>{QUEUE_DEPTH_ALERT})",
            off_msg=f"{agent_id} queue drained: pending={depth}",
        )
