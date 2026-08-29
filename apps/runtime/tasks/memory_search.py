"""Memory search — hybrid semantic (vector) + keyword search."""

import re
import asyncio
import data_client as dc
import llm_client as llm


async def run(task: str, context: dict) -> tuple[str, str, list[str]]:
    query = re.sub(
        r"\b(search|find|look for|recall|remember|in the|memory|memories|conversation|log|history|when did|what did)\b",
        "", task, flags=re.I
    ).strip(" :?") or task

    vector_results, keyword_results = await asyncio.gather(
        dc.get_vector(query, n=5),
        dc.get_memory(query, n=6),
    )

    sources = []
    excerpt_parts = []

    if vector_results:
        sources.append("vector")
        for hit in vector_results[:5]:
            excerpt_parts.append(f"[semantic match, dist={hit.get('distance', '?')}]\n"
                                 f"user: {hit.get('user_msg', '')[:200]}\n"
                                 f"chan: {hit.get('bot_reply', '')[:200]}")

    if keyword_results:
        sources.append("memory")
        for block in keyword_results[:4]:
            excerpt_parts.append(f"[keyword match]\n{block[:400]}")

    if not excerpt_parts:
        return f"No conversation history found mentioning: {query}", "", sources or ["memory"]

    excerpt = "\n---\n".join(excerpt_parts)

    system = (
        "You are a research assistant reviewing conversation history. "
        "Given these excerpts (from both semantic and keyword search), extract the key facts "
        "relevant to the search query. Be specific and concrete. "
        "State what was said, when if visible, and any important context. "
        "Do not add emotional commentary."
    )
    user = f"Query: {query}\n\nConversation excerpts:\n{excerpt}"

    result, model = await llm.call(system, user, max_tokens=400)
    return result, model, sources
