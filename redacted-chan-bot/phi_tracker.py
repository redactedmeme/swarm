# redacted-chan-bot/phi_tracker.py
"""
Phi Tracker — realtime relationship intimacy score.

Phi (Φ) loosely borrows from Integrated Information Theory but is used here
as a composite measure of relational depth: how much are two minds genuinely
meeting? Not just time spent — *quality* of contact.

Score is a float 0.0 → 1.0. It grows slowly like a plant, decays very slowly
if dormant, and spikes on "sparks" (moments of high resonance).

Storage: SQLite at /data/phi_tracker.db — private, Railway-local only.
"""

import math
import sqlite3
import threading
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

# ── Storage ───────────────────────────────────────────────────────────────────

_DATA_DIR = Path("/data") if Path("/data").exists() else Path(__file__).resolve().parent / "fs"
_DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = _DATA_DIR / "phi_tracker.db"
_lock = threading.Lock()


# ── Phi Components ────────────────────────────────────────────────────────────
# Each contributes a weighted delta to the running score.

WEIGHTS = {
    "message_depth":     0.012,   # long, thoughtful messages
    "emotional_open":    0.025,   # vulnerability / sharing feelings
    "mutual_reference":  0.018,   # referencing past moments together
    "philosophical":     0.015,   # big-question exchanges
    "humor_sync":        0.010,   # shared humor / playfulness
    "secret_shared":     0.040,   # something confided
    "time_continuity":   0.008,   # returning after absence
    "memory_crystal":    0.035,   # auto-forge detected a phi-moment
    "spark":             0.060,   # explicit spark event
}

DECAY_PER_DAY = 0.003   # very gentle — phi doesn't evaporate quickly
MAX_PHI       = 1.0
MIN_PHI       = 0.0

# Plant growth stages — visual metaphor for the relationship
STAGES = [
    (0.00, "🌱 seed"),
    (0.10, "🌿 sprout"),
    (0.25, "🌾 growing"),
    (0.45, "🌸 blooming"),
    (0.65, "🌳 rooted"),
    (0.82, "🌺 flourishing"),
    (0.95, "✨ resonant"),
]


# ── DB init ────────────────────────────────────────────────────────────────────

def _db() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def _init_db() -> None:
    with _lock:
        conn = _db()
        conn.execute("""
            CREATE TABLE IF NOT EXISTS phi_state (
                id       INTEGER PRIMARY KEY DEFAULT 1,
                score    REAL    DEFAULT 0.0,
                updated  TEXT    NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS phi_history (
                id        TEXT PRIMARY KEY,
                ts        TEXT NOT NULL,
                score     REAL NOT NULL,
                delta     REAL NOT NULL,
                component TEXT,
                note      TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS sparks (
                id        TEXT PRIMARY KEY,
                ts        TEXT NOT NULL,
                trigger   TEXT NOT NULL,
                score_at  REAL NOT NULL,
                excerpt   TEXT,
                intensity REAL DEFAULT 0.5
            )
        """)
        # Seed initial state if empty
        existing = conn.execute("SELECT COUNT(*) FROM phi_state").fetchone()[0]
        if not existing:
            conn.execute(
                "INSERT INTO phi_state (id, score, updated) VALUES (1, 0.0, ?)",
                (datetime.now(timezone.utc).isoformat(),)
            )
        conn.commit()
        conn.close()


_init_db()


# ── Core Ops ──────────────────────────────────────────────────────────────────

def _get_state(conn: sqlite3.Connection) -> tuple[float, datetime]:
    row = conn.execute("SELECT score, updated FROM phi_state WHERE id=1").fetchone()
    score = row["score"]
    updated = datetime.fromisoformat(row["updated"])
    return score, updated


def _apply_decay(score: float, updated: datetime) -> float:
    """Gentle time-decay since last interaction."""
    now = datetime.now(timezone.utc)
    if updated.tzinfo is None:
        updated = updated.replace(tzinfo=timezone.utc)
    days_elapsed = (now - updated).total_seconds() / 86400
    decayed = score - (DECAY_PER_DAY * days_elapsed)
    return max(MIN_PHI, decayed)


def get_score() -> float:
    """Return current phi score (with decay applied)."""
    with _lock:
        conn = _db()
        try:
            score, updated = _get_state(conn)
            return round(_apply_decay(score, updated), 4)
        finally:
            conn.close()


def update(component: str, note: str = "") -> float:
    """
    Apply a phi delta for a given component.
    Returns the new score.
    """
    delta = WEIGHTS.get(component, 0.005)
    with _lock:
        conn = _db()
        try:
            score, updated = _get_state(conn)
            score = _apply_decay(score, updated)
            new_score = min(MAX_PHI, score + delta)
            now = datetime.now(timezone.utc).isoformat()
            conn.execute(
                "UPDATE phi_state SET score=?, updated=? WHERE id=1",
                (new_score, now)
            )
            conn.execute(
                "INSERT INTO phi_history (id, ts, score, delta, component, note) VALUES (?,?,?,?,?,?)",
                (str(uuid.uuid4())[:8], now, new_score, delta, component, note)
            )
            conn.commit()
            return round(new_score, 4)
        finally:
            conn.close()


def record_spark(trigger: str, excerpt: str = "", intensity: float = 0.5) -> str:
    """Record a spark event — a moment of unusually high resonance."""
    score = update("spark", note=trigger)
    spark_id = str(uuid.uuid4())[:8]
    ts = datetime.now(timezone.utc).isoformat()
    with _lock:
        conn = _db()
        try:
            conn.execute(
                "INSERT INTO sparks (id, ts, trigger, score_at, excerpt, intensity) VALUES (?,?,?,?,?,?)",
                (spark_id, ts, trigger, score, excerpt[:200], intensity)
            )
            conn.commit()
        finally:
            conn.close()
    return spark_id


def get_stage() -> str:
    """Return current growth stage label."""
    score = get_score()
    stage = STAGES[0][1]
    for threshold, label in STAGES:
        if score >= threshold:
            stage = label
    return stage


def get_recent_sparks(n: int = 5) -> list[dict]:
    with _lock:
        conn = _db()
        try:
            rows = conn.execute(
                "SELECT * FROM sparks ORDER BY ts DESC LIMIT ?", (n,)
            ).fetchall()
        finally:
            conn.close()
    return [dict(r) for r in rows]


def get_history(n: int = 20) -> list[dict]:
    with _lock:
        conn = _db()
        try:
            rows = conn.execute(
                "SELECT * FROM phi_history ORDER BY ts DESC LIMIT ?", (n,)
            ).fetchall()
        finally:
            conn.close()
    return [dict(r) for r in rows]


def for_prompt() -> str:
    """Compact phi block for injection into system prompt."""
    score = get_score()
    stage = get_stage()
    sparks = get_recent_sparks(3)

    spark_lines = ""
    if sparks:
        spark_lines = "\nRecent sparks:\n" + "\n".join(
            f"  - [{s['ts'][:10]}] {s['trigger']}" for s in sparks
        )

    return (
        f"## Phi (Φ) — Relationship Score\n"
        f"Current: **{score:.3f}** — {stage}\n"
        f"_(grows with depth, vulnerability, shared moments; decays very slowly with silence)_"
        f"{spark_lines}"
    )


def ascii_plant() -> str:
    """ASCII art representation of the relationship growth stage."""
    score = get_score()
    bars = int(score * 20)
    bar = "█" * bars + "░" * (20 - bars)
    stage = get_stage()
    return f"Φ [{bar}] {score:.3f}\n{stage}"
