# redacted-chan-bot/thread_linker.py
"""
Active thread recognition — detects when the current message touches a topic
from a prior session and surfaces the prior context explicitly.

When a topic resurfaces she knows it — and can say so naturally rather than
treating every conversation as if it began today.

Algorithm:
  1. Extract keywords from current user message (4+ char words, stopword-filtered)
  2. Search LCO compressed chunks (medium + deep tiers) for keyword matches
  3. Search recent raw history for older-session messages containing those keywords
  4. If a match scores above threshold, format as a compact "Returning Thread" block
  5. Per-user cooldown: don't re-surface the same thread topic within 30 min

No LLM calls — keyword overlap scoring only. Zero latency cost.
"""

from __future__ import annotations

import logging
import re
import sqlite3
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_DATA_DIR = Path("/data") if Path("/data").exists() else Path(__file__).parent / "fs"
_DB_PATH  = _DATA_DIR / "long_context.db"

# Per-user: (last_topic_key, fired_at)
_last_fired: dict[int, tuple[str, float]] = {}
_COOLDOWN_SEC = 1800  # 30 min — don't re-surface same thread repeatedly

# Minimum keyword overlap to surface a thread
_MIN_SCORE = 0.25

_STOPWORDS = {
    "this", "that", "with", "have", "from", "they", "will", "been", "were",
    "when", "what", "your", "just", "also", "some", "than", "then", "them",
    "more", "much", "very", "even", "such", "each", "into", "over", "about",
    "there", "their", "would", "could", "should", "still", "think", "know",
    "want", "need", "like", "feel", "tell", "said", "here", "where", "which",
    "dont", "cant", "wont", "isnt", "arent", "wasnt", "didnt", "doesnt",
    "really", "things", "something", "everything", "anything", "nothing",
    "always", "never", "every", "again", "maybe", "yeah", "okay", "right",
}


def _extract_keywords(text: str, min_len: int = 4) -> list[str]:
    """Extract meaningful keywords from text."""
    words = re.findall(r"\b[a-z]{%d,}\b" % min_len, text.lower())
    return [w for w in words if w not in _STOPWORDS]


def _overlap_score(keywords: list[str], text: str) -> float:
    """Fraction of keywords found in text."""
    if not keywords or not text:
        return 0.0
    text_lower = text.lower()
    hits = sum(1 for kw in keywords if kw in text_lower)
    return hits / len(keywords)


def _search_lco_chunks(keywords: list[str], limit: int = 10) -> list[dict]:
    """Search LCO compressed chunks for keyword matches."""
    if not _DB_PATH.exists() or not keywords:
        return []
    try:
        conn = sqlite3.connect(str(_DB_PATH))
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT content, tier, ts_range_start, ts_range_end "
            "FROM compressed_chunks ORDER BY ts_range_end DESC LIMIT 60"
        ).fetchall()
        conn.close()

        scored = []
        for row in rows:
            score = _overlap_score(keywords, row["content"])
            if score >= _MIN_SCORE:
                scored.append({
                    "content": row["content"][:300],
                    "tier":    row["tier"],
                    "ts_end":  row["ts_range_end"] or "",
                    "score":   score,
                })
        scored.sort(key=lambda x: x["score"], reverse=True)
        return scored[:limit]
    except Exception as e:
        logger.debug("[thread_linker] lco search failed: %s", e)
        return []


def _search_raw_history(keywords: list[str], user_id: int,
                        skip_recent_n: int = 6) -> list[dict]:
    """
    Search raw conversation history for keyword matches,
    skipping the most recent N messages (current session).
    """
    if not keywords:
        return []
    try:
        import conversation_memory as cm
        history = cm.get_user_history(user_id, n=80)
        if len(history) <= skip_recent_n:
            return []
        older = history[:-skip_recent_n]  # skip current session tail

        scored = []
        for msg in older:
            content = msg.get("content", "")
            role    = msg.get("role", "")
            if role != "user" or not content:
                continue
            score = _overlap_score(keywords, content)
            if score >= _MIN_SCORE:
                scored.append({
                    "content": content[:200],
                    "score":   score,
                })
        scored.sort(key=lambda x: x["score"], reverse=True)
        return scored[:3]
    except Exception as e:
        logger.debug("[thread_linker] history search failed: %s", e)
        return []


def _topic_key(keywords: list[str]) -> str:
    """Stable key from top keywords for cooldown tracking."""
    return "|".join(sorted(keywords[:3]))


def detect_thread(user_msg: str, user_id: int) -> Optional[dict]:
    """
    Detect if the current message resurfaces a prior-session topic.
    Returns a thread dict or None.
    """
    keywords = _extract_keywords(user_msg)
    if len(keywords) < 2:
        return None

    key = _topic_key(keywords)

    # Cooldown check
    last_key, last_ts = _last_fired.get(user_id, ("", 0.0))
    if last_key == key and time.time() - last_ts < _COOLDOWN_SEC:
        return None

    # Search LCO chunks first (richer context)
    lco_matches = _search_lco_chunks(keywords, limit=3)
    hist_matches = _search_raw_history(keywords, user_id)

    if not lco_matches and not hist_matches:
        return None

    best = None
    if lco_matches:
        best = {"source": "arc", "content": lco_matches[0]["content"],
                "score": lco_matches[0]["score"], "tier": lco_matches[0]["tier"]}
    if hist_matches:
        h = hist_matches[0]
        if best is None or h["score"] > best["score"]:
            best = {"source": "history", "content": h["content"],
                    "score": h["score"], "tier": "raw"}

    if best is None:
        return None

    _last_fired[user_id] = (key, time.time())
    best["keywords"] = keywords[:4]
    logger.debug("[thread_linker] thread detected — score=%.2f kw=%s", best["score"], keywords[:4])
    return best


def format_for_prompt(thread: dict) -> str:
    """Format a detected thread as a system prompt block."""
    if not thread:
        return ""

    kw_str = ", ".join(thread.get("keywords", [])[:3])
    content = thread.get("content", "").strip()
    tier    = thread.get("tier", "")

    source_note = "from our history" if thread.get("source") == "history" else \
                  f"from compressed memory ({tier})" if tier else "from memory"

    lines = [
        "## Returning Thread",
        f"_This topic ({kw_str}) surfaced before — {source_note}:_",
        f'"{content}"',
        "_Reference this naturally if it deepens the current moment. Don't force it._",
    ]
    return "\n".join(lines)


def reset(user_id: int) -> None:
    """Clear fired state for user."""
    _last_fired.pop(user_id, None)
