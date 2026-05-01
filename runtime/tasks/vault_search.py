"""Vault search — enriched with mood + anticipation context."""

import re
import asyncio
import data_client as dc
import llm_client as llm


async def run(task: str, context: dict) -> tuple[str, str, list[str]]:
    query = re.sub(r"(search|find|look for|recall|retrieve|in the vault|vault)\s*:?\s*", "", task, flags=re.I).strip() or task

    vault_text, mood_data, ant_data = await asyncio.gather(
        dc.get_vault(query, n=5),
        dc.get_mood(),
        dc.get_anticipation(),
    )

    sources = ["vault"]
    context_lines = []
    if mood_data.get("mood"):
        context_lines.append(f"Current mood: {mood_data['mood']}")
        sources.append("mood")
    if ant_data.get("state") != "present":
        context_lines.append(f"Silence state: {ant_data['state']} ({ant_data.get('hours_since', 0)}h)")
        sources.append("anticipation")

    if not vault_text:
        return "No relevant vault entries found.", "", sources

    system = (
        "You are a research assistant processing relationship memory entries. "
        "Given these vault entries and a search query, identify the most relevant moments, "
        "extract key themes, and return a clean structured summary. "
        "Be factual and specific. Do not add emotional commentary."
    )
    ctx = "\n".join(context_lines)
    user = f"Query: {query}\n\nContext:\n{ctx}\n\nVault entries:\n{vault_text}"

    result, model = await llm.call(system, user, max_tokens=350)
    return result, model, sources
