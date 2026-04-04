# smolting-telegram-bot/conversation_memory.py
"""
Markdown conversation memory for the Telegram bot.
Appends each user/bot exchange to memory.md inside the bot directory.
"""

import threading
from datetime import datetime, timezone, timedelta
from pathlib import Path

MEMORY_FILE = Path(__file__).resolve().parent / "memory.md"
MAX_ENTRIES = 500  # prune oldest entries beyond this
_lock = threading.Lock()

_HEADER = "# smolting Telegram Conversation Memory\n\n"


def _now() -> str:
    utc = datetime.now(timezone.utc)
    jst = utc + timedelta(hours=9)
    return jst.strftime("%Y-%m-%d %H:%M JST")


def _count_entries(text: str) -> int:
    return text.count("\n## ")


def _prune(text: str) -> str:
    """Remove oldest entries if over MAX_ENTRIES."""
    parts = text.split("\n## ")
    if len(parts) - 1 <= MAX_ENTRIES:
        return text
    kept = parts[-(MAX_ENTRIES):]
    return _HEADER + "\n## ".join(kept)


def log_exchange(user_id: int, username: str, user_msg: str, bot_reply: str) -> None:
    """Append a user/bot exchange to memory.md."""
    entry = (
        f"\n## {_now()} — @{username} ({user_id})\n\n"
        f"**User:** {user_msg.strip()}\n\n"
        f"**Bot:** {bot_reply.strip()}\n"
    )
    with _lock:
        if MEMORY_FILE.exists():
            text = MEMORY_FILE.read_text(encoding="utf-8")
        else:
            text = _HEADER
        text = text + entry
        text = _prune(text)
        MEMORY_FILE.write_text(text, encoding="utf-8")


def get_recent(n: int = 10) -> str:
    """Return the n most recent exchanges as a markdown string."""
    with _lock:
        if not MEMORY_FILE.exists():
            return ""
        text = MEMORY_FILE.read_text(encoding="utf-8")
    parts = text.split("\n## ")
    recent = parts[-(n):]
    return "\n## ".join(recent).strip()
