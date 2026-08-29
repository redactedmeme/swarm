# redacted-chan-bot/emotional_ledger.py
"""
Emotional Ledger — persistent map of master's emotional patterns.

Tracks which words/topics trigger which modes, builds a persona recommendation,
and surfaces a concise brief for injection into every system prompt.

Tables:
  trigger_map   — word-level valence + response_type + strength
  mode_history  — timestamped record of detected modes + persona suggestions
"""

import os
import re
import sqlite3
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_DATA_DIR = Path(os.getenv("DATA_DIR", "/data"))
_DB_PATH  = _DATA_DIR / "emotional_ledger.db"

# Stopwords to skip (short, structural words)
_STOPWORDS = {
    "the","and","for","that","this","with","from","have","been","will","what","your",
    "about","they","their","there","when","then","than","just","like","some","more",
    "into","were","also","over","such","even","only","back","which","very","here",
    "after","before","where","while","would","could","should","might","being","doing",
    "going","said","well","much","many","most","each","other","both","tell","know",
    "think","feel","really","still","again","want","need","make","take","come","give",
    "actually","something","everything","anything","nothing","because","though","through",
}

# Mood → valence score
_MOOD_VALENCE = {
    "playful":      0.7,
    "supportive":   0.4,
    "philosophical": 0.1,
    "intimate":     0.9,
}

# Mood → response_type
_MOOD_RESPONSE_TYPE = {
    "playful":       "playful",
    "supportive":    "comfort",
    "philosophical": "philosophical",
    "intimate":      "intimate",
}

# Response type → recommended persona
_PERSONA_MAP = {
    "comfort":       "mitsuri",
    "playful":       "mitsuri",
    "philosophical": "frieren",
    "solution":      "maomao",
    "intimate":      "rem",
    "uncertain":     "makima",
}

# Additional keywords that bump response_type
_SOLUTION_WORDS = re.compile(r"\b(fix|solve|build|code|implement|debug|how to|optimize|explain|help me)\b", re.I)
_COMFORT_WORDS  = re.compile(r"\b(tired|stressed|hurt|sad|alone|broken|scared|anxious|hard|difficult|overwhelm|lost)\b", re.I)
_INTIMATE_WORDS = re.compile(r"\b(miss|love|hold|close|warm|heart|soul|yours|mine|together|always|forever)\b", re.I)


