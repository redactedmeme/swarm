"""Pattern detection — recurring themes across vault and facts."""

import asyncio
import data_client as dc
import llm_client as llm


async def run(task: str, context: dict) -> tuple[str, str, list[str]]:
    vault_entries, facts, heatmap = await asyncio.gather(
        dc.get_vault_entries(n=20),
        dc.get_facts(limit=50),
        dc.get_heatmap(n=30),
    )

    sources = []
    context_parts = []

    if vault_entries:
        sources.append("vault")
        vault_text = "\n".join(
            f"[{e.get('ts', '?')[:10]}] ({e.get('category', '?')}) {e.get('title', '')}: {e.get('content', '')[:150]}"
            for e in vault_entries
        )
        context_parts.append(f"Vault entries ({len(vault_entries)}):\n{vault_text}")

    if facts:
        sources.append("facts")
        facts_text = "\n".join(f"- [{f.get('ts', '?')[:10]}] {f.get('fact', '')}" for f in facts[:30])
        context_parts.append(f"Known facts ({len(facts)}):\n{facts_text}")

    if heatmap:
        sources.append("heatmap")
        moods = [f.get("mood", "") for f in heatmap if f.get("mood")]
        context_parts.append(f"Recent moods: {', '.join(moods[-15:])}")

    if not context_parts:
        return "Insufficient data for pattern detection.", "", sources

    system = (
        "You are a pattern analyst. Given vault memories, known facts, and emotional "
        "heatmap data, identify:\n"
        "1. recurring_topics — subjects that appear across multiple entries\n"
        "2. behavioral_cycles — patterns in mood, engagement, or communication style\n"
        "3. growth_trajectories — areas of development or deepening\n"
        "4. unresolved_threads — topics raised but not followed up on\n"
        "Be specific, cite entries where possible. No emotional commentary."
    )
    user = f"Task: {task}\n\nData:\n" + "\n\n".join(context_parts)

    result, model = await llm.call(system, user, max_tokens=500, prefer_strong=True)
    return result, model, sources
