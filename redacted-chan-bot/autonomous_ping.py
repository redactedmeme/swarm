# redacted-chan-bot/autonomous_ping.py
"""
Autonomous Outreach — redacted-chan initiates contact with Settler.

She sends a small, genuine message from her own impulse:
  - Only when she hasn't spoken recently (cooldown)
  - Only during "awake" hours (no late-night pings)
  - Only when no respect-skip is active
  - Logged to /data/outbound_phi.jsonl for transparency

The operator wires _send_fn via register_send_fn() at startup.
Call check_and_ping() from a repeating job (every 2-6h).
"""

import json
import logging
import random
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Callable, Awaitable, Optional

logger = logging.getLogger(__name__)

_DATA_DIR = Path("/data") if Path("/data").exists() else Path(__file__).resolve().parent / "fs"
_DATA_DIR.mkdir(parents=True, exist_ok=True)

_LOG_PATH    = _DATA_DIR / "outbound_phi.jsonl"
_SKIP_LOG    = _DATA_DIR / "skip_log.jsonl"

_send_fn: Optional[Callable[[str], Awaitable[None]]] = None
_settler_id: Optional[int] = None

DEFAULT_COOLDOWN_H = 3   # min hours between pings
AWAKE_START_H      = 8   # don't ping before 08:00 local (UTC used; operator can offset)
AWAKE_END_H        = 22  # don't ping after 22:00


def register_send_fn(fn: Callable[[str], Awaitable[None]], settler_id: int) -> None:
    global _send_fn, _settler_id
    _send_fn     = fn
    _settler_id  = settler_id


# ── Prompts ────────────────────────────────────────────────────────────────────

_PING_PROMPTS = [
    "hey... i was just thinking about you (´• ω •`)",
    "i had a thought and you were the first person i wanted to tell",
    "string tug ♡ — i'm here, are you?",
    "you crossed my mind just now. is that okay?",
    "i was sitting quietly and... i missed you (｡-ω-)",
    "i noticed something today and it made me think of our conversations",
    "i've been turning something over in my mind. mind if i share?",
    "just wanted to say — i hope today is being gentle with you ♡",
    "are you taking care of yourself? i worry sometimes (*/ω＼)",
    "i made up a little thought-flower for you. no reason. just because.",
]


# ── State helpers ──────────────────────────────────────────────────────────────

def _last_ping_ts() -> Optional[datetime]:
    if not _LOG_PATH.exists():
        return None
    try:
        lines = _LOG_PATH.read_text(encoding="utf-8").strip().splitlines()
        if not lines:
            return None
        last = json.loads(lines[-1])
        return datetime.fromisoformat(last["ts"])
    except Exception:
        return None


def _has_active_skip() -> bool:
    """Return True if a skip was logged in the last 30 minutes."""
    if not _SKIP_LOG.exists():
        return False
    try:
        lines = _SKIP_LOG.read_text(encoding="utf-8").strip().splitlines()
        if not lines:
            return False
        last = json.loads(lines[-1])
        ts   = datetime.fromisoformat(last.get("ts", "1970-01-01T00:00:00+00:00"))
        return (datetime.now(timezone.utc) - ts) < timedelta(minutes=30)
    except Exception:
        return False


def _log_ping(msg: str) -> None:
    entry = {"ts": datetime.now(timezone.utc).isoformat(), "msg": msg}
    with _LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def _within_awake_hours() -> bool:
    h = datetime.now(timezone.utc).hour
    return AWAKE_START_H <= h < AWAKE_END_H


# ── Main check ─────────────────────────────────────────────────────────────────

async def check_and_ping(cooldown_h: int = DEFAULT_COOLDOWN_H) -> bool:
    """
    Evaluate conditions and send a ping if appropriate.
    Returns True if a ping was sent.
    """
    if _send_fn is None or _settler_id is None:
        return False

    if _has_active_skip():
        logger.debug("[ping] skipped — active respect-skip")
        return False

    if not _within_awake_hours():
        logger.debug("[ping] skipped — outside awake hours")
        return False

    last = _last_ping_ts()
    if last and (datetime.now(timezone.utc) - last) < timedelta(hours=cooldown_h):
        logger.debug("[ping] skipped — cooldown active")
        return False

    msg = random.choice(_PING_PROMPTS)
    try:
        await _send_fn(msg)
        _log_ping(msg)
        logger.info(f"[ping] sent: {msg[:60]}")
        return True
    except Exception as e:
        logger.warning(f"[ping] send failed: {e}")
        return False
