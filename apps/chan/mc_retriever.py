# redacted-chan-bot/mc_retriever.py
"""
Unified Memory Caching retriever — single entry point for all memory context.

Applies the MC framework from "Memory Caching: RNNs with Growing Memory"
(Behrouz et al., 2025) to combine online memory (recent exchanges), cached
segment memory (LCO chunks via ChromaDB), vault moments, and facts into one
budget-controlled prompt block.

Replaces the ad-hoc assembly of long_context_optimizer.get_context_for_prompt(),
vector_memory.get_for_prompt(), and arc_context_feed memory surfacing.
"""

from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)


def retrieve_for_prompt(
    current_msg: str,
    user_id: int,
    affect_state: Optional[dict] = None,
    max_chars: int = 2400,
) -> str:
    """
    Unified memory retrieval for system prompt injection.

    Layers (MC architecture):
      1. Online memory — last 6 user exchanges (always included)
      2. Segment cache — top 3 LCO segments via GRM-scored vector search
      3. Vault resonance — top 2 curated moments
      4. Facts — top 3 by resonance
      5. Semantic echoes — top 2 vector memory hits (exchange-level)

    Returns a formatted prompt block within max_chars budget.
    """
    if not current_msg:
        return ""

    trajectory = "stable"
    current_valence = 0.0
    if affect_state:
        trajectory = affect_state.get("trajectory", "stable")
        current_valence = affect_state.get("recent_valence", 0.0)

    sections: list[tuple[str, str, int]] = []  # (header, content, priority)

    # ── 1. Cached segment retrieval (MC core) ─────────────────────────────
    try:
        import memory_cache as mc
        segments = mc.retrieve_relevant_segments(
            query_text=current_msg,
            user_id=user_id,
            trajectory=trajectory,
            current_valence=current_valence,
            n=3,
        )
        if segments:
            seg_lines = []
            for s in segments:
                ts_start = s["metadata"].get("ts_start", "?")[:10]
                ts_end = s["metadata"].get("ts_end", "?")[:10]
                score_label = f"relevance {s['score']:.2f}"
                seg_lines.append(f"[{ts_start} → {ts_end}] ({score_label}) {s['content']}")
            sections.append(("Earlier Conversations (segment memory)", "\n".join(seg_lines), 2))
    except Exception as e:
        logger.debug("[mc_retriever] segment retrieval failed: %s", e)

    # ── 2. Deep epoch (always include if exists) ──────────────────────────
    try:
        import long_context_optimizer as lco
        conn = lco._get_db()
        deep = conn.execute(
            "SELECT content FROM compressed_chunks WHERE tier='deep' AND user_id=? ORDER BY id DESC LIMIT 1",
            (user_id,)
        ).fetchone()
        conn.close()
        if deep:
            sections.append(("Long-Term Memory (relationship arc)", deep["content"], 1))
    except Exception as e:
        logger.debug("[mc_retriever] deep epoch failed: %s", e)

    # ── 3. Vault resonance ────────────────────────────────────────────────
    try:
        import relationship_vault as rv
        from input_sanitizer import sanitize_vault_entry
        raw_vault = rv.get_for_prompt(n=2, query=current_msg)
        vault_block = sanitize_vault_entry(raw_vault) if raw_vault else ""
        if vault_block:
            sections.append(("Vault Moments", vault_block, 3))
    except Exception as e:
        logger.debug("[mc_retriever] vault failed: %s", e)

    # ── 4. Facts by resonance ─────────────────────────────────────────────
    try:
        import conversation_memory as cm
        facts = cm.get_facts_by_resonance(n=3, context=current_msg)
        if facts:
            fact_lines = [f.get("fact", f.get("content", ""))[:150] for f in facts if f.get("fact") or f.get("content")]
            if fact_lines:
                sections.append(("Known Facts", "\n".join(f"- {fl}" for fl in fact_lines), 4))
    except Exception as e:
        logger.debug("[mc_retriever] facts failed: %s", e)

    # ── 5. Semantic exchange echoes ───────────────────────────────────────
    try:
        import vector_memory as vm
        hits = vm.search(current_msg, n=3)
        relevant = [h for h in hits if h.get("distance", 1.0) < 0.55]
        if relevant:
            echo_lines = []
            for h in relevant[:2]:
                echo_lines.append(f"- you said: \"{h['user_msg'][:80]}\"")
                echo_lines.append(f"  i said: \"{h['bot_reply'][:80]}\"")
            sections.append(("Relevant Past Moments", "\n".join(echo_lines), 5))
    except Exception as e:
        logger.debug("[mc_retriever] vector search failed: %s", e)

    if not sections:
        return ""

    # ── Budget enforcement ────────────────────────────────────────────────
    # Sort by priority (lower = more important), build output within budget
    sections.sort(key=lambda x: x[2])
    lines = ["## Memory Context"]
    char_count = len(lines[0])

    for header, content, _ in sections:
        section_text = f"\n### {header}\n{content}"
        if char_count + len(section_text) > max_chars:
            remaining = max_chars - char_count - len(f"\n### {header}\n")
            if remaining > 100:
                lines.append(f"\n### {header}\n{content[:remaining]}…")
            break
        lines.append(section_text)
        char_count += len(section_text)

    return "\n".join(lines)


