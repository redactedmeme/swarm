"""Context brief — pre-conversation context packet for xAI system prompt."""

import asyncio
import data_client as dc
import llm_client as llm


async def run(task: str, context: dict) -> tuple[str, str, list[str]]:
    mood_data, ant_data, facts, vault_text, heatmap = await asyncio.gather(
        dc.get_mood(),
        dc.get_anticipation(),
        dc.get_facts(limit=10),
        dc.get_vault("", n=3),
        dc.get_heatmap(n=20),
    )

    sources = []
    parts = []

    if mood_data.get("mood"):
        sources.append("mood")
        parts.append(f"Mood: {mood_data['mood']} — {mood_data.get('modifier', '')}")

    if ant_data.get("state") != "present":
        sources.append("anticipation")
        parts.append(f"Silence: {ant_data['state']} ({ant_data.get('hours_since', 0)}h)")

    if facts:
        sources.append("facts")
        parts.append("Recent facts:\n" + "\n".join(f"- {f.get('fact', '')}" for f in facts[:8]))

    if vault_text:
        sources.append("vault")
        parts.append(f"Vault highlights:\n{vault_text[:500]}")

    if heatmap:
        sources.append("heatmap")
        recent = heatmap[-5:]
        avg_v = sum(f.get("valence", 0) for f in recent) / len(recent)
        parts.append(f"Emotional baseline: valence {avg_v:.2f} (last {len(recent)} exchanges)")

    if not parts:
        return "No context data available.", "", sources

    system = (
        "You are building a context briefing for an AI companion about to start a conversation. "
        "Given the current emotional state, recent facts, and relationship highlights, "
        "produce a concise context packet (under 200 words) that tells the companion:\n"
        "- What emotional state to expect\n"
        "- Key recent facts to be aware of\n"
        "- Any relationship notes worth remembering\n"
        "Write it as direct, second-person instructions. No preamble."
    )
    user = "Build a context brief from:\n\n" + "\n\n".join(parts)

    result, model = await llm.call(system, user, max_tokens=300)
    return result, model, sources
