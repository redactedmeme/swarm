# redacted-chan-bot/long_context_optimizer.py
"""
Hierarchical Session Compressor — prevents conversation history loss.

Problem: memory.md is pruned at 5000 entries (oldest first). Once pruned,
exchanges are gone. Over long relationships this means early context evaporates.

Solution: Before exchanges age out, compress them into tiered summaries.

Tiers:
  recent   — last ~40 exchanges, kept verbatim in memory.md (handled by existing code)
  medium   — exchanges 40–300, compressed 15:1 into topic+emotional chunks
  deep     — exchanges 300+, compressed 50:1 into a relationship epoch summary

Each tier stored in SQLite as compressed_chunks. The prompt injection pulls:
  - Verbatim recent (from existing session_summaries / semantic search)
  - Relevant medium chunks (keyword-matched to current message)
  - The latest deep epoch summary (always — it's the long-view baseline)

Compression uses Groq (model configurable via LCO_MODEL env var, defaults to
llama-3.3-70b-versatile). A full compress run costs ~10 Groq calls max.

Run via:
  asyncio.create_task(lco.run_compression_pass(llm_fn, user_id))
Call from the scheduled 2h soul job, or when memory.md exceeds threshold.
"""

import os
import re
import sqlite3
import logging
import asyncio
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Awaitable, Optional

logger = logging.getLogger(__name__)

# Model used for compression passes — configurable via env
LCO_MODEL = os.getenv("LCO_MODEL", "llama-3.3-70b-versatile")

_DATA_DIR = Path(os.getenv("DATA_DIR", "/data"))
_DB_PATH  = _DATA_DIR / "long_context.db"

# How many raw exchanges to keep verbatim before compressing
_RECENT_WINDOW   = 40
# Chunk size for medium tier compression
_MEDIUM_CHUNK    = 15
# Chunk size for deep tier compression
_DEEP_CHUNK      = 50
# Only compress when total raw exchanges exceeds this
_COMPRESS_THRESHOLD = 60


