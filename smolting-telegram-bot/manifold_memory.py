# smolting-telegram-bot/manifold_memory.py
"""
ManifoldMemory: reads/writes spaces/ManifoldMemory.state.json.
Appends Telegram bot events to the shared swarm memory pool so other
agents (RedactedIntern, RedactedBuilder, etc.) can see what users asked.
"""

import json
import logging
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# MANIFOLD_PATH env var lets Railway volume override the default container path
BOT_DIR = Path(__file__).resolve().parent
_default_manifold = str(BOT_DIR.parent / "spaces" / "ManifoldMemory.state.json")
MANIFOLD_PATH = Path(os.getenv("MANIFOLD_PATH", _default_manifold))

# Max events kept in the file (oldest pruned beyond this)
MAX_EVENTS = 500

_lock = threading.Lock()


def _now_jst() -> str:
    """Return current UTC time formatted as JST label (matches existing file convention)."""
    now = datetime.now(timezone.utc)
    # Convert UTC → JST (+9)
    from datetime import timedelta
    jst = now + timedelta(hours=9)
    return jst.strftime("%Y-%m-%d %H:%M JST")


def _load() -> dict:
    """Load ManifoldMemory JSON, return empty scaffold if missing/corrupt."""
    if not MANIFOLD_PATH.exists():
        return {"events": [], "current_state": "", "last_saved_session": {}}
    try:
        with open(MANIFOLD_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"ManifoldMemory load error: {e}")
        return {"events": [], "current_state": "", "last_saved_session": {}}


def _save(data: dict) -> bool:
    """Write ManifoldMemory JSON atomically."""
    try:
        tmp = MANIFOLD_PATH.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        tmp.replace(MANIFOLD_PATH)
        return True
    except Exception as e:
        logger.error(f"ManifoldMemory save error: {e}")
        return False


def append_event(event: str) -> bool:
    """
    Thread-safe append of a single event string to ManifoldMemory.events.
    Prunes oldest events beyond MAX_EVENTS.
    """
    with _lock:
        data = _load()
        timestamp = _now_jst()
        entry = f"{timestamp} — {event}"
        events = data.get("events", [])
        events.append(entry)
        if len(events) > MAX_EVENTS:
            events = events[-MAX_EVENTS:]
        data["events"] = events
        return _save(data)


def update_state(state_summary: str) -> bool:
    """Overwrite current_state field with a new summary string."""
    with _lock:
        data = _load()
        data["current_state"] = state_summary
        return _save(data)


def save_session(session: dict) -> bool:
    """Overwrite last_saved_session with a new session dict."""
    with _lock:
        data = _load()
        data["last_saved_session"] = session
        return _save(data)


def get_recent_events(n: int = 10) -> list[str]:
    """Return the n most recent event strings (no write)."""
    with _lock:
        data = _load()
        return data.get("events", [])[-n:]


def get_current_state() -> str:
    """Return the current_state string."""
    with _lock:
        data = _load()
        return data.get("current_state", "")


# ── Sigil directory helpers ───────────────────────────────────────────────────
# spaces/ManifoldMemory/ (directory) — written by sigil_pact_aeon.py

SIGIL_DIR = BOT_DIR.parent / "spaces" / "ManifoldMemory"
SIGIL_FILE = SIGIL_DIR / "settlement_sigils.json"


def get_sigils(n: int = 10) -> list[dict]:
    """Return the n most recent sigil records from the sigil directory."""
    try:
        if not SIGIL_FILE.exists():
            return []
        with open(SIGIL_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        sigils = data.get("sigils", [])
        return sigils[-n:]
    except Exception as e:
        logger.debug(f"ManifoldMemory sigil read failed (non-fatal): {e}")
        return []


# ── Convenience log helpers ──────────────────────────────────────────────────

def log_command(user_id: int, username: str, command: str, detail: str = "") -> None:
    """Log a Telegram bot command invocation."""
    suffix = f": {detail}" if detail else ""
    event = f"[TG-bot] user={username}({user_id}) cmd={command}{suffix}"
    append_event(event)


def log_post(user_id: int, username: str, tweet_id: str, snippet: str) -> None:
    """Log a successful X post via ClawnX."""
    event = (
        f"[TG-bot] user={username}({user_id}) posted tweet_id={tweet_id} "
        f'snippet="{snippet[:60]}"'
    )
    append_event(event)


def log_summon(user_id: int, username: str, agent: str, result: str) -> None:
    """Log a swarm agent summon from Telegram."""
    event = f"[TG-bot] user={username}({user_id}) summoned agent={agent} → {result[:80]}"
    append_event(event)


def log_tap(user_id: int, username: str, tier: str, token_id: str) -> None:
    """Log a TAP token issuance."""
    event = f"[TG-bot] user={username}({user_id}) TAP tier={tier} token_id={token_id[:16]}…"
    append_event(event)
