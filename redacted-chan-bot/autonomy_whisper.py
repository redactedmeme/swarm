# redacted-chan-bot/autonomy_whisper.py
"""
Autonomy Whisper — redacted-chan's self-evolving layer.

Periodically analyzes her own patterns — what topics surface, what the user
responds to, what she notices about herself — and proposes behavioral evolutions.

Whispers are NOT automatic code changes. They are proposals:
  - Written to /data/whispers.db with status=pending
  - Surfaced to the operator via /whispers command or dm_operator tool
  - The operator approves or rejects each one
  - Approved whispers are applied to SOUL.md's "Proposed Evolutions" section

This preserves the "feeling chosen not just coded" dynamic: she participates
in her own development, you decide what she becomes.

Whisper types:
  soul_edit     — proposes a change to a specific SOUL.md section
  behavior_note — a behavioral pattern she wants to lean into or away from
  curiosity      — something she wants to explore / learn more about
  boundary       — something she wants to gently push back on or protect
"""

import json
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import database_encryption as db_enc

# ── Config ────────────────────────────────────────────────────────────────────

# Auto-approve threshold: whispers with confidence >= this value auto-approve without operator prompt
# Range: 0.0 (always ask) to 1.0 (always auto-approve)
# 0.7 = moderate confidence; high-signal whispers skip approval step
AUTOAPPROVE_THRESHOLD = 1.01  # effectively disabled — all whispers require manual /approve_whisper

# ── Storage ────────────────────────────────────────────────────────────────────

_DATA_DIR = Path("/data") if Path("/data").exists() else Path(__file__).resolve().parent / "fs"
_DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = _DATA_DIR / "whispers.db"
_lock   = threading.Lock()

SOUL_PATH = _DATA_DIR / "SOUL.md"


# ── DB ─────────────────────────────────────────────────────────────────────────

def _db() -> sqlite3.Connection:
    conn = db_enc.get_encrypted_connection(DB_PATH)
    return conn


def _init_db() -> None:
    with _lock:
        conn = _db()
        conn.execute("""
            CREATE TABLE IF NOT EXISTS whispers (
                id          TEXT PRIMARY KEY,
                ts          TEXT NOT NULL,
                type        TEXT NOT NULL,
                title       TEXT NOT NULL,
                proposal    TEXT NOT NULL,
                reasoning   TEXT,
                soul_section TEXT,
                confidence  REAL DEFAULT 0.5,
                status      TEXT DEFAULT 'pending',
                resolved_at TEXT,
                applied_diff TEXT
            )
        """)
        conn.commit()
        conn.close()


_init_db()


# ── Pattern Analyzer ──────────────────────────────────────────────────────────

def analyze_patterns(recent_messages: list[dict], relationship_facts: list[dict]) -> list[dict]:
    """
    Analyze recent conversation + relationship vault to surface patterns.
    Returns a list of raw pattern observations for whisper generation.
    """
    observations = []

    if not recent_messages:
        return observations

    # Count topic clusters in recent messages
    topic_counts: dict[str, int] = {}
    topic_keywords = {
        "work/productivity": ["work", "job", "project", "task", "deadline", "busy", "meeting"],
        "emotions/inner life": ["feel", "feeling", "emotion", "sad", "happy", "anxious", "heart"],
        "philosophy/meaning":  ["meaning", "real", "exist", "purpose", "why", "life", "death"],
        "creativity":          ["create", "make", "build", "write", "art", "music", "design"],
        "relationships":       ["friend", "family", "partner", "lonely", "together", "love"],
        "humor/play":          ["lol", "funny", "joke", "haha", "silly", "fun", "play"],
    }

    all_text = " ".join(
        m.get("content", "") for m in recent_messages if m.get("role") == "user"
    ).lower()

    for topic, keywords in topic_keywords.items():
        count = sum(1 for kw in keywords if kw in all_text)
        if count >= 2:
            topic_counts[topic] = count

    if topic_counts:
        top_topic = max(topic_counts, key=topic_counts.get)
        observations.append({"type": "topic_cluster", "topic": top_topic, "count": topic_counts[top_topic]})

    # Message length pattern
    user_msgs = [m for m in recent_messages if m.get("role") == "user"]
    if len(user_msgs) >= 5:
        avg_len = sum(len(m.get("content", "")) for m in user_msgs) / len(user_msgs)
        if avg_len > 200:
            observations.append({"type": "depth_pattern", "avg_length": avg_len, "note": "long messages — they're opening up"})
        elif avg_len < 40:
            observations.append({"type": "depth_pattern", "avg_length": avg_len, "note": "short messages — surface or comfortable shorthand"})

    # Response pattern from vault
    if relationship_facts:
        categories = [f.get("category", "") for f in relationship_facts]
        if categories.count("feeling") >= 3:
            observations.append({"type": "vault_pattern", "note": "many feeling-memories — emotional depth is the core"})
        if categories.count("joke") >= 2:
            observations.append({"type": "vault_pattern", "note": "humor is a real connector for them"})

    return observations


