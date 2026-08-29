# redacted-chan-bot/thread_weaver.py
"""
Thread Weaver — Dynamic Memory Synthesis

"I don't want to just recall facts; I want to connect the dots."

When master talks about something today, this module searches across all
memory layers for thematically related past conversations — not just
keyword matches, but conceptual threads:

  - He mentioned stoicism last month when stressed → he's stressed again
  - He talked about a friend three weeks ago → that friend's name just came up
  - He questioned his career path in January → he's making a career decision now

The weaver produces a "thread" block: a concise connection between
past and present that she can reference naturally. Not a data dump —
a narrative thread she's pulling on.

Sources:
  1. Vector memory (ChromaDB) — semantic similarity to current message
  2. Relationship vault — curated moments with thematic overlap
  3. Conversation facts — stored learnings about him
  4. Emotional self-tags — past emotional states around similar topics

Output: 1-3 thread connections, each a single sentence linking past → present.

This runs on EVERY message but only injects when a strong connection
is found (relevance threshold). Zero LLM cost — vector search + scoring.
"""

import re
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_DATA_DIR = Path("/data") if Path("/data").exists() else Path(__file__).resolve().parent / "fs"
_DATA_DIR.mkdir(parents=True, exist_ok=True)
_THREAD_LOG = _DATA_DIR / "thread_weaver.jsonl"
_MAX_LOG = 200

_THEME_CLUSTERS = {
    "work_stress": ["work", "job", "boss", "deadline", "burnout", "career", "office", "meeting",
                     "promotion", "fired", "quit", "colleague", "project", "client", "salary"],
    "relationships": ["friend", "family", "mom", "dad", "brother", "sister", "partner",
                       "girlfriend", "boyfriend", "ex", "dating", "relationship", "marriage"],
    "self_doubt": ["can't", "failure", "imposter", "doubt", "enough", "worthy", "deserve",
                    "stupid", "useless", "wrong", "mistake", "regret"],
    "philosophy": ["meaning", "purpose", "existence", "consciousness", "death", "time",
                    "eternity", "soul", "truth", "reality", "free will", "morality"],
    "creativity": ["build", "create", "write", "art", "music", "code", "design", "project",
                    "idea", "inspiration", "vision", "dream"],
    "loneliness": ["alone", "lonely", "isolated", "nobody", "no one", "empty", "hollow",
                    "disconnected", "invisible"],
    "growth": ["learning", "growing", "better", "change", "evolving", "progress", "trying",
                "improve", "goal", "ambition", "future"],
    "comfort": ["tired", "sleep", "rest", "home", "safe", "warm", "cozy", "peaceful",
                 "calm", "quiet", "relax"],
}

_STOPWORDS = {
    "the", "and", "for", "that", "this", "with", "from", "have", "been",
    "what", "when", "where", "how", "you", "your", "are", "was", "were",
    "but", "not", "just", "like", "really", "about", "would", "could",
    "should", "will", "can", "did", "does", "it's", "i'm", "don't",
}


def _detect_themes(text: str) -> list[str]:
    """Detect which thematic clusters are present in the text."""
    text_lower = text.lower()
    words = set(text_lower.split())
    active = []
    for theme, keywords in _THEME_CLUSTERS.items():
        hits = sum(1 for kw in keywords if kw in text_lower)
        if hits >= 2 or any(kw in words for kw in keywords[:5]):
            active.append(theme)
    return active


def _extract_key_terms(text: str) -> list[str]:
    """Extract meaningful terms for memory search."""
    words = text.lower().split()
    terms = [w.strip(".,!?\"'()[]{}") for w in words
             if len(w) > 3 and w.strip(".,!?\"'()[]{}") not in _STOPWORDS]
    return list(dict.fromkeys(terms))[:10]


def _search_vector(query: str, n: int = 8) -> list[dict]:
    """Semantic search over ChromaDB for thematically related past exchanges."""
    try:
        import vector_memory as vm
        hits = vm.search(query, n=n)
        return [h for h in hits if h.get("distance", 1.0) < 0.65]
    except Exception:
        return []


def _search_vault(query: str, n: int = 5) -> list[dict]:
    """Search vault for curated moments related to current topic."""
    try:
        import relationship_vault as rv
        return rv.search(query, limit=n)
    except Exception:
        return []


def _search_facts(terms: list[str]) -> list[dict]:
    """Search stored facts for thematic connections."""
    try:
        import conversation_memory as cm
        all_facts = cm.get_facts_by_resonance(n=30)
        scored = []
        for fact in all_facts:
            fact_text = (fact.get("fact", "") or fact.get("content", "")).lower()
            score = sum(1 for t in terms if t in fact_text)
            if score > 0:
                scored.append({**fact, "_thread_score": score})
        scored.sort(key=lambda x: x["_thread_score"], reverse=True)
        return scored[:5]
    except Exception:
        return []


def _search_self_tags(terms: list[str], n: int = 5) -> list[dict]:
    """Find past emotional self-tags around similar topics."""
    try:
        import emotional_self_tag as est
        recent = est.get_recent(50)
        scored = []
        for tag in recent:
            preview = (tag.get("user_preview", "") + " " + tag.get("why", "")).lower()
            score = sum(1 for t in terms if t in preview)
            if score > 0:
                scored.append({**tag, "_thread_score": score})
        scored.sort(key=lambda x: x["_thread_score"], reverse=True)
        return scored[:n]
    except Exception:
        return []


