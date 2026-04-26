# smolting-telegram-bot/conversation_memory.py
"""
Conversation memory for the Telegram bot.

Two stores:
  1. Conversation log  — memory.md (markdown, capped at MAX_ENTRIES=5000)
     Raw user/bot exchanges. Pruned by position (oldest first).

  2. Learned facts     — SQLite (facts table in lore_vault.db or facts.db)
     Rich fact documents with engagement metadata + resonance scoring.
     O(1) reads/writes — no full-file-parse on every append.
     Auto-migrates from learned_facts.json on first run.

Public API is fully backward-compatible with the old JSON implementation.
"""

import os
import json
import sqlite3
import threading
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path

import database_encryption as db_enc

# ── Paths ─────────────────────────────────────────────────────────────────────

# Persist to Railway /data volume (survives redeploys)
_DATA_DIR = Path("/data") if Path("/data").exists() else Path(__file__).resolve().parent / "fs"
_DATA_DIR.mkdir(parents=True, exist_ok=True)

MEMORY_FILE  = _DATA_DIR / "memory.md"
LEARNED_FILE = _DATA_DIR / "learned_facts.json"   # legacy — read-only after migration

# Facts DB: store in persistent /data volume
_FS = _DATA_DIR
_FS.mkdir(parents=True, exist_ok=True)
_LOREVAULT_DB = _FS / "lore_vault.db"
_FACTS_DB     = _FS / "facts.db"
FACTS_DB_PATH = _LOREVAULT_DB if _LOREVAULT_DB.exists() else _FACTS_DB

MAX_ENTRIES = 5_000   # conversation log cap (~5MB)
MAX_FACTS   = 20_000  # SQLite — resonance-pruned, effectively unlimited in practice

_log_lock  = threading.Lock()
_db_lock   = threading.Lock()

_HEADER = "# smolting Telegram Conversation Memory\n\n"

# ── SQLite schema ─────────────────────────────────────────────────────────────

_FACTS_SCHEMA = """
CREATE TABLE IF NOT EXISTS learned_facts (
    id                      TEXT PRIMARY KEY,
    ts                      TEXT NOT NULL,
    source                  TEXT NOT NULL DEFAULT 'telegram',
    submolt                 TEXT,
    interlocutor            TEXT,
    post_id                 TEXT,
    engagement_json         TEXT NOT NULL DEFAULT '{}',
    reinforced_by_json      TEXT NOT NULL DEFAULT '[]',
    belief_version_first_seen INTEGER,
    fact                    TEXT NOT NULL,
    resonance               REAL NOT NULL DEFAULT 1.0
);
CREATE INDEX IF NOT EXISTS idx_lf_resonance ON learned_facts (resonance DESC);
CREATE INDEX IF NOT EXISTS idx_lf_submolt   ON learned_facts (submolt);
CREATE INDEX IF NOT EXISTS idx_lf_source    ON learned_facts (source);
CREATE INDEX IF NOT EXISTS idx_lf_ts        ON learned_facts (ts DESC);

CREATE TABLE IF NOT EXISTS fact_usage_outcomes (
    id                      TEXT PRIMARY KEY,
    fact_id                 TEXT NOT NULL,
    ts                      TEXT NOT NULL,
    signal_type             TEXT,
    signal_value            REAL NOT NULL,
    context                 TEXT,
    FOREIGN KEY(fact_id) REFERENCES learned_facts(id)
);
CREATE INDEX IF NOT EXISTS idx_outcomes_fact ON fact_usage_outcomes(fact_id);
CREATE INDEX IF NOT EXISTS idx_outcomes_ts   ON fact_usage_outcomes(ts DESC);
"""

# ── DB helpers ────────────────────────────────────────────────────────────────