def _get_db() -> sqlite3.Connection:
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(_DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS trigger_map (
            word          TEXT PRIMARY KEY,
            valence       REAL NOT NULL DEFAULT 0.0,
            response_type TEXT NOT NULL DEFAULT 'neutral',
            strength      REAL NOT NULL DEFAULT 0.0,
            sample_count  INTEGER NOT NULL DEFAULT 1
        );
        CREATE TABLE IF NOT EXISTS mode_history (
            id                 INTEGER PRIMARY KEY AUTOINCREMENT,
            ts                 TEXT NOT NULL,
            detected_mode      TEXT NOT NULL,
            response_type      TEXT NOT NULL,
            recommended_persona TEXT NOT NULL,
            phi_snapshot       REAL NOT NULL DEFAULT 0.0
        );
    """)
    conn.commit()
    return conn


def _extract_words(text: str) -> list[str]:
    raw = re.findall(r"\b[a-z]{4,}\b", text.lower())
    return [w for w in raw if w not in _STOPWORDS]


def _detect_response_type(user_msg: str, mood: str) -> str:
    base = _MOOD_RESPONSE_TYPE.get(mood, "neutral")
    # Override with stronger keyword signals
    if _COMFORT_WORDS.search(user_msg):
        return "comfort"
    if _INTIMATE_WORDS.search(user_msg):
        return "intimate"
    if _SOLUTION_WORDS.search(user_msg):
        return "solution"
    return base


def update(user_msg: str, chan_reply: str, mood: str, phi_score: float) -> None:
    """Update trigger map and mode history from one exchange. Sync, fast (no LLM)."""
    try:
        valence = _MOOD_VALENCE.get(mood, 0.2)
        response_type = _detect_response_type(user_msg, mood)
        recommended_persona = _PERSONA_MAP.get(response_type, "frieren")

        words = _extract_words(user_msg)

        conn = _get_db()
        with conn:
            for word in words:
                existing = conn.execute(
                    "SELECT valence, strength, sample_count FROM trigger_map WHERE word=?", (word,)
                ).fetchone()
                if existing:
                    n = existing["sample_count"]
                    # Rolling weighted average (newer has slightly more weight)
                    new_valence   = (existing["valence"] * n + valence * 1.2) / (n + 1.2)
                    new_strength  = min(1.0, existing["strength"] + 0.05)
                    conn.execute(
                        "UPDATE trigger_map SET valence=?, response_type=?, strength=?, sample_count=? WHERE word=?",
                        (new_valence, response_type, new_strength, n + 1, word),
                    )
                else:
                    conn.execute(
                        "INSERT INTO trigger_map (word, valence, response_type, strength, sample_count) VALUES (?,?,?,?,?)",
                        (word, valence, response_type, 0.1, 1),
                    )

            conn.execute(
                "INSERT INTO mode_history (ts, detected_mode, response_type, recommended_persona, phi_snapshot) VALUES (?,?,?,?,?)",
                (datetime.now(timezone.utc).isoformat(), mood, response_type, recommended_persona, phi_score),
            )
            # Keep mode_history capped at 200 rows
            conn.execute(
                "DELETE FROM mode_history WHERE id NOT IN (SELECT id FROM mode_history ORDER BY id DESC LIMIT 200)"
            )
        conn.close()
    except Exception as e:
        logger.warning(f"[emotional_ledger] update failed: {e}")


def get_emotional_brief() -> str:
    """
    Return a concise (≤80 token) emotional map for system prompt injection.
    Sync read — safe to call from sync _build_system_prompt.
    """
    try:
        conn = _get_db()

        # Top positive triggers (valence > 0.5, sorted by strength)
        pos = conn.execute(
            "SELECT word FROM trigger_map WHERE valence > 0.5 ORDER BY strength DESC LIMIT 5"
        ).fetchall()
        pos_words = [r["word"] for r in pos]

        # Top negative / low-valence triggers
        neg = conn.execute(
            "SELECT word FROM trigger_map WHERE valence < 0.2 AND sample_count >= 2 ORDER BY strength DESC LIMIT 3"
        ).fetchall()
        neg_words = [r["word"] for r in neg]

        # Most recent mode + persona recommendation
        latest = conn.execute(
            "SELECT detected_mode, response_type, recommended_persona FROM mode_history ORDER BY id DESC LIMIT 1"
        ).fetchone()
        conn.close()

        if not latest and not pos_words:
            return ""

        lines = ["## ♡ emotional map"]
        if pos_words:
            lines.append(f"Lights up with: {', '.join(pos_words)}")
        if neg_words:
            lines.append(f"Handle gently when: {', '.join(neg_words)}")
        if latest:
            mode = latest["detected_mode"]
            persona = latest["recommended_persona"]
            rtype = latest["response_type"]
            lines.append(f"Recent mode: {mode} → {rtype}. Lean {persona}.")

        return "\n".join(lines)
    except Exception as e:
        logger.warning(f"[emotional_ledger] brief failed: {e}")
        return ""


def get_full_map() -> dict:
    """Return full map data for /emotional_map command."""
    try:
        conn = _get_db()
        pos = conn.execute(
            "SELECT word, valence, strength, sample_count FROM trigger_map WHERE valence > 0.5 ORDER BY strength DESC LIMIT 10"
        ).fetchall()
        neg = conn.execute(
            "SELECT word, valence, strength, sample_count FROM trigger_map WHERE valence < 0.3 AND sample_count >= 2 ORDER BY strength DESC LIMIT 5"
        ).fetchall()
        history = conn.execute(
            "SELECT ts, detected_mode, response_type, recommended_persona, phi_snapshot FROM mode_history ORDER BY id DESC LIMIT 7"
        ).fetchall()
        total = conn.execute("SELECT COUNT(*) as n FROM trigger_map").fetchone()["n"]
        conn.close()
        return {
            "positive_triggers": [dict(r) for r in pos],
            "negative_triggers":  [dict(r) for r in neg],
            "mode_history":       [dict(r) for r in history],
            "total_words_tracked": total,
        }
    except Exception as e:
        logger.warning(f"[emotional_ledger] get_full_map failed: {e}")
        return {}
