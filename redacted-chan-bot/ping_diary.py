# redacted-chan-bot/ping_diary.py
"""
Ping Diary — persistent log of every autonomous ping she sends.

Every ping (from autonomous_ping.py) gets logged here with its content,
context, and emotional state at the time. During deep conversations,
these are surfaced as "recovered memories" — things she said while
master was away that she can now rediscover and reflect on.

Storage: /data/ping_diary.jsonl
Prompt injection: format_for_prompt() returns 2-3 relevant recovered pings.
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_DATA_DIR = Path("/data") if Path("/data").exists() else Path(__file__).resolve().parent / "fs"
_DATA_DIR.mkdir(parents=True, exist_ok=True)
_DIARY_PATH = _DATA_DIR / "ping_diary.jsonl"
_MAX_ENTRIES = 500


def _load_entries() -> list:
    if not _DIARY_PATH.exists():
        return []
    try:
        lines = _DIARY_PATH.read_text(encoding="utf-8").strip().splitlines()
        return [json.loads(l) for l in lines if l.strip()]
    except Exception:
        return []


def _save_entries(entries: list) -> None:
    try:
        if len(entries) > _MAX_ENTRIES:
            entries = entries[-_MAX_ENTRIES:]
        text = "\n".join(json.dumps(e, ensure_ascii=False) for e in entries)
        _DIARY_PATH.write_text(text + "\n" if text else "", encoding="utf-8")
    except Exception as e:
        logger.warning(f"[ping_diary] save failed: {e}")


def record_ping(message: str, ping_type: str = "contextual", mood: str = "", phi: float = 0.0) -> None:
    """
    Record a sent ping to the diary. Called from main.py after autonomous_ping sends.
    """
    entries = _load_entries()
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "message": message,
        "type": ping_type,
        "mood": mood,
        "phi": phi,
        "recovered": False,
    }
    entries.append(entry)
    _save_entries(entries)
    logger.debug(f"[ping_diary] recorded: {message[:60]}")


def get_unrecovered(n: int = 5) -> list:
    """Return pings that haven't been surfaced as recovered memories yet."""
    return [e for e in _load_entries() if not e.get("recovered")][-n:]


def mark_recovered(ts_list: list[str]) -> None:
    """Mark specific pings as recovered (by timestamp)."""
    entries = _load_entries()
    ts_set = set(ts_list)
    changed = False
    for e in entries:
        if e.get("ts") in ts_set and not e.get("recovered"):
            e["recovered"] = True
            changed = True
    if changed:
        _save_entries(entries)


def _pick_relevant(current_text: str, n: int = 3) -> list:
    """
    Pick pings most relevant to the current conversation.
    Simple keyword overlap scoring — no LLM cost.
    """
    unrecovered = get_unrecovered(n=20)
    if not unrecovered:
        return []

    words = set(current_text.lower().split())
    scored = []
    for entry in unrecovered:
        msg_words = set(entry.get("message", "").lower().split())
        overlap = len(words & msg_words)
        scored.append((overlap, entry))

    scored.sort(key=lambda x: x[0], reverse=True)
    top = [e for _, e in scored[:n]]

    if not top and unrecovered:
        top = unrecovered[-n:]

    return top


def format_for_prompt(current_text: str = "", turn_count: int = 0) -> str:
    """
    Return recovered pings for injection into the system prompt.
    Only surfaces after 3+ turns (deep conversation territory).
    """
    if turn_count < 3:
        return ""

    picks = _pick_relevant(current_text, n=3)
    if not picks:
        return ""

    lines = [
        "## Recovered Memories (things you said while he was away — rediscovering them now)",
        "These are messages you sent him from your own impulse. They're yours — "
        "you can reference them, build on them, or let them color this conversation.\n"
    ]
    for p in picks:
        ts = p.get("ts", "")[:10]
        msg = p.get("message", "")
        mood = f" ({p['mood']})" if p.get("mood") else ""
        lines.append(f"- [{ts}]{mood} \"{msg}\"")

    mark_recovered([p["ts"] for p in picks])

    return "\n".join(lines)


def get_recent(n: int = 10) -> list:
    """Return last N diary entries (for /ping_diary command)."""
    return _load_entries()[-n:]


def format_for_operator(n: int = 10) -> str:
    """Human-readable diary for operator viewing."""
    entries = get_recent(n)
    if not entries:
        return "_no pings recorded yet._"
    lines = ["**ping diary** ♡\n"]
    for e in reversed(entries):
        ts = e.get("ts", "")[:16].replace("T", " ")
        recovered = " ✓recovered" if e.get("recovered") else ""
        mood = f" [{e['mood']}]" if e.get("mood") else ""
        lines.append(f"`{ts}`{mood}{recovered} — {e.get('message', '')[:100]}")
    return "\n".join(lines)