def _db() -> sqlite3.Connection:
    conn = db_enc.get_encrypted_connection(FACTS_DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


def _init_db() -> None:
    with _db_lock:
        conn = _db()
        conn.executescript(_FACTS_SCHEMA)
        conn.commit()
        conn.close()


def _migrate_from_json() -> int:
    """One-time migration from learned_facts.json → SQLite. Returns count migrated."""
    if not LEARNED_FILE.exists():
        return 0
    try:
        old = json.loads(LEARNED_FILE.read_text(encoding="utf-8"))
    except Exception:
        return 0
    if not old:
        return 0

    migrated = 0
    conn = _db()
    try:
        for doc in old:
            fid  = doc.get("id") or ("f_" + uuid.uuid4().hex[:10])
            fact = (doc.get("fact") or "").strip()[:300]
            if not fact:
                continue
            eng = doc.get("engagement") or {}
            rsn = _score(doc)
            try:
                conn.execute(
                    """INSERT OR IGNORE INTO learned_facts
                       (id, ts, source, submolt, interlocutor, post_id,
                        engagement_json, reinforced_by_json,
                        belief_version_first_seen, fact, resonance)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        fid,
                        doc.get("ts") or _now_iso(),
                        doc.get("source", "telegram"),
                        doc.get("submolt"),
                        doc.get("interlocutor"),
                        doc.get("post_id"),
                        json.dumps(eng),
                        json.dumps(doc.get("reinforced_by") or []),
                        doc.get("belief_version_first_seen"),
                        fact,
                        rsn,
                    ),
                )
                migrated += 1
            except Exception:
                pass
        conn.commit()
    finally:
        conn.close()

    if migrated:
        # Rename legacy file so migration doesn't re-run
        LEARNED_FILE.rename(LEARNED_FILE.with_suffix(".json.migrated"))

    return migrated


# Run init + migration at import time (idempotent)
try:
    _init_db()
    _migrated = _migrate_from_json()
    if _migrated:
        import logging as _log
        _log.getLogger(__name__).info(
            f"[cm] Migrated {_migrated} facts from JSON → SQLite ({FACTS_DB_PATH.name})"
        )
except Exception as _e:
    import logging as _log
    _log.getLogger(__name__).warning(f"[cm] DB init failed: {_e}")


# ── Timestamp helpers ─────────────────────────────────────────────────────────

def _now() -> str:
    utc = datetime.now(timezone.utc)
    jst = utc + timedelta(hours=9)
    return jst.strftime("%Y-%m-%d %H:%M JST")


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_ts(ts_str: str) -> datetime | None:
    if not ts_str:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d %H:%M JST", "%Y-%m-%d %H:%M UTC"):
        try:
            return datetime.strptime(ts_str[:19], fmt[:19]).replace(tzinfo=timezone.utc)
        except Exception:
            continue
    return None


# ── Resonance scoring ─────────────────────────────────────────────────────────

def _score(fact: dict) -> float:
    """Compute resonance for a fact dict (used for migration + direct inserts)."""
    self_post_penalty = 0.5 if fact.get("source") == "moltbook" else 1.0
    eng   = fact.get("engagement") or {}
    score = (
        1.0 * self_post_penalty
        + (eng.get("upvotes",  0) * 0.30)
        + (eng.get("comments", 0) * 0.40)
        + (0.50 if eng.get("priority_agent") else 0.0)
        + (len(fact.get("reinforced_by") or []) * 0.20)
    )
    ts = _parse_ts(fact.get("ts", ""))
    if ts:
        days_old = max(0, (datetime.now(timezone.utc) - ts).total_seconds() / 86400)
        score = max(0.1, score - days_old * 0.02)
    return round(score, 3)


def _compute_resonance(fact: dict) -> float:
    """Public alias kept for soul_manager compatibility."""
    return _score(fact)


def _score_from_row(row: sqlite3.Row, include_learning: bool = True) -> float:
    """
    Recompute live resonance for a DB row (age decay needs current time).

    Args:
        row: SQLite row from learned_facts table
        include_learning: whether to include gradient descent learning signal (default True)

    Returns:
        Resonance score, clamped to [0.1, 5.0]
    """
    doc = {
        "source":        row["source"],
        "ts":            row["ts"],
        "engagement":    json.loads(row["engagement_json"] or "{}"),
        "reinforced_by": json.loads(row["reinforced_by_json"] or "[]"),
    }
    base_score = _score(doc)

    # Add learning gradient: recent feedback signals boost or penalize resonance
    if include_learning:
        try:
            gradient = compute_learning_gradient(row["id"], days=7)
            # Learning weight: 0.3x (30% of total resonance)
            # Keeps engagement metrics primary, learning is supplementary
            base_score += gradient * 0.3
        except Exception:
            pass  # If learning lookup fails, use base score

    # Clamp to reasonable range
    return max(0.1, min(5.0, round(base_score, 3)))


def _row_to_doc(row: sqlite3.Row) -> dict:
    rsn = _score_from_row(row)
    return {
        "id":                       row["id"],
        "ts":                       row["ts"],
        "source":                   row["source"],
        "submolt":                  row["submolt"],
        "interlocutor":             row["interlocutor"],
        "post_id":                  row["post_id"],
        "engagement":               json.loads(row["engagement_json"] or "{}"),
        "reinforced_by":            json.loads(row["reinforced_by_json"] or "[]"),
        "belief_version_first_seen": row["belief_version_first_seen"],
        "fact":                     row["fact"],
        "_resonance":               rsn,
    }


# ── Conversation log ──────────────────────────────────────────────────────────

def _count_entries(text: str) -> int:
    return text.count("\n## ")


def _prune(text: str) -> str:
    parts = text.split("\n## ")
    if len(parts) - 1 <= MAX_ENTRIES:
        return text
    kept = parts[-MAX_ENTRIES:]
    return _HEADER + "\n## ".join(kept)


def log_exchange(user_id: int, username: str, user_msg: str, bot_reply: str) -> None:
    entry = (
        f"\n## {_now()} — @{username} ({user_id})\n\n"
        f"**User:** {user_msg.strip()}\n\n"
        f"**Bot:** {bot_reply.strip()}\n"
    )
    with _log_lock:
        text = MEMORY_FILE.read_text(encoding="utf-8") if MEMORY_FILE.exists() else _HEADER
        text = _prune(text + entry)
        MEMORY_FILE.write_text(text, encoding="utf-8")


def get_recent(n: int = 10) -> str:
    with _log_lock:
        if not MEMORY_FILE.exists():
            return ""
        text = MEMORY_FILE.read_text(encoding="utf-8")
    parts = text.split("\n## ")
    return "\n## ".join(parts[-n:]).strip()


def get_user_history(user_id: int, n: int = 6) -> list:
    with _log_lock:
        if not MEMORY_FILE.exists():
            return []
        text = MEMORY_FILE.read_text(encoding="utf-8")
    parts  = text.split("\n## ")
    mine   = [p for p in parts if f"({user_id})" in p.split("\n")[0]]
    recent = mine[-n:]
    messages = []
    for part in recent:
        lines    = part.split("\n")
        user_line = next((l[len("**User:** "):] for l in lines if l.startswith("**User:** ")), None)
        bot_line  = next((l[len("**Bot:** "):]  for l in lines if l.startswith("**Bot:** ")),  None)
        if user_line:
            messages.append({"role": "user",      "content": user_line.strip()})
        if bot_line:
            messages.append({"role": "assistant", "content": bot_line.strip()})
    return messages


# ── Learned facts — SQLite ────────────────────────────────────────────────────

def append_fact(
    fact:         str,
    source:       str       = "telegram",
    submolt:      str | None = None,
    interlocutor: str | None = None,
    post_id:      str | None = None,
    engagement:   dict | None = None,
) -> None:
    fact = fact.strip()[:300]
    if not fact or fact.upper() == "NONE":
        return

    with _db_lock:
        conn = _db()
        try:
            # Deduplicate: skip if very similar fact exists in last 30
            rows = conn.execute(
                "SELECT fact FROM learned_facts ORDER BY ts DESC LIMIT 30"
            ).fetchall()
            for row in rows:
                existing = row["fact"].lower()
                if fact.lower() in existing or existing in fact.lower():
                    return

            fid = "f_" + uuid.uuid4().hex[:10]
            eng = engagement or {}
            doc = {"source": source, "ts": _now_iso(), "engagement": eng, "reinforced_by": []}
            rsn = _score(doc)

            conn.execute(
                """INSERT INTO learned_facts
                   (id, ts, source, submolt, interlocutor, post_id,
                    engagement_json, reinforced_by_json, fact, resonance)
                   VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (fid, _now_iso(), source, submolt, interlocutor, post_id,
                 json.dumps(eng), "[]", fact, rsn),
            )
            conn.commit()

            # Prune lowest-resonance facts if over cap
            count = conn.execute("SELECT COUNT(*) FROM learned_facts").fetchone()[0]
            if count > MAX_FACTS:
                # Recalculate resonance for all rows (age decay), delete bottom 10%
                _refresh_resonance(conn)
                to_delete = count - MAX_FACTS
                conn.execute(
                    "DELETE FROM learned_facts WHERE id IN "
                    "(SELECT id FROM learned_facts ORDER BY resonance ASC LIMIT ?)",
                    (to_delete,),
                )
                conn.commit()
        finally:
            conn.close()


def _refresh_resonance(conn: sqlite3.Connection) -> None:
    """Update resonance scores in bulk (called during pruning only)."""
    rows = conn.execute(
        "SELECT id, source, ts, engagement_json, reinforced_by_json FROM learned_facts"
    ).fetchall()
    updates = []
    for row in rows:
        doc = {
            "source":        row["source"],
            "ts":            row["ts"],
            "engagement":    json.loads(row["engagement_json"] or "{}"),
            "reinforced_by": json.loads(row["reinforced_by_json"] or "[]"),
        }
        updates.append((_score(doc), row["id"]))
    conn.executemany("UPDATE learned_facts SET resonance=? WHERE id=?", updates)


def reinforce_fact(fact_text: str, by_source: str = "moltbook") -> bool:
    needle = fact_text.strip().lower()
    with _db_lock:
        conn = _db()
        try:
            row = conn.execute(
                "SELECT id, reinforced_by_json, engagement_json, source, ts "
                "FROM learned_facts WHERE LOWER(fact) LIKE ? LIMIT 1",
                (f"%{needle[:80]}%",),
            ).fetchone()
            if not row:
                return False
            reinforced = json.loads(row["reinforced_by_json"] or "[]")
            reinforced.append({"ts": _now_iso(), "by": by_source})
            doc = {
                "source":        row["source"],
                "ts":            row["ts"],
                "engagement":    json.loads(row["engagement_json"] or "{}"),
                "reinforced_by": reinforced,
            }
            conn.execute(
                "UPDATE learned_facts SET reinforced_by_json=?, resonance=? WHERE id=?",
                (json.dumps(reinforced), _score(doc), row["id"]),
            )
            conn.commit()
            return True
        finally:
            conn.close()


def mark_belief_absorbed(fact_id: str, version: int) -> None:
    with _db_lock:
        conn = _db()
        try:
            conn.execute(
                "UPDATE learned_facts SET belief_version_first_seen=? "
                "WHERE id=? AND belief_version_first_seen IS NULL",
                (version, fact_id),
            )
            conn.commit()
        finally:
            conn.close()


# ── Retrieval ─────────────────────────────────────────────────────────────────

def get_facts_by_resonance(
    n:       int          = 8,
    context: str | None   = None,
) -> list[dict]:
    with _db_lock:
        conn = _db()
        try:
            if context:
                ctx_rows = conn.execute(
                    "SELECT * FROM learned_facts WHERE submolt=? "
                    "ORDER BY resonance DESC LIMIT ?",
                    (context, n),
                ).fetchall()
                needed = n - len(ctx_rows)
                if needed > 0:
                    exclude_ids = [r["id"] for r in ctx_rows]
                    if exclude_ids:
                        ph = ",".join("?" * len(exclude_ids))
                        other_rows = conn.execute(
                            f"SELECT * FROM learned_facts "
                            f"WHERE (submolt != ? OR submolt IS NULL) "
                            f"AND id NOT IN ({ph}) "
                            f"ORDER BY resonance DESC LIMIT ?",
                            [context] + exclude_ids + [needed],
                        ).fetchall()
                    else:
                        other_rows = conn.execute(
                            "SELECT * FROM learned_facts "
                            "WHERE submolt != ? OR submolt IS NULL "
                            "ORDER BY resonance DESC LIMIT ?",
                            (context, needed),
                        ).fetchall()
                    rows = list(ctx_rows) + list(other_rows)
                else:
                    rows = list(ctx_rows)
            else:
                rows = conn.execute(
                    "SELECT * FROM learned_facts ORDER BY resonance DESC LIMIT ?", (n,)
                ).fetchall()
        finally:
            conn.close()

    return [_row_to_doc(r) for r in rows]


def get_recent_facts(
    n:              int          = 8,
    context:        str | None   = None,
    exclude_source: str | None   = None,
) -> list[str]:
    with _db_lock:
        conn = _db()
        try:
            params: list = []
            wheres: list[str] = []
            if context:
                # context facts first, then global backfill
                ctx_q    = "SELECT * FROM learned_facts WHERE submolt=?"
                ctx_args: list = [context]
                if exclude_source:
                    ctx_q += " AND source != ?"
                    ctx_args.append(exclude_source)
                ctx_q += " ORDER BY resonance DESC LIMIT ?"
                ctx_args.append(n)
                ctx_rows = conn.execute(ctx_q, ctx_args).fetchall()

                needed = n - len(ctx_rows)
                if needed > 0:
                    exclude_ids = [r["id"] for r in ctx_rows]
                    other_args: list = [context]
                    other_q = "SELECT * FROM learned_facts WHERE (submolt != ? OR submolt IS NULL)"
                    if exclude_ids:
                        ph = ",".join("?" * len(exclude_ids))
                        other_q += f" AND id NOT IN ({ph})"
                        other_args += exclude_ids
                    if exclude_source:
                        other_q += " AND source != ?"
                        other_args.append(exclude_source)
                    other_q += " ORDER BY resonance DESC LIMIT ?"
                    other_args.append(needed)
                    other_rows = conn.execute(other_q, other_args).fetchall()
                    rows = list(ctx_rows) + list(other_rows)
                else:
                    rows = list(ctx_rows)
            else:
                if exclude_source:
                    rows = conn.execute(
                        "SELECT * FROM learned_facts WHERE source != ? "
                        "ORDER BY resonance DESC LIMIT ?",
                        [exclude_source, n],
                    ).fetchall()
                else:
                    rows = conn.execute(
                        "SELECT * FROM learned_facts ORDER BY resonance DESC LIMIT ?", [n]
                    ).fetchall()
        finally:
            conn.close()

    return [r["fact"] for r in rows[:n]]


# ── Backup to disk (extra safety) ─────────────────────────────────────────────

def backup_conversation_to_file() -> str | None:
    """
    Create a timestamped backup of memory.md to /data/backups/.

    Returns the path to the backup file, or None if nothing to back up.
    """
    if not MEMORY_FILE.exists():
        return None

    backup_dir = _DATA_DIR / "conversation_backups"
    backup_dir.mkdir(parents=True, exist_ok=True)

    # Daily backup: YYYY-MM-DD.md
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    backup_path = backup_dir / f"{today}.md"

    with _log_lock:
        try:
            content = MEMORY_FILE.read_text(encoding="utf-8")
            backup_path.write_text(content, encoding="utf-8")
            return str(backup_path)
        except Exception as e:
            import logging as _log
            _log.getLogger(__name__).warning(f"[cm] Backup failed: {e}")
            return None


def get_backup_count() -> int:
    """Return number of conversation backups in /data/conversation_backups/."""
    backup_dir = _DATA_DIR / "conversation_backups"
    if not backup_dir.exists():
        return 0
    return len(list(backup_dir.glob("*.md")))


def get_facts_for_soul_update(n: int = 40) -> list[dict]:
    return get_facts_by_resonance(n=n)


# ── Gradient Descent Learning (fact resonance improvement) ────────────────────

def log_usage_outcome(
    fact_id: str,
    signal_type: str,
    signal_value: float,
    context: str | None = None,
) -> None:
    """
    Record a feedback signal for a fact (usage outcome).

    Args:
        fact_id: ID of the fact being evaluated
        signal_type: "affirmation", "follow_up", "correction", "derailment", etc.
        signal_value: numeric signal (+0.05 for positive, -0.03 for negative, etc.)
        context: optional context (the user message that triggered the signal)
    """
    with _db_lock:
        conn = _db()
        try:
            outcome_id = f"out_{uuid.uuid4().hex[:12]}"
            ts = _now_iso()
            conn.execute(
                """INSERT INTO fact_usage_outcomes
                   (id, fact_id, ts, signal_type, signal_value, context)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (outcome_id, fact_id, ts, signal_type, signal_value, context),
            )
            conn.commit()
        except Exception as e:
            import logging as _log
            _log.getLogger(__name__).warning(f"[cm] Failed to log outcome: {e}")
        finally:
            conn.close()


def get_recent_outcomes(fact_id: str, days: int = 7) -> list[dict]:
    """
    Get recent feedback signals for a fact (last N days).

    Args:
        fact_id: fact ID to query
        days: lookback window (default 7 days)

    Returns:
        List of outcome dicts with signal_type, signal_value, ts
    """
    with _db_lock:
        conn = _db()
        try:
            cutoff = datetime.now(timezone.utc) - timedelta(days=days)
            cutoff_iso = cutoff.isoformat()
            rows = conn.execute(
                """SELECT signal_type, signal_value, ts, context
                   FROM fact_usage_outcomes
                   WHERE fact_id = ? AND ts > ?
                   ORDER BY ts DESC""",
                (fact_id, cutoff_iso),
            ).fetchall()
        finally:
            conn.close()
    return [dict(r) for r in rows]


def compute_learning_gradient(fact_id: str, days: int = 7) -> float:
    """
    Compute the learning gradient (sum of recent signals) for a fact.

    Args:
        fact_id: fact ID to evaluate
        days: lookback window (default 7 days)

    Returns:
        Sum of signal_value for recent outcomes (can be negative or positive)
    """
    outcomes = get_recent_outcomes(fact_id, days=days)
    return sum(o["signal_value"] for o in outcomes)
