# redacted-chan-bot/relationship_vault.py
"""
Relationship memory vault — private, persistent, Railway-local only.

Stores rich relationship memories: moments that had texture, inside jokes,
patterns noticed about the user, secrets shared, feelings that mattered.
Unlike conversation_memory (raw log + facts), this is curated — only written
when something genuinely worth keeping happened.

Storage: SQLite at /data/relationship_vault.db (Railway volume).
Never committed to git. Never logged externally.
"""

import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import database_encryption as db_enc

# ── Storage path — Railway /data volume, falls back to local for dev ──────────

_DATA_DIR = Path("/data") if Path("/data").exists() else Path(__file__).resolve().parent / "fs"
_DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = _DATA_DIR / "relationship_vault.db"

_lock = threading.Lock()

# ── Categories ────────────────────────────────────────────────────────────────

CATEGORIES = {
    "moment":    "a meaningful moment or exchange worth remembering",
    "pattern":   "something noticed about the user — a habit, preference, or recurring feeling",
    "secret":    "something they shared in confidence",
    "joke":      "an inside joke or shared reference that belongs to just us",
    "feeling":   "how something felt — the emotional texture of a moment",
    "milestone": "a first, a turning point, something that marked a change",
}


# ── DB init ─────────────────────────────���──────────────────────────────────���──

def _db() -> sqlite3.Connection:
    conn = db_enc.get_encrypted_connection(DB_PATH)
    return conn


def _init_db() -> None:
    with _lock:
        conn = _db()
        conn.execute("""
            CREATE TABLE IF NOT EXISTS memories (
                id           TEXT PRIMARY KEY,
                ts           TEXT NOT NULL,
                content      TEXT NOT NULL,
                category     TEXT NOT NULL DEFAULT 'moment',
                title        TEXT,
                emotional_tone TEXT,
                source       TEXT DEFAULT 'chan_llm',
                recalled     INTEGER DEFAULT 0
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_memories_ts ON memories(ts DESC)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_memories_cat ON memories(category)")
        conn.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts
            USING fts5(id UNINDEXED, content, title, emotional_tone, tokenize='porter ascii')
        """)
        conn.commit()
        conn.close()


_init_db()


# ── Write ─────────────────────────────��───────────────────────────────────────

def add_memory(
    content: str,
    category: str = "moment",
    title: Optional[str] = None,
    emotional_tone: Optional[str] = None,
    source: str = "chan_llm",
) -> str:
    """Store a relationship memory. Returns the new entry ID."""
    if category not in CATEGORIES:
        category = "moment"

    entry_id = str(uuid.uuid4())[:8]
    ts = datetime.now(timezone.utc).isoformat()
    content = content[:500]
    title = title[:80] if title else None
    emotional_tone = emotional_tone[:80] if emotional_tone else None

    with _lock:
        conn = _db()
        try:
            conn.execute(
                "INSERT INTO memories (id, ts, content, category, title, emotional_tone, source) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (entry_id, ts, content, category, title, emotional_tone, source),
            )
            conn.execute(
                "INSERT INTO memories_fts (id, content, title, emotional_tone) VALUES (?, ?, ?, ?)",
                (entry_id, content, title or "", emotional_tone or ""),
            )
            conn.commit()
        finally:
            conn.close()

    return entry_id


# ── Read ────────────────────────────────────────────────────────────────���─────

def get_recent(n: int = 10, category: Optional[str] = None) -> list[dict]:
    """Return the most recent memories, optionally filtered by category."""
    with _lock:
        conn = _db()
        try:
            if category:
                rows = conn.execute(
                    "SELECT * FROM memories WHERE category=? ORDER BY ts DESC LIMIT ?",
                    (category, n),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM memories ORDER BY ts DESC LIMIT ?", (n,)
                ).fetchall()
        finally:
            conn.close()
    return [dict(r) for r in rows]


def search(query: str, limit: int = 5) -> list[dict]:
    """Full-text search across memory content, title, and emotional tone."""
    with _lock:
        conn = _db()
        try:
            rows = conn.execute(
                "SELECT m.* FROM memories m "
                "JOIN memories_fts f ON m.id = f.id "
                "WHERE memories_fts MATCH ? "
                "ORDER BY rank LIMIT ?",
                (query, limit),
            ).fetchall()
        finally:
            conn.close()
    return [dict(r) for r in rows]


def get_for_prompt(n: int = 6) -> str:
    """
    Return a formatted block of recent memories for injection into system prompt.
    Marks recalled memories so they don't dominate every conversation.
    """
    rows = get_recent(n)
    if not rows:
        return ""

    lines = []
    for r in rows:
        ts_short = r["ts"][:10]
        title_part = f"**{r['title']}** — " if r.get("title") else ""
        tone_part = f" _{r['emotional_tone']}_" if r.get("emotional_tone") else ""
        lines.append(f"- [{ts_short}] [{r['category']}] {title_part}{r['content']}{tone_part}")

    _bump_recalled(rows)
    return "## Relationship Memories\n" + "\n".join(lines)


def _bump_recalled(rows: list[dict]) -> None:
    if not rows:
        return
    ids = [r["id"] for r in rows]
    with _lock:
        conn = _db()
        try:
            ph = ",".join("?" * len(ids))
            conn.execute(f"UPDATE memories SET recalled=recalled+1 WHERE id IN ({ph})", ids)
            conn.commit()
        finally:
            conn.close()


def count() -> int:
    with _lock:
        conn = _db()
        try:
            return conn.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
        finally:
            conn.close()
