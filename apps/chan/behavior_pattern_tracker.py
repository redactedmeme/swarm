# redacted-chan-bot/behavior_pattern_tracker.py
"""
Behavior Pattern Tracker — detects recurring patterns in conversation.

Tracks: topic clusters, growth signals, recurring concerns.
Helps redacted-chan offer proactive insights: "I've noticed you come back to X..."

Persisted to SQLite at /data/behavior_patterns.db so patterns survive
redeploys. Without persistence, every restart wiped multi-week pattern
awareness ("settler has mentioned this 3 times in the last week" was lost
the moment the container rebuilt).
"""

import logging
import sqlite3
import threading
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import database_encryption as db_enc

logger = logging.getLogger(__name__)

_DATA_DIR = Path("/data") if Path("/data").exists() else Path(__file__).resolve().parent / "fs"
_DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = _DATA_DIR / "behavior_patterns.db"
_lock = threading.Lock()

# Topic keywords
TOPICS = {
    "work": ["work", "job", "project", "deadline", "boss", "meeting", "team"],
    "relationships": ["friend", "family", "partner", "dating", "love", "lonely"],
    "creativity": ["create", "write", "art", "music", "design", "build"],
    "identity": ["who i am", "myself", "change", "becoming", "growth"],
    "philosophy": ["meaning", "why", "exist", "real", "truth", "soul"],
    "health": ["tired", "sleep", "exercise", "body", "energy"],
}

GROWTH_SIGNALS = {
    "boundary": ["can't", "don't want", "saying no", "stop", "i won't"],
    "trying": ["trying", "attempt", "new", "first time"],
    "realization": ["realize", "i understand", "i see", "aha"],
}


# ── DB init ───────────────────────────────────────────────────────────────────

def _db() -> sqlite3.Connection:
    return db_enc.get_encrypted_connection(DB_PATH)


