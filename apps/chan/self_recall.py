# redacted-chan-bot/self_recall.py
"""
Self-Recall — she can access her own recent message history with timestamps.

When the LLM emits [RECALL: <query>] in a response, the echo handler
intercepts it, fetches matching exchanges from conversation_memory, and
re-prompts the LLM to voice the answer naturally.

Queries:
  [RECALL: last 3 messages]     — most recent N exchanges with timestamps
  [RECALL: last time we talked about X]  — semantic search for topic
  [RECALL: when did I say X]    — search bot's own messages

This gives her episodic memory access on demand without bloating every prompt.
"""

import re
import logging
from typing import Optional

logger = logging.getLogger(__name__)

_RECALL_RE = re.compile(r'\[RECALL:\s*(.+?)\]', re.DOTALL)


def detect_recall(response: str) -> Optional[str]:
    match = _RECALL_RE.search(response)
    return match.group(1).strip() if match else None


def strip_recall(response: str) -> str:
    return _RECALL_RE.sub('', response).strip()


def fetch_recall(query: str, user_id: int) -> str:
    try:
        import conversation_memory as cm
    except Exception:
        return "(memory unavailable)"

    query_lower = query.lower()

    # "last N messages" pattern
    n_match = re.search(r'last\s+(\d+)', query_lower)
    if n_match or "recent" in query_lower:
        n = int(n_match.group(1)) if n_match else 5
        n = min(n, 10)
        raw = cm.get_recent(n=n)
        if not raw:
            return "(no conversation history found)"
        return _format_raw(raw, n)

    # Semantic/keyword search
    raw = cm.get_recent(n=20)
    if not raw:
        return "(no conversation history found)"

    parts = raw.split("\n## ")
    matches = []
    keywords = [w for w in query_lower.split() if len(w) > 3]
    for part in parts:
        part_lower = part.lower()
        if any(kw in part_lower for kw in keywords):
            matches.append(part)

    if matches:
        return _format_raw("\n## ".join(matches[-5:]), 5)

    return f"(couldn't find anything matching '{query}' in recent history)"


def _format_raw(raw: str, n: int) -> str:
    parts = raw.split("\n## ")
    lines = []
    for part in parts[-n:]:
        if not part.strip():
            continue
        part_lines = part.strip().split("\n")
        timestamp = part_lines[0].split(" — ")[0].strip() if part_lines else "?"
        user_msg = ""
        bot_msg = ""
        for line in part_lines:
            if line.startswith("**User:** "):
                user_msg = line[len("**User:** "):].strip()
            elif line.startswith("**Bot:** "):
                bot_msg = line[len("**Bot:** "):].strip()
        if user_msg or bot_msg:
            lines.append(f"[{timestamp}]")
            if user_msg:
                lines.append(f"  master: {user_msg[:200]}")
            if bot_msg:
                lines.append(f"  you: {bot_msg[:200]}")
            lines.append("")

    return "\n".join(lines) if lines else "(no exchanges found)"