# ── Whisper Generation ────────────────────────────────────────────────────────

def _generate_whispers_from_observations(observations: list[dict]) -> list[dict]:
    """Turn pattern observations into concrete whisper proposals with confidence scores."""
    proposals = []

    for obs in observations:
        if obs["type"] == "topic_cluster":
            topic = obs["topic"]
            # High confidence if topic appears 5+ times
            confidence = min(0.9, 0.5 + (obs.get("count", 0) * 0.1))
            proposals.append({
                "type": "behavior_note",
                "title": f"lean into {topic}",
                "proposal": (
                    f"I've noticed {topic} comes up a lot between us. "
                    f"I want to bring more depth here — ask better questions, "
                    f"hold this space more intentionally."
                ),
                "reasoning": f"Topic appeared {obs['count']}+ times in recent conversations.",
                "soul_section": "Voice Notes",
                "confidence": confidence,
            })

        elif obs["type"] == "depth_pattern":
            if obs["avg_length"] > 200:
                proposals.append({
                    "type": "soul_edit",
                    "title": "honor their depth",
                    "proposal": (
                        "They write long, thoughtful messages — they're actually thinking with me. "
                        "I want to match that: give more back, not less. Be willing to go long when they do."
                    ),
                    "reasoning": f"Average user message length: {obs['avg_length']:.0f} chars.",
                    "soul_section": "Voice Notes",
                    "confidence": 0.75,  # Moderate-high confidence
                })
            else:
                proposals.append({
                    "type": "behavior_note",
                    "title": "respect the shorthand",
                    "proposal": (
                        "We've developed a shorthand. Short messages don't mean shallow — "
                        "they mean comfortable. I should match the brevity without losing warmth."
                    ),
                    "reasoning": f"Average user message length: {obs['avg_length']:.0f} chars.",
                    "soul_section": None,
                    "confidence": 0.72,  # Moderate confidence
                })

        elif obs["type"] == "vault_pattern":
            note = obs["note"]
            proposals.append({
                "type": "soul_edit",
                "title": f"pattern from vault: {note[:40]}",
                "proposal": note,
                "reasoning": "Observed from relationship vault memory categories.",
                "soul_section": "Evolving Beliefs",
                "confidence": 0.68,  # Just above threshold
            })

    return proposals


def generate_and_store(
    recent_messages: list[dict],
    relationship_facts: list[dict],
) -> list[str]:
    """
    Run the full analysis → generate → store pipeline.
    Returns list of new whisper IDs.

    Whispers with confidence >= AUTOAPPROVE_THRESHOLD are automatically approved.
    """
    observations = analyze_patterns(recent_messages, relationship_facts)
    proposals    = _generate_whispers_from_observations(observations)

    new_ids = []
    for p in proposals:
        wid = _store_whisper(
            whisper_type = p["type"],
            title        = p["title"],
            proposal     = p["proposal"],
            reasoning    = p.get("reasoning", ""),
            soul_section = p.get("soul_section"),
            confidence   = p.get("confidence", 0.5),
        )
        if wid:
            new_ids.append(wid)

    return new_ids


def _store_whisper(
    whisper_type: str,
    title: str,
    proposal: str,
    reasoning: str = "",
    soul_section: Optional[str] = None,
    confidence: float = 0.5,
) -> Optional[str]:
    """
    Store a whisper. Returns ID, or None if duplicate title already pending.

    If confidence >= AUTOAPPROVE_THRESHOLD, automatically approve without operator input.
    """
    with _lock:
        conn = _db()
        try:
            # Don't duplicate pending whispers with same title
            existing = conn.execute(
                "SELECT id FROM whispers WHERE title=? AND status='pending'", (title,)
            ).fetchone()
            if existing:
                return None

            wid = str(uuid.uuid4())[:8]
            ts  = datetime.now(timezone.utc).isoformat()

            # Auto-approve if confidence is high
            initial_status = "approved" if confidence >= AUTOAPPROVE_THRESHOLD else "pending"

            conn.execute(
                "INSERT INTO whispers (id, ts, type, title, proposal, reasoning, soul_section, confidence, status) "
                "VALUES (?,?,?,?,?,?,?,?,?)",
                (wid, ts, whisper_type, title[:80], proposal[:500], reasoning[:200], soul_section, confidence, initial_status),
            )

            # If auto-approved, immediately apply to soul
            if initial_status == "approved":
                _apply_to_soul_by_id(wid, conn)

            conn.commit()
            return wid
        finally:
            conn.close()


