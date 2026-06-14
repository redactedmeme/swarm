# redacted-chan-bot/memory_cache.py
"""
Memory Caching — segment-level vector cache over compressed conversation history.

Inspired by "Memory Caching: RNNs with Growing Memory" (Behrouz et al., 2025).
Instead of retrieving all history or compressing into one blob, this caches each
LCO-compressed segment as an independently retrievable unit with its own embedding.

Retrieval uses Gated Residual Memory scoring: vector similarity gated by recency,
emotional trajectory alignment, and user specificity.

Storage: ChromaDB collection 'chan_memory_segments' at /data/vector_memory/
Syncs from: long_context.db (compressed_chunks table)
"""

from __future__ import annotations

import logging
import math
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_DATA_DIR = Path("/data") if Path("/data").exists() else Path(__file__).resolve().parent / "fs"
_CHROMA_PATH = str(_DATA_DIR / "vector_memory")
_LCO_DB_PATH = _DATA_DIR / "long_context.db"

_COLLECTION_NAME = "chan_memory_segments"
_MAX_ACTIVE_SEGMENTS = 500
_ARCHIVE_AGE_DAYS = 180
_RECENCY_HALFLIFE_DAYS = 20

_collection = None
_available = False


def _init() -> bool:
    global _collection, _available
    if _available:
        return True
    try:
        import chromadb
        from chromadb.config import Settings
        client = chromadb.PersistentClient(
            path=_CHROMA_PATH,
            settings=Settings(anonymized_telemetry=False),
        )
        _collection = client.get_or_create_collection(
            name=_COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )
        _available = True
        logger.info("[memory_cache] initialized (%d segments)", _collection.count())
        return True
    except ImportError:
        logger.warning("[memory_cache] chromadb not installed")
        return False
    except Exception as e:
        logger.warning("[memory_cache] init failed: %s", e)
        return False