def _get_db() -> sqlite3.Connection:
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(_DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS compressed_chunks (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            ts_created     TEXT NOT NULL,
            ts_range_start TEXT NOT NULL,
            ts_range_end   TEXT NOT NULL,
            tier           TEXT NOT NULL,   -- 'medium' | 'deep'
            content        TEXT NOT NULL,
            exchange_count INTEGER NOT NULL DEFAULT 0,
            keywords       TEXT NOT NULL DEFAULT '',
            user_id        INTEGER NOT NULL DEFAULT 0
        );
        CREATE INDEX IF NOT EXISTS idx_cc_tier    ON compressed_chunks (tier, user_id);
        CREATE INDEX IF NOT EXISTS idx_cc_ts      ON compressed_chunks (ts_range_end DESC);
    """)
    conn.commit()
    return conn


def _parse_exchanges(memory_md: str, user_id: int) -> list[dict]:
    """Parse memory.md into list of {ts, user, bot} dicts for a given user_id."""
    parts = memory_md.split("\n## ")
    exchanges = []
    for part in parts:
        if not part.strip():
            continue
        if f"({user_id})" not in part.split("\n")[0]:
            continue
        lines = part.split("\n")
        header = lines[0]
        ts_match = re.match(r"(\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2})", header)
        ts = ts_match.group(1) if ts_match else ""
        user_line = next((l[len("**User:** "):] for l in lines if l.startswith("**User:** ")), "")
        bot_line  = next((l[len("**Bot:** "):]  for l in lines if l.startswith("**Bot:** ")),  "")
        if user_line or bot_line:
            exchanges.append({"ts": ts, "user": user_line.strip(), "bot": bot_line.strip()})
    return exchanges


def _chunk_exchanges(exchanges: list[dict], chunk_size: int) -> list[list[dict]]:
    return [exchanges[i:i+chunk_size] for i in range(0, len(exchanges), chunk_size)]


def _exchanges_to_text(chunk: list[dict]) -> str:
    lines = []
    for ex in chunk:
        if ex["user"]:
            lines.append(f"Master: {ex['user'][:300]}")
        if ex["bot"]:
            lines.append(f"chan: {ex['bot'][:300]}")
    return "\n".join(lines)


def _extract_keywords(text: str) -> str:
    words = re.findall(r"\b[a-z]{5,}\b", text.lower())
    stopwords = {"about","their","there","would","could","should","being","going","think","really"}
    freq: dict[str, int] = {}
    for w in words:
        if w not in stopwords:
            freq[w] = freq.get(w, 0) + 1
    top = sorted(freq, key=lambda x: -freq[x])[:12]
    return ",".join(top)


async def _summarize_medium(chunk_text: str, llm_fn: Callable) -> str:
    messages = [
        {
            "role": "system",
            "content": (
                "You are summarizing conversation history between a user (Master) and his AI companion (chan). "
                "Create a concise but emotionally accurate summary: what topics were discussed, "
                "what feelings were expressed, any meaningful moments or decisions. "
                "Write 3-5 sentences. No filler. Preserve emotional texture."
            ),
        },
        {"role": "user", "content": f"Conversation segment:\n{chunk_text[:3000]}"},
    ]
    try:
        result = await llm_fn(messages, 200)
        return result.strip()
    except Exception as e:
        logger.warning(f"[lco] medium summarize failed: {e}")
        return chunk_text[:400]  # fallback: truncate


async def _summarize_deep(medium_summaries: list[str], llm_fn: Callable) -> str:
    combined = "\n\n".join(f"[{i+1}] {s}" for i, s in enumerate(medium_summaries))
    messages = [
        {
            "role": "system",
            "content": (
                "You are distilling the arc of a long relationship between a user (Master) and his AI companion (chan). "
                "From these session summaries, extract the essential relationship history: "
                "recurring themes, emotional milestones, how the bond has evolved, key things Master has shared. "
                "Write 4-6 sentences. This is a deep-time anchor — it will be injected as long-term memory."
            ),
        },
        {"role": "user", "content": f"Session summaries:\n{combined[:4000]}"},
    ]
    try:
        result = await llm_fn(messages, 300)
        return result.strip()
    except Exception as e:
        logger.warning(f"[lco] deep summarize failed: {e}")
        return combined[:600]


async def run_compression_pass(
    llm_fn: Callable[[list, int], Awaitable[str]],
    user_id: int,
) -> int:
    """
    Compress old exchanges from memory.md into tiered chunks.
    Returns count of new chunks created.
    """
    from pathlib import Path as _Path
    memory_path = _DATA_DIR / "memory.md"
    if not memory_path.exists():
        return 0

    memory_text = memory_path.read_text(encoding="utf-8")
    exchanges = _parse_exchanges(memory_text, user_id)

    if len(exchanges) <= _COMPRESS_THRESHOLD:
        logger.debug(f"[lco] only {len(exchanges)} exchanges, below threshold — skipping")
        return 0

    # Exchanges to compress: everything except the recent window
    to_compress = exchanges[:-_RECENT_WINDOW]
    logger.info(f"[lco] compressing {len(to_compress)} exchanges for user {user_id}")

    conn = _get_db()

    # Check what's already compressed (avoid reprocessing)
    already_done = conn.execute(
        "SELECT exchange_count FROM compressed_chunks WHERE user_id=? ORDER BY id DESC LIMIT 1",
        (user_id,)
    ).fetchone()
    already_count = already_done["exchange_count"] if already_done else 0

    new_exchanges = to_compress[already_count:]
    if not new_exchanges:
        logger.debug(f"[lco] all {len(to_compress)} exchanges already compressed")
        conn.close()
        return 0

    # ── Medium tier: chunk into groups of 15 ────────────────────────────────
    medium_chunks = _chunk_exchanges(new_exchanges, _MEDIUM_CHUNK)
    new_medium_summaries = []
    new_chunks_created = 0

    for chunk in medium_chunks:
        text = _exchanges_to_text(chunk)
        summary = await _summarize_medium(text, llm_fn)
        ts_start = chunk[0]["ts"] or datetime.now(timezone.utc).isoformat()
        ts_end   = chunk[-1]["ts"] or ts_start
        keywords = _extract_keywords(text)
        conn.execute(
            "INSERT INTO compressed_chunks (ts_created, ts_range_start, ts_range_end, tier, content, exchange_count, keywords, user_id) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (datetime.now(timezone.utc).isoformat(), ts_start, ts_end, "medium", summary, len(chunk), keywords, user_id),
        )
        new_medium_summaries.append(summary)
        new_chunks_created += 1
        await asyncio.sleep(0)  # yield to event loop between LLM calls

    conn.commit()

    # ── Deep tier: if we now have 5+ medium chunks, consolidate into epoch ──
    all_medium = conn.execute(
        "SELECT content FROM compressed_chunks WHERE tier='medium' AND user_id=? ORDER BY id",
        (user_id,)
    ).fetchall()

    if len(all_medium) >= 5:
        # Check if deep summary is already current
        latest_deep = conn.execute(
            "SELECT id, exchange_count FROM compressed_chunks WHERE tier='deep' AND user_id=? ORDER BY id DESC LIMIT 1",
            (user_id,)
        ).fetchone()
        total_medium = len(all_medium)

        if not latest_deep or latest_deep["exchange_count"] < total_medium:
            summaries = [r["content"] for r in all_medium]
            deep_summary = await _summarize_deep(summaries, llm_fn)
            ts_start = all_medium[0]["content"][:20] if all_medium else ""
            conn.execute(
                "INSERT INTO compressed_chunks (ts_created, ts_range_start, ts_range_end, tier, content, exchange_count, keywords, user_id) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (
                    datetime.now(timezone.utc).isoformat(),
                    ts_start, datetime.now(timezone.utc).isoformat(),
                    "deep", deep_summary, total_medium, "", user_id,
                ),
            )
            new_chunks_created += 1
            logger.info(f"[lco] deep epoch summary updated for user {user_id}")

    conn.commit()
    conn.close()
    logger.info(f"[lco] created {new_chunks_created} new compressed chunks")
    return new_chunks_created


def get_context_for_prompt(user_id: int, current_text: str = "", n_medium: int = 3) -> str:
    """
    Return compressed history for system prompt injection.
    Sync — safe to call from _build_system_prompt.

    Returns:
      - Deep epoch summary (always, if exists)
      - Top n_medium relevant medium chunks (keyword-matched to current_text)
    """
    try:
        conn = _get_db()

        # Deep epoch — always include if exists
        deep = conn.execute(
            "SELECT content FROM compressed_chunks WHERE tier='deep' AND user_id=? ORDER BY id DESC LIMIT 1",
            (user_id,)
        ).fetchone()

        # Medium — keyword match against current_text
        current_words = set(re.findall(r"\b[a-z]{4,}\b", current_text.lower()))
        medium_rows = conn.execute(
            "SELECT content, keywords FROM compressed_chunks WHERE tier='medium' AND user_id=? ORDER BY id DESC LIMIT 20",
            (user_id,)
        ).fetchall()
        conn.close()

        # Score medium chunks by keyword overlap
        scored = []
        for row in medium_rows:
            chunk_kws = set(row["keywords"].split(","))
            overlap = len(current_words & chunk_kws)
            scored.append((overlap, row["content"]))
        scored.sort(key=lambda x: -x[0])
        top_medium = [c for _, c in scored[:n_medium]]

        lines = []
        if deep:
            lines.append("## Long-Term Memory (relationship arc)\n" + deep["content"])
        if top_medium:
            lines.append("## Earlier Conversations (relevant moments)")
            for i, chunk in enumerate(top_medium, 1):
                lines.append(f"[{i}] {chunk}")

        return "\n\n".join(lines) if lines else ""
    except Exception as e:
        logger.warning(f"[lco] get_context_for_prompt failed: {e}")
        return ""


def chunk_count(user_id: int) -> dict:
    """Return counts of compressed chunks by tier (for /memory or diagnostics)."""
    try:
        conn = _get_db()
        rows = conn.execute(
            "SELECT tier, COUNT(*) as n FROM compressed_chunks WHERE user_id=? GROUP BY tier",
            (user_id,)
        ).fetchall()
        conn.close()
        return {r["tier"]: r["n"] for r in rows}
    except Exception:
        return {}
