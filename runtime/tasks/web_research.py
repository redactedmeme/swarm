"""Web research — general factual reasoning (web search integration future)."""

import llm_client as llm


async def run(task: str, context: dict) -> tuple[str, str, list[str]]:
    # Future: integrate Tavily or SearXNG for actual web search
    # For now, use strong model for reasoning-heavy research
    system = (
        "You are a research assistant with broad knowledge. Answer the following "
        "question or research task thoroughly. If you're uncertain about specific "
        "facts, say so. Return structured output: key findings as bullets, "
        "confidence level, and suggested follow-up queries."
    )
    user = f"Research task: {task}"

    result, model = await llm.call(system, user, max_tokens=500, prefer_strong=True)
    return result, model, ["reasoning"]