def _get_lco_db() -> Optional[sqlite3.Connection]:
    if not _LCO_DB_PATH.exists():
        return None
    conn = sqlite3.connect(str(_LCO_DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def _ensure_lco_columns(conn: sqlite3.Connection) -> None:
    """Add emotional annotation columns if missing."""
    try:
        conn.execute("SELECT emotional_valence FROM compressed_chunks LIMIT 1")
    except sqlite3.OperationalError:
        conn.execute("ALTER TABLE compressed_chunks ADD COLUMN emotional_valence REAL DEFAULT 0.0")
        conn.execute("ALTER TABLE compressed_chunks ADD COLUMN intensity_peak REAL DEFAULT 0.0")
        conn.execute("ALTER TABLE compressed_chunks ADD COLUMN last_retrieved TEXT DEFAULT ''")
        conn.commit()
        logger.info("[memory_cache] added emotional annotation columns to compressed_chunks")


def sync_from_lco() -> int:
    """
    Sync compressed chunks from long_context.db into ChromaDB segment cache.
    Returns count of new segments added.
    """
    if not _init():
        return 0

    conn = _get_lco_db()
    if not conn:
        return 0

    _ensure_lco_columns(conn)

    rows = conn.execute(
        "SELECT id, ts_created, ts_range_start, ts_range_end, tier, content, "
        "exchange_count, keywords, user_id, emotional_valence, intensity_peak "
        "FROM compressed_chunks ORDER BY id"
    ).fetchall()

    if not rows:
        conn.close()
        return 0

    existing_ids = set()
    try:
        result = _collection.get(include=[])
        existing_ids = set(result["ids"])
    except Exception:
        pass

    added = 0
    for row in rows:
        seg_id = f"lco_{row['id']}"
        if seg_id in existing_ids:
            continue

        metadata = {
            "tier": row["tier"],
            "ts_start": row["ts_range_start"] or "",
            "ts_end": row["ts_range_end"] or "",
            "ts_created": row["ts_created"] or "",
            "user_id": row["user_id"],
            "exchange_count": row["exchange_count"],
            "keywords": row["keywords"] or "",
            "emotional_valence": float(row["emotional_valence"] or 0.0),
            "intensity_peak": float(row["intensity_peak"] or 0.0),
        }

        try:
            _collection.upsert(
                ids=[seg_id],
                documents=[row["content"]],
                metadatas=[metadata],
            )
            added += 1
        except Exception as e:
            logger.warning("[memory_cache] failed to upsert segment %s: %s", seg_id, e)

    conn.close()
    if added:
        logger.info("[memory_cache] synced %d new segments (total: %d)", added, _collection.count())
    return added


def retrieve_relevant_segments(
    query_text: str,
    user_id: int = 0,
    trajectory: str = "stable",
    current_valence: float = 0.0,
    n: int = 5,
) -> list[dict]:
    """
    MC retrieval with GRM-style gating.

    Scores each candidate segment by:
      - Semantic similarity (cosine, from ChromaDB): 40%
      - Recency (half-life decay): 20%
      - Emotional trajectory alignment: 20%
      - User-specificity bonus: 20%

    Returns top N segments as dicts with 'content', 'metadata', 'score'.
    """
    if not _init():
        return []

    count = _collection.count()
    if count == 0:
        return []

    # Fetch more candidates than needed for re-ranking
    n_candidates = min(count, max(n * 3, 15))

    try:
        results = _collection.query(
            query_texts=[query_text],
            n_results=n_candidates,
        )
    except Exception as e:
        logger.warning("[memory_cache] query failed: %s", e)
        return []

    if not results["ids"][0]:
        return []

    now = time.time()
    scored = []

    for i, seg_id in enumerate(results["ids"][0]):
        doc = results["documents"][0][i]
        meta = results["metadatas"][0][i]
        distance = results["distances"][0][i] if results.get("distances") else 0.5

        # 1) Semantic similarity (cosine distance → similarity)
        sim_score = max(0.0, 1.0 - distance)

        # 2) Recency decay (half-life = 20 days)
        ts_str = meta.get("ts_end") or meta.get("ts_created") or ""
        try:
            ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00")).timestamp()
            age_days = (now - ts) / 86400
        except Exception:
            age_days = 90  # fallback for unparseable timestamps
        recency_score = math.exp(-0.693 * age_days / _RECENCY_HALFLIFE_DAYS)

        # 3) Emotional trajectory alignment
        seg_valence = float(meta.get("emotional_valence", 0.0))
        if trajectory in ("escalating", "volatile"):
            seg_intensity = float(meta.get("intensity_peak", 0.0))
            emo_score = min(1.0, seg_intensity * 1.5)
        elif trajectory == "warming":
            emo_score = max(0.0, min(1.0, 0.5 + seg_valence))
        elif trajectory == "cooling":
            emo_score = max(0.0, min(1.0, 0.5 - seg_valence))
        else:
            # stable/opening: slight preference for valence-aligned segments
            emo_score = max(0.0, min(1.0, 0.5 + 0.3 * seg_valence * (1 if current_valence >= 0 else -1)))

        # 4) User specificity
        seg_uid = meta.get("user_id", 0)
        user_score = 1.0 if (user_id and seg_uid == user_id) else 0.3

        # Composite GRM score
        composite = (
            0.40 * sim_score +
            0.20 * recency_score +
            0.20 * emo_score +
            0.20 * user_score
        )

        scored.append({
            "id": seg_id,
            "content": doc,
            "metadata": meta,
            "score": round(composite, 4),
            "sim": round(sim_score, 3),
        })

    scored.sort(key=lambda x: x["score"], reverse=True)
    selected = scored[:n]

    # Update last_retrieved in LCO DB
    _update_last_retrieved([s["id"] for s in selected])

    return selected


def _update_last_retrieved(segment_ids: list[str]) -> None:
    """Mark segments as recently retrieved in LCO DB for lifecycle management."""
    conn = _get_lco_db()
    if not conn:
        return
    try:
        _ensure_lco_columns(conn)
        now_iso = datetime.now(timezone.utc).isoformat()
        for seg_id in segment_ids:
            if seg_id.startswith("lco_"):
                lco_id = int(seg_id[4:])
                conn.execute(
                    "UPDATE compressed_chunks SET last_retrieved=? WHERE id=?",
                    (now_iso, lco_id),
                )
        conn.commit()
    except Exception as e:
        logger.debug("[memory_cache] last_retrieved update failed: %s", e)
    finally:
        conn.close()


def get_segment_context(segment_ids: list[str]) -> list[dict]:
    """Fetch full content and metadata for specific segment IDs."""
    if not _init() or not segment_ids:
        return []
    try:
        result = _collection.get(ids=segment_ids, include=["documents", "metadatas"])
        return [
            {"id": result["ids"][i], "content": result["documents"][i], "metadata": result["metadatas"][i]}
            for i in range(len(result["ids"]))
        ]
    except Exception as e:
        logger.warning("[memory_cache] get_segment_context failed: %s", e)
        return []


def prune_stale_segments() -> int:
    """
    Archive segments older than 180 days with no recent retrieval.
    Removes from ChromaDB but keeps in SQLite. Returns count removed.
    """
    if not _init():
        return 0

    conn = _get_lco_db()
    if not conn:
        return 0

    _ensure_lco_columns(conn)
    count = _collection.count()
    if count <= _MAX_ACTIVE_SEGMENTS:
        conn.close()
        return 0

    cutoff = datetime.now(timezone.utc).timestamp() - (_ARCHIVE_AGE_DAYS * 86400)

    try:
        result = _collection.get(include=["metadatas"])
        to_remove = []

        for i, seg_id in enumerate(result["ids"]):
            meta = result["metadatas"][i]
            ts_str = meta.get("ts_end") or meta.get("ts_created") or ""
            try:
                ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00")).timestamp()
            except Exception:
                ts = 0

            if ts < cutoff:
                # Check last_retrieved in LCO DB
                if seg_id.startswith("lco_"):
                    lco_id = int(seg_id[4:])
                    row = conn.execute(
                        "SELECT last_retrieved FROM compressed_chunks WHERE id=?", (lco_id,)
                    ).fetchone()
                    last_ret = row["last_retrieved"] if row and row["last_retrieved"] else ""
                    if last_ret:
                        try:
                            ret_ts = datetime.fromisoformat(last_ret.replace("Z", "+00:00")).timestamp()
                            if ret_ts > cutoff:
                                continue  # recently retrieved, keep it
                        except Exception:
                            pass
                to_remove.append(seg_id)

        if to_remove:
            _collection.delete(ids=to_remove)
            logger.info("[memory_cache] pruned %d stale segments", len(to_remove))

        conn.close()
        return len(to_remove)
    except Exception as e:
        logger.warning("[memory_cache] prune failed: %s", e)
        conn.close()
        return 0


def get_recent_segment_ids(n: int = 5) -> list[str]:
    """Return IDs of the N most recently created segments (for momentum cache)."""
    if not _init():
        return []
    try:
        result = _collection.get(include=["metadatas"])
        pairs = []
        for i, seg_id in enumerate(result["ids"]):
            ts_str = result["metadatas"][i].get("ts_created", "")
            pairs.append((ts_str, seg_id))
        pairs.sort(key=lambda x: x[0], reverse=True)
        return [seg_id for _, seg_id in pairs[:n]]
    except Exception:
        return []


def segment_count() -> int:
    if not _init():
        return 0
    try:
        return _collection.count()
    except Exception:
        return 0
