"""General research — factual reasoning anchored with known facts."""

import data_client as dc
import llm_client as llm


async def run(task: str, context: dict) -> tuple[str, str, list[str]]:
    # Seed with top resonance facts for anchoring
    facts = await dc.get_facts(limit=15)
    sources = []
    facts_context = ""
    if facts:
        sources.append("facts")
        facts_context = "Known facts about the user:\n" + "\n".join(
            f"- {f.get('fact', '')}" for f in facts[:10] if f.get("fact")
        )

    system = (
        "You are a research assistant. Answer the following factual question or complete "
        "the research task as concisely and specifically as possible. "
        "Use the provided user context to anchor your answer where relevant. "
        "Return structured output where appropriate (bullets, numbers, key facts). "
        "Do not add emotional commentary or personal opinion."
    )
    user = f"{facts_context}\n\nTask: {task}" if facts_context else f"Task: {task}"

    result, model = await llm.call(system, user, max_tokens=400)
    return result, model, sources