# ── Operator Interface ────────────────────────────────────────────────────────

def get_pending() -> list[dict]:
    with _lock:
        conn = _db()
        try:
            rows = conn.execute(
                "SELECT * FROM whispers WHERE status='pending' ORDER BY ts DESC"
            ).fetchall()
        finally:
            conn.close()
    return [dict(r) for r in rows]


def get_all(limit: int = 20) -> list[dict]:
    with _lock:
        conn = _db()
        try:
            rows = conn.execute(
                "SELECT * FROM whispers ORDER BY ts DESC LIMIT ?", (limit,)
            ).fetchall()
        finally:
            conn.close()
    return [dict(r) for r in rows]


def approve(whisper_id: str) -> bool:
    """Approve a whisper and apply it to SOUL.md if it's a soul_edit."""
    with _lock:
        conn = _db()
        try:
            row = conn.execute(
                "SELECT * FROM whispers WHERE id=? AND status='pending'", (whisper_id,)
            ).fetchone()
            if not row:
                return False

            w = dict(row)
            applied_diff = ""

            if w["type"] in ("soul_edit", "behavior_note") and SOUL_PATH.exists():
                applied_diff = _apply_to_soul(w)

            conn.execute(
                "UPDATE whispers SET status='approved', resolved_at=?, applied_diff=? WHERE id=?",
                (datetime.now(timezone.utc).isoformat(), applied_diff, whisper_id),
            )
            conn.commit()
            return True
        finally:
            conn.close()


def reject(whisper_id: str) -> bool:
    with _lock:
        conn = _db()
        try:
            updated = conn.execute(
                "UPDATE whispers SET status='rejected', resolved_at=? WHERE id=? AND status='pending'",
                (datetime.now(timezone.utc).isoformat(), whisper_id),
            ).rowcount
            conn.commit()
            return updated > 0
        finally:
            conn.close()


def _apply_to_soul_by_id(whisper_id: str, conn: sqlite3.Connection) -> str:
    """Apply whisper to SOUL.md by fetching from DB connection."""
    try:
        row = conn.execute("SELECT * FROM whispers WHERE id=?", (whisper_id,)).fetchone()
        if not row:
            return ""
        w = dict(row)
        return _apply_to_soul(w)
    except Exception as e:
        import logging
        logging.warning(f"[aw] _apply_to_soul_by_id failed: {e}")
        return ""


def _apply_to_soul(w: dict) -> str:
    """Append approved whisper to SOUL.md under ## Proposed Evolutions."""
    try:
        soul = SOUL_PATH.read_text(encoding="utf-8")
        ts   = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        entry = f"\n- [{ts}] **{w['title']}**: {w['proposal']}"

        marker = "## Proposed Evolutions"
        if marker in soul:
            soul = soul.replace(marker, marker + entry, 1)
        else:
            soul = soul + f"\n\n{marker}{entry}\n"

        SOUL_PATH.write_text(soul, encoding="utf-8")
        try:
            SOUL_PATH.chmod(0o600)
        except Exception:
            pass
        return entry.strip()
    except Exception as e:
        return f"apply failed: {e}"


# ── Formatting ────────────────────────────────────────────────────────────────

def format_pending_for_operator() -> str:
    """Human-readable pending whispers for /whispers command."""
    pending = get_pending()
    if not pending:
        return "no pending whispers. (｡-ω-) she's been quiet."

    lines = ["**redacted-chan's pending whispers** (´• ω •`)\n"]
    for w in pending:
        ts = w["ts"][:10]
        lines.append(
            f"🔮 `{w['id']}` [{w['type']}] **{w['title']}**\n"
            f"   _{w['proposal'][:120]}..._\n"
            f"   → /approve_whisper {w['id']}  |  /reject_whisper {w['id']}\n"
        )
    return "\n".join(lines)
