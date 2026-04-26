# redacted-chan-bot/vector_memory.py
"""
Vector Memory — semantic search over conversation history.

Instead of retrieving the N most recent exchanges, this embeds every
exchange and retrieves the ones *most semantically relevant* to whatever
is being talked about right now.

When you mention your dog, she remembers the conversation about your dog —
not just the last 20 messages. That's the difference.

Storage: ChromaDB at /data/vector_memory/ (Railway persistent volume).
Embedding: ChromaDB default (all-MiniLM-L6-v2 via onnxruntime, ~30MB, no API key).
"""

import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_DATA_DIR = Path("/data") if Path("/data").exists() else Path(__file__).resolve().parent / "fs"
_DATA_DIR.mkdir(parents=True, exist_ok=True)
_CHROMA_PATH = str(_DATA_DIR / "vector_memory")

_client = None
_collection = None
_available = False


def _init() -> bool:
    global _client, _collection, _available
    if _available:
        return True
    try:
        import chromadb
        from chromadb.config import Settings
        _client = chromadb.PersistentClient(
            path=_CHROMA_PATH,
            settings=Settings(anonymized_telemetry=False),
        )
        _collection = _client.get_or_create_collection(
            name="chan_conversations",
            metadata={"hnsw:space": "cosine"},
        )
        _available = True
        logger.info(f"[vector_memory] initialized ({_collection.count()} docs)")
        return True
    except ImportError:
        logger.warning("[vector_memory] chromadb not installed — falling back to recency")
        return False
    except Exception as e:
        logger.warning(f"[vector_memory] init failed: {e}")
        return False


def add_exchange(
    doc_id: str,
    user_msg: str,
    bot_reply: str,
    metadata: Optional[dict] = None,
) -> bool:
    """
    Embed and store a conversation exchange.
    doc_id should be unique per exchange (e.g. timestamp-based).
    """
    if not _init():
        return False
    try:
        combined = f"user: {user_msg}\nchan: {bot_reply}"
        meta = {
            "user_msg":  user_msg[:500],
            "bot_reply": bot_reply[:500],
            **(metadata or {}),
        }
        _collection.upsert(
            ids=[doc_id],
            documents=[combined],
            metadatas=[meta],
        )
        return True
    except Exception as e:
        logger.warning(f"[vector_memory] add_exchange failed: {e}")
        return False


def search(query: str, n: int = 5, where: Optional[dict] = None) -> list[dict]:
    """
    Semantic search over stored exchanges.
    Returns list of {user_msg, bot_reply, distance, metadata}.
    """
    if not _init():
        return []
    try:
        count = _collection.count()
        if count == 0:
            return []
        n = min(n, count)
        kwargs = {"query_texts": [query], "n_results": n}
        if where:
            kwargs["where"] = where
        results = _collection.query(**kwargs)
        out = []
        for i, doc_id in enumerate(results["ids"][0]):
            meta = results["metadatas"][0][i]
            dist = results["distances"][0][i] if results.get("distances") else 1.0
            out.append({
                "id":        doc_id,
                "user_msg":  meta.get("user_msg", ""),
                "bot_reply": meta.get("bot_reply", ""),
                "distance":  round(dist, 3),
                "metadata":  meta,
            })
        return out
    except Exception as e:
        logger.warning(f"[vector_memory] search failed: {e}")
        return []


def get_for_prompt(current_msg: str, n: int = 4) -> str:
    """
    Retrieve semantically relevant past moments for system prompt injection.
    Only returns results with cosine distance < 0.6 (meaningfully similar).
    """
    hits = search(current_msg, n=n)
    relevant = [h for h in hits if h["distance"] < 0.6]
    if not relevant:
        return ""

    lines = ["## Relevant Past Moments (semantic memory)"]
    for h in relevant:
        lines.append(f"- you said: \"{h['user_msg'][:100]}\"")
        lines.append(f"  i said:   \"{h['bot_reply'][:100]}\"")
    return "\n".join(lines)


def count() -> int:
    if not _init():
        return 0
    try:
        return _collection.count()
    except Exception:
        return 0