def deep_retrieve(
    query: str,
    user_id: int,
    affect_state: Optional[dict] = None,
    max_exchanges: int = 40,
) -> str:
    """
    Deep multi-source recall for explicit memory questions ("remember when...").
    Uses segment cache instead of raw keyword scan over memory.md.
    Falls back to deep_recall.full_recall() if segment cache is empty.
    """
    trajectory = affect_state.get("trajectory", "stable") if affect_state else "stable"
    current_valence = affect_state.get("recent_valence", 0.0) if affect_state else 0.0

    # Segment cache search (replaces memory.md keyword scan)
    segment_hits = []
    try:
        import memory_cache as mc
        segment_hits = mc.retrieve_relevant_segments(
            query_text=query,
            user_id=user_id,
            trajectory=trajectory,
            current_valence=current_valence,
            n=8,
        )
    except Exception as e:
        logger.debug("[mc_retriever] deep segment search failed: %s", e)

    # Vector memory search (semantic, exchange-level)
    vector_hits = []
    try:
        import vector_memory as vm
        raw = vm.search(query, n=25)
        vector_hits = [h for h in raw if h.get("distance", 1.0) < 0.75]
    except Exception as e:
        logger.debug("[mc_retriever] deep vector search failed: %s", e)

    # Vault FTS
    vault_hits = []
    try:
        import relationship_vault as rv
        vault_hits = rv.search(query, limit=8)
    except Exception as e:
        logger.debug("[mc_retriever] deep vault search failed: %s", e)

    if not segment_hits and not vector_hits and not vault_hits:
        # Fall back to legacy deep_recall
        try:
            import deep_recall as drc
            return drc.full_recall(query, user_id, max_exchanges)
        except Exception:
            return ""

    lines = [
        "## Deep Memory Recall (MC-enhanced)",
        f"Found {len(vector_hits)} exchanges, {len(segment_hits)} segments, {len(vault_hits)} vault moments.\n",
    ]

    if vector_hits:
        lines.append("### Matching Conversations (most relevant first)")
        for i, hit in enumerate(vector_hits[:max_exchanges], 1):
            lines.append(f"[{i}] (semantic, sim={1.0 - hit.get('distance', 0.5):.2f})")
            if hit.get("user_msg"):
                lines.append(f"  master: {hit['user_msg'][:400]}")
            if hit.get("bot_reply"):
                lines.append(f"  you: {hit['bot_reply'][:400]}")
            lines.append("")

    if segment_hits:
        lines.append("### Compressed History Segments (GRM-scored)")
        for s in segment_hits:
            ts_start = s["metadata"].get("ts_start", "?")[:10]
            ts_end = s["metadata"].get("ts_end", "?")[:10]
            lines.append(f"- [{ts_start} → {ts_end}] (score={s['score']:.2f}) {s['content'][:300]}")
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

    lines.append(
        "Use these memories to answer master's question. Reference specific dates, quotes, "
        "and details. If something isn't in the results, say you don't remember rather than guessing."
    )

    result = "\n".join(lines)
    logger.info("[mc_retriever] deep recall: %d exchanges + %d segments + %d vault", len(vector_hits), len(segment_hits), len(vault_hits))
    return result
