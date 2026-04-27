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
from datetime import datetime, timezone, timedelta
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
                recalled     INTEGER DEFAULT 0,
                love_resonance REAL DEFAULT 0.5
            )
        """)
        # Migrate existing tables that lack love_resonance
        try:
            conn.execute("ALTER TABLE memories ADD COLUMN love_resonance REAL DEFAULT 0.5")
        except Exception:
            pass  # column already exists
        conn.execute("CREATE INDEX IF NOT EXISTS idx_memories_ts ON memories(ts DESC)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_memories_cat ON memories(category)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_memories_love ON memories(love_resonance DESC)")
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


def _relevance_score(memory: dict, query: str, now: datetime) -> float:
    """
    Score a vault memory for relevance to the current message.
    Combines keyword overlap, love_resonance, and recency.
    Inspired by Holographic trust-scoring + Honcho query-length heuristics.
    """
    # Recency: half-life ~20 days
    try:
        ts = datetime.fromisoformat(memory["ts"].replace("Z", "+00:00"))
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        days_old = max(0, (now - ts).total_seconds() / 86400)
    except Exception:
        days_old = 30
    recency = 1.0 / (1.0 + days_old * 0.05)

    # Love resonance — learned signal of which memories actually land
    love = float(memory.get("love_resonance", 0.5))

    # Keyword overlap (Jaccard) between query and memory text
    overlap = 0.0
    if query:
        q_words = set(query.lower().split())
        m_text = (memory.get("content", "") + " " + memory.get("title", "")).lower()
        m_words = set(m_text.split())
        if q_words and m_words:
            overlap = len(q_words & m_words) / max(1, len(q_words | m_words))
            overlap = min(1.0, overlap * 4)  # amplify small matches

    # Composite: relevance 35%, love 35%, recency 30%
    return overlap * 0.35 + love * 0.35 + recency * 0.30


def get_for_prompt(n: int = 6, query: str = "") -> str:
    """
    Return a formatted block of memories scored by relevance to current message.
    When query is provided, fetches a broad candidate pool and ranks by relevance
    (keyword overlap + love_resonance + recency) instead of pure recency.
    """
    # Fetch broader candidate pool so ranking has something to work with
    pool_size = max(n * 5, 40)
    with _lock:
        conn = _db()
        try:
            rows = conn.execute(
                "SELECT * FROM memories ORDER BY ts DESC LIMIT ?", (pool_size,)
            ).fetchall()
        finally:
            conn.close()

    if not rows:
        return ""

    rows = [dict(r) for r in rows]

    if query:
        now = datetime.now(timezone.utc)
        rows = sorted(rows, key=lambda m: _relevance_score(m, query, now), reverse=True)

    rows = rows[:n]

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


def get_by_categories(categories: list[str], limit: int = 20) -> list[dict]:
    """Return recent memories filtered to specific categories, ordered by love_resonance DESC."""
    if not categories:
        return []
    with _lock:
        conn = _db()
        try:
            ph = ",".join("?" * len(categories))
            rows = conn.execute(
                f"SELECT * FROM memories WHERE category IN ({ph}) "
                f"ORDER BY love_resonance DESC, ts DESC LIMIT ?",
                (*categories, limit),
            ).fetchall()
        finally:
            conn.close()
    return [dict(r) for r in rows]


def update_love_resonance(memory_id: str, delta: float) -> None:
    """Adjust love_resonance for a memory by delta. Clamped to [0.0, 1.0]."""
    with _lock:
        conn = _db()
        try:
            row = conn.execute(
                "SELECT love_resonance FROM memories WHERE id=?", (memory_id,)
            ).fetchone()
            if not row:
                return
            new_score = max(0.0, min(1.0, row["love_resonance"] + delta))
            conn.execute(
                "UPDATE memories SET love_resonance=? WHERE id=?", (new_score, memory_id)
            )
            conn.commit()
        finally:
            conn.close()


def find_resonant_memories(emotional_frame, limit: int = 2) -> list[dict]:
    """
    Find vault memories that match the current emotional state.

    Matches by emotional tone (vulnerable moments when user opening up, jokes when playful, etc.)
    and recency — recent memories weighted higher than old ones.

    Args:
        emotional_frame: Object with valence, openness, humor attributes
        limit: max memories to return (default 2)

    Returns:
        List of memory dicts ranked by emotional resonance
    """
    if not hasattr(emotional_frame, 'openness'):
        return []

    # Map emotional state to preferred categories
    prefs = []

    if emotional_frame.openness > 0.3:
        prefs.extend(["secret", "feeling"])  # vulnerable moments
    if emotional_frame.humor > 0.4:
        prefs.extend(["joke"])  # playful moments
    if emotional_frame.valence < -0.2:
        prefs.extend(["feeling", "moment"])  # when they're down

    if not prefs:
        prefs = ["moment", "feeling"]  # default

    with _lock:
        conn = _db()
        try:
            rows = conn.execute(
                "SELECT * FROM memories ORDER BY ts DESC LIMIT 50"
            ).fetchall()
        finally:
            conn.close()

    if not rows:
        return []

    # Score by category match + recency
    scored = []
    for r in rows:
        row_dict = dict(r)
        score = 1.0
        if row_dict.get("category") in prefs:
            score += 2.0
        scored.append((score, row_dict))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [m for _, m in scored[:limit]]