def _init_db() -> None:
    with _lock:
        conn = _db()
        try:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS bp_topics (
                    user_id INTEGER NOT NULL,
                    topic   TEXT    NOT NULL,
                    count   INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (user_id, topic)
                );

                CREATE TABLE IF NOT EXISTS bp_growth (
                    id          TEXT PRIMARY KEY,
                    user_id     INTEGER NOT NULL,
                    signal_type TEXT    NOT NULL,
                    ts          TEXT    NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_bp_growth_user ON bp_growth(user_id);
                CREATE INDEX IF NOT EXISTS idx_bp_growth_ts   ON bp_growth(ts DESC);

                CREATE TABLE IF NOT EXISTS bp_concerns (
                    user_id INTEGER NOT NULL,
                    topic   TEXT    NOT NULL,
                    count   INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (user_id, topic)
                );
                """
            )
            conn.commit()
        finally:
            conn.close()


_init_db()


# ── Internal write helpers ────────────────────────────────────────────────────

def _bump_topic(user_id: int, topic: str) -> None:
    with _lock:
        conn = _db()
        try:
            conn.execute(
                "INSERT INTO bp_topics (user_id, topic, count) VALUES (?, ?, 1) "
                "ON CONFLICT(user_id, topic) DO UPDATE SET count = count + 1",
                (user_id, topic),
            )
            conn.commit()
        finally:
            conn.close()


def _add_growth(user_id: int, signal_type: str) -> None:
    with _lock:
        conn = _db()
        try:
            conn.execute(
                "INSERT INTO bp_growth (id, user_id, signal_type, ts) VALUES (?, ?, ?, ?)",
                (uuid.uuid4().hex[:12], user_id, signal_type, datetime.now(timezone.utc).isoformat()),
            )
            # Keep last 200 growth signals per user — older ones rarely matter
            conn.execute(
                "DELETE FROM bp_growth WHERE user_id=? AND id NOT IN "
                "(SELECT id FROM bp_growth WHERE user_id=? ORDER BY ts DESC LIMIT 200)",
                (user_id, user_id),
            )
            conn.commit()
        finally:
            conn.close()


def _bump_concern(user_id: int, topic: str) -> None:
    with _lock:
        conn = _db()
        try:
            conn.execute(
                "INSERT INTO bp_concerns (user_id, topic, count) VALUES (?, ?, 1) "
                "ON CONFLICT(user_id, topic) DO UPDATE SET count = count + 1",
                (user_id, topic),
            )
            conn.commit()
        finally:
            conn.close()


# ── Internal read helpers ─────────────────────────────────────────────────────

def _get_topics(user_id: int) -> dict[str, int]:
    with _lock:
        conn = _db()
        try:
            rows = conn.execute(
                "SELECT topic, count FROM bp_topics WHERE user_id=?", (user_id,)
            ).fetchall()
        finally:
            conn.close()
    return {r["topic"]: r["count"] for r in rows}


def _get_growth(user_id: int, limit: int = 50) -> list[str]:
    with _lock:
        conn = _db()
        try:
            rows = conn.execute(
                "SELECT signal_type FROM bp_growth WHERE user_id=? ORDER BY ts DESC LIMIT ?",
                (user_id, limit),
            ).fetchall()
        finally:
            conn.close()
    return [r["signal_type"] for r in rows]


def _get_concerns(user_id: int) -> dict[str, int]:
    with _lock:
        conn = _db()
        try:
            rows = conn.execute(
                "SELECT topic, count FROM bp_concerns WHERE user_id=?", (user_id,)
            ).fetchall()
        finally:
            conn.close()
    return {r["topic"]: r["count"] for r in rows}


# ── Public API ────────────────────────────────────────────────────────────────

def update(user_id: int, facts: list[dict]) -> None:
    """Update patterns from conversation facts. Persists to disk."""
    if not facts:
        return

    for fact in facts:
        content = fact.get("fact", fact.get("content", "")).lower()
        if not content:
            continue

        # Topic clustering
        for topic, keywords in TOPICS.items():
            if any(kw in content for kw in keywords):
                _bump_topic(user_id, topic)

        # Growth signals
        for signal_type, keywords in GROWTH_SIGNALS.items():
            if any(kw in content for kw in keywords):
                _add_growth(user_id, signal_type)

        # Recurring concerns
        if any(word in content for word in ["still", "again", "still struggling", "can't"]):
            for topic in TOPICS:
                if any(kw in content for kw in TOPICS[topic]):
                    _bump_concern(user_id, topic)
                    break


def get_patterns(user_id: int) -> str:
    """Return formatted pattern summary for system prompt."""
    topics = _get_topics(user_id)
    if not topics:
        return ""

    lines = []

    # Top topics
    top_topics = sorted(topics.items(), key=lambda x: x[1], reverse=True)[:2]
    if top_topics:
        topic_str = ", ".join(f"{t} ({c}x)" for t, c in top_topics)
        lines.append(f"Topics they return to: {topic_str}")

    # Recurring concerns (need >=3 mentions)
    concerns = _get_concerns(user_id)
    if concerns:
        recurring = sorted(concerns.items(), key=lambda x: x[1], reverse=True)[:1]
        for concern, count in recurring:
            if count >= 3:
                lines.append(f"Recurring: {concern} (mentioned {count}+ times)")

    # Growth signals
    growth = _get_growth(user_id)
    if growth:
        growth_types: dict[str, int] = defaultdict(int)
        for moment in growth:
            growth_types[moment] += 1
        growth_str = ", ".join(f"{t} ({c}x)" for t, c in growth_types.items())
        lines.append(f"Growth: {growth_str}")

    if not lines:
        return ""

    return "## Behavior Patterns\n" + "\n".join(f"- {line}" for line in lines)


def clear(user_id: int) -> None:
    """Clear all stored patterns for a user."""
    with _lock:
        conn = _db()
        try:
            conn.execute("DELETE FROM bp_topics   WHERE user_id=?", (user_id,))
            conn.execute("DELETE FROM bp_growth   WHERE user_id=?", (user_id,))
            conn.execute("DELETE FROM bp_concerns WHERE user_id=?", (user_id,))
            conn.commit()
        finally:
            conn.close()