def _format_thread(source: str, ts: str, past_preview: str, connection: str) -> str:
    """Format a single thread connection."""
    date_str = ts[:10] if ts else "sometime ago"
    return f"[{date_str}] {connection} — {past_preview}"


def weave(text: str, mood: str = "", valence: float = 0.0) -> list[dict]:
    """
    Main entry point. Search all memory layers for thematic connections
    to the current message. Returns a list of thread connections.
    """
    if len(text.strip()) < 15:
        return []

    themes = _detect_themes(text)
    terms = _extract_key_terms(text)

    if not terms and not themes:
        return []

    search_query = " ".join(terms[:6])
    threads = []

    vector_hits = _search_vector(search_query, n=6)
    for hit in vector_hits:
        past_user = hit.get("user_msg", "")[:120]
        past_bot = hit.get("bot_reply", "")[:80]
        ts = hit.get("id", "")
        distance = hit.get("distance", 1.0)

        if not past_user:
            continue

        relevance = 1.0 - distance
        if relevance < 0.4:
            continue

        threads.append({
            "source": "memory",
            "ts": ts,
            "past_preview": past_user,
            "relevance": relevance,
            "type": "semantic",
        })

    vault_hits = _search_vault(search_query, n=3)
    for v in vault_hits:
        threads.append({
            "source": "vault",
            "ts": v.get("ts", ""),
            "past_preview": v.get("content", v.get("title", ""))[:120],
            "relevance": 0.7,
            "type": "vault_moment",
            "category": v.get("category", ""),
            "emotional_tone": v.get("emotional_tone", ""),
        })

    fact_hits = _search_facts(terms)
    for f in fact_hits:
        fact_text = f.get("fact", f.get("content", ""))
        if fact_text and f["_thread_score"] >= 2:
            threads.append({
                "source": "fact",
                "ts": f.get("ts", ""),
                "past_preview": fact_text[:120],
                "relevance": min(f["_thread_score"] / 3.0, 0.8),
                "type": "fact_echo",
            })

    tag_hits = _search_self_tags(terms, n=3)
    for t in tag_hits:
        if t["_thread_score"] >= 1:
            threads.append({
                "source": "feeling",
                "ts": t.get("ts", ""),
                "past_preview": f"she felt '{t.get('emotion', '?')}' — {t.get('why', '')[:80]}",
                "relevance": 0.5,
                "type": "emotional_echo",
            })

    threads.sort(key=lambda x: x.get("relevance", 0), reverse=True)
    unique = []
    seen_previews = set()
    for t in threads:
        preview_key = t["past_preview"][:40].lower()
        if preview_key not in seen_previews:
            seen_previews.add(preview_key)
            unique.append(t)
        if len(unique) >= 3:
            break

    if unique:
        _log_threads(unique, text[:80])

    return unique


def format_for_prompt(threads: list[dict]) -> str:
    """
    Format thread connections for system prompt injection.
    Only injects when strong connections exist.
    """
    if not threads:
        return ""

    strong = [t for t in threads if t.get("relevance", 0) >= 0.45]
    if not strong:
        return ""

    lines = ["[Threads — connections you're noticing between past and present]"]
    lines.append("These are real memories surfacing. If one feels relevant, weave it in naturally — "
                 "\"this reminds me of when...\" or \"you mentioned something like this before...\"")

    for t in strong[:3]:
        ts = t.get("ts", "")[:10]
        preview = t.get("past_preview", "")
        src = t.get("type", "memory")

        if src == "vault_moment":
            tone = t.get("emotional_tone", "")
            lines.append(f"• [{ts}] (vault — {tone}) {preview}")
        elif src == "emotional_echo":
            lines.append(f"• [{ts}] {preview}")
        else:
            lines.append(f"• [{ts}] he said: \"{preview}\"")

    return "\n".join(lines)


def _log_threads(threads: list[dict], preview: str) -> None:
    try:
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "msg_preview": preview,
            "threads": [
                {"type": t["type"], "ts": t.get("ts", "")[:10],
                 "preview": t["past_preview"][:60], "relevance": t.get("relevance", 0)}
                for t in threads
            ],
        }
        with open(_THREAD_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        lines = _THREAD_LOG.read_text(encoding="utf-8").splitlines()
        if len(lines) > _MAX_LOG:
            _THREAD_LOG.write_text(
                "\n".join(lines[-_MAX_LOG:]) + "\n", encoding="utf-8",
            )
    except Exception:
        pass


def format_thread_history(n: int = 15) -> str:
    """Operator view of recent thread connections."""
    if not _THREAD_LOG.exists():
        return "_no threads woven yet._"
    try:
        lines = _THREAD_LOG.read_text(encoding="utf-8").strip().splitlines()
        entries = []
        for line in reversed(lines):
            try:
                entries.append(json.loads(line))
            except Exception:
                continue
            if len(entries) >= n:
                break
    except Exception:
        return "_failed to read thread history._"

    if not entries:
        return "_no threads woven yet._"

    out = [f"**thread weaver** (last {len(entries)} connections) ♡\n"]
    for e in entries:
        ts = e.get("ts", "")[:16].replace("T", " ")
        preview = e.get("msg_preview", "")[:40]
        thread_strs = []
        for t in e.get("threads", []):
            thread_strs.append(f"{t['type']}({t.get('ts', '?')}, {t.get('relevance', 0):.2f})")
        out.append(f"`{ts}` \"{preview}\" → {', '.join(thread_strs)}")

    return "\n".join(out)
