# redacted-chan-bot/deep_recall.py
"""
Deep Recall — full conversation history search when she needs to remember.

When master asks "remember when...", "what did we talk about...", "last time
you mentioned...", this module does a broad, multi-source search across:
  1. Vector memory (ChromaDB) — semantic search, 20+ hits
  2. memory.md — full-text keyword search across all 5000 entries
  3. Relationship vault — FTS search for curated moments
  4. Long-context compressed chunks — keyword match against medium-tier summaries

The result is formatted as a large recall block injected into the system prompt.
With 128k token context on Gemma 4, we can afford to inject 50+ relevant exchanges.

This replaces the narrow self_recall.py for memory questions while keeping
self_recall for simple timestamp queries.
"""

import re
import logging
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

_RECALL_PATTERNS = re.compile(
    r'(remember\s+(?:when|that|the|how|what|if)|'
    r'do you recall|'
    r'what did (?:we|you|i)\s+(?:talk|say|discuss|mention)|'
    r'when did (?:we|you|i)|'
    r'last time (?:we|you|i)|'
    r'have (?:we|you|i) ever|'
    r'did (?:we|you|i) (?:ever|once)|'
    r'what was (?:that|the) (?:thing|time|conversation)|'
    r'that (?:time|day|night|conversation) (?:when|where)|'
    r'you (?:once|used to) (?:said|told|mentioned|asked)|'
    r'we (?:once|used to) (?:talked|discussed|said)|'
    r'how long (?:ago|since)|'
    r'what (?:were|was) (?:we|that)|'
    r'tell me about (?:when|the time)|'
    r'you said something (?:about|like)|'
    r'i told you (?:about|that)|'
    r'(?:first|earliest) (?:time|thing|conversation))',
    re.IGNORECASE,
)

_TOPIC_EXTRACT = re.compile(
    r'(?:remember|recall|about|when|that|the|talk about|discuss|mention|said about|told you about)\s+(.{3,60}?)(?:\?|$|\.|\!)',
    re.IGNORECASE,
)


def is_recall_question(text: str) -> bool:
    return bool(_RECALL_PATTERNS.search(text))


def _extract_search_terms(text: str) -> list[str]:
    """Extract meaningful search terms from the recall question."""
    topic_match = _TOPIC_EXTRACT.search(text)
    if topic_match:
        topic = topic_match.group(1).strip()
        words = [w for w in topic.split() if len(w) > 2]
        return words if words else text.split()

    stopwords = {
        "the", "and", "for", "that", "this", "with", "from", "have", "been",
        "what", "when", "where", "how", "did", "does", "you", "we", "our",
        "about", "remember", "recall", "talk", "said", "told", "ever",
        "once", "time", "last", "first", "just", "like", "some", "were",
        "was", "your", "say", "tell", "asked", "mentioned", "discussed",
    }
    words = text.lower().split()
    terms = [w.strip("?.,!\"'") for w in words if w.strip("?.,!\"'") not in stopwords and len(w) > 2]
    return terms


def search_vector_memory(query: str, n: int = 25) -> list[dict]:
    """Semantic search over ChromaDB — broad retrieval."""
    try:
        import vector_memory as vm
        hits = vm.search(query, n=n)
        return [h for h in hits if h.get("distance", 1.0) < 0.75]
    except Exception as e:
        logger.warning(f"[deep_recall] vector search failed: {e}")
        return []


def search_memory_md(terms: list[str], max_results: int = 30) -> list[dict]:
    """Full-text keyword search over memory.md (all 5000 entries)."""
    try:
        import conversation_memory as cm
        from conversation_memory import MEMORY_FILE, _log_lock

        with _log_lock:
            if not MEMORY_FILE.exists():
                return []
            text = MEMORY_FILE.read_text(encoding="utf-8")

        parts = text.split("\n## ")
        results = []

        for part in parts:
            if not part.strip():
                continue
            part_lower = part.lower()
            score = sum(1 for term in terms if term.lower() in part_lower)
            if score > 0:
                lines = part.strip().split("\n")
                header = lines[0] if lines else ""
                ts_match = re.match(r"(\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2})", header)
                ts = ts_match.group(1) if ts_match else ""

                user_msg = ""
                bot_msg = ""
                for line in lines:
                    if line.startswith("**User:** "):
                        user_msg = line[len("**User:** "):].strip()
                    elif line.startswith("**Bot:** "):
                        bot_msg = line[len("**Bot:** "):].strip()

                if user_msg or bot_msg:
                    results.append({
                        "ts": ts,
                        "user_msg": user_msg,
                        "bot_reply": bot_msg,
                        "score": score,
                        "source": "memory_md",
                    })

        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:max_results]
    except Exception as e:
        logger.warning(f"[deep_recall] memory.md search failed: {e}")
        return []


def search_vault(query: str, n: int = 10) -> list[dict]:
    """Full-text search over relationship vault."""
    try:
        import relationship_vault as rv
        results = rv.search(query, limit=n)
        return results
    except Exception as e:
        logger.warning(f"[deep_recall] vault search failed: {e}")
        return []


def search_compressed_chunks(terms: list[str], user_id: int, n: int = 10) -> list[dict]:
    """Search long-context compressed medium-tier chunks."""
    try:
        import long_context_optimizer as lco
        conn = lco._get_db()
        rows = conn.execute(
            "SELECT content, keywords, ts_range_start, ts_range_end "
            "FROM compressed_chunks WHERE tier='medium' AND user_id=? ORDER BY id DESC LIMIT 50",
            (user_id,)
        ).fetchall()
        conn.close()

        results = []
        terms_set = set(t.lower() for t in terms)
        for row in rows:
            chunk_kws = set(row["keywords"].split(","))
            content_lower = row["content"].lower()
            kw_overlap = len(terms_set & chunk_kws)
            text_matches = sum(1 for t in terms_set if t in content_lower)
            score = kw_overlap * 2 + text_matches

            if score > 0:
                results.append({
                    "content": row["content"],
                    "ts_start": row["ts_range_start"],
                    "ts_end": row["ts_range_end"],
                    "score": score,
                    "source": "compressed",
                })

        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:n]
    except Exception as e:
        logger.warning(f"[deep_recall] compressed search failed: {e}")
        return []


def _deduplicate(vector_hits: list[dict], md_hits: list[dict]) -> list[dict]:
    """
    Merge vector and memory.md hits, deduplicating by content overlap.
    Vector hits take priority (they have semantic relevance scores).
    """
    seen_previews = set()
    merged = []

    for hit in vector_hits:
        preview = (hit.get("user_msg", "")[:50] + hit.get("bot_reply", "")[:50]).lower()
        if preview not in seen_previews:
            seen_previews.add(preview)
            merged.append({
                "ts": hit.get("id", ""),
                "user_msg": hit.get("user_msg", ""),
                "bot_reply": hit.get("bot_reply", ""),
                "source": "semantic",
                "relevance": 1.0 - hit.get("distance", 0.5),
            })

    for hit in md_hits:
        preview = (hit.get("user_msg", "")[:50] + hit.get("bot_reply", "")[:50]).lower()
        if preview not in seen_previews:
            seen_previews.add(preview)
            merged.append({
                "ts": hit.get("ts", ""),
                "user_msg": hit.get("user_msg", ""),
                "bot_reply": hit.get("bot_reply", ""),
                "source": "keyword",
                "relevance": hit.get("score", 0) / 5.0,
            })

    merged.sort(key=lambda x: x.get("relevance", 0), reverse=True)
    return merged


def full_recall(query: str, user_id: int, max_exchanges: int = 40) -> str:
    """
    Broad multi-source search. Returns a formatted block for prompt injection.
    This is the main entry point — called from the echo handler when a
    recall question is detected.
    """
    terms = _extract_search_terms(query)
    if not terms:
        terms = [w for w in query.lower().split() if len(w) > 3]

    search_query = " ".join(terms) if terms else query

    vector_hits = search_vector_memory(search_query, n=25)
    md_hits = search_memory_md(terms, max_results=30)
    vault_hits = search_vault(search_query, n=8)
    compressed_hits = search_compressed_chunks(terms, user_id, n=5)

    merged = _deduplicate(vector_hits, md_hits)[:max_exchanges]

    if not merged and not vault_hits and not compressed_hits:
        return ""

    lines = [
        "## Deep Memory Recall",
        f"Searching for: \"{' '.join(terms)}\"",
        f"Found {len(merged)} exchanges, {len(vault_hits)} vault moments, {len(compressed_hits)} compressed summaries.\n",
    ]

    if merged:
        lines.append("### Matching Conversations (most relevant first)")
        for i, hit in enumerate(merged, 1):
            ts = hit.get("ts", "?")
            src = hit.get("source", "?")
            lines.append(f"[{i}] ({ts}) [{src}]")
            if hit.get("user_msg"):
                lines.append(f"  master: {hit['user_msg'][:400]}")
            if hit.get("bot_reply"):
                lines.append(f"  you: {hit['bot_reply'][:400]}")
            lines.append("")

    if vault_hits:
        lines.append("### Vault Memories (curated moments)")
        for v in vault_hits:
            ts = v.get("ts", "")[:10]
            cat = v.get("category", "moment")
            title = v.get("title", "")
            content = v.get("content", "")
            tone = v.get("emotional_tone", "")
            lines.append(f"- [{ts}] [{cat}] {title}: {content[:200]} ({tone})")
        lines.append("")

    if compressed_hits:
        lines.append("### Compressed History (older conversations)")
        for c in compressed_hits:
            lines.append(f"- [{c.get('ts_start', '?')} → {c.get('ts_end', '?')}] {c['content'][:300]}")
        lines.append("")

    lines.append(
        "Use these memories to answer master's question. Reference specific dates, quotes, "
        "and details from the exchanges above. You have real memories — use them. "
        "If something isn't in the results, say you don't remember rather than guessing."
    )

    result = "\n".join(lines)
    logger.info(f"[deep_recall] returned {len(merged)} exchanges + {len(vault_hits)} vault + {len(compressed_hits)} compressed for query: {search_query[:60]}")
    return result


def get_expanded_history(user_id: int, n: int = 50) -> list:
    """
    Get a larger history window for recall turns.
    Returns chat messages in [{role, content}] format.
    """
    try:
        import conversation_memory as cm
        return cm.get_user_history(user_id, n=n)
    except Exception:
        return []
