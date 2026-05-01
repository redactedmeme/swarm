"""Daily digest — structured summary of the day's interactions."""

import asyncio
import data_client as dc
import llm_client as llm


async def run(task: str = "", context: dict = None) -> tuple[str, str, list[str]]:
    history, heatmap, facts = await asyncio.gather(
        dc.get_history("", n=50),
        dc.get_heatmap(n=30),
        dc.get_facts(limit=20),
    )

    sources = []
    parts = []

    if history:
        sources.append("history")
        msgs = [f"[{m.get('role', '?')}] {m.get('content', '')[:150]}" for m in history[-30:]]
        parts.append("Recent exchanges:\n" + "\n".join(msgs))

    if heatmap:
        sources.append("heatmap")
        moods = [f"{f.get('ts', '?')[:16]} — {f.get('mood', '?')} v={f.get('valence', 0):.1f}" for f in heatmap[-10:]]
        parts.append("Emotional frames:\n" + "\n".join(moods))

    if facts:
        sources.append("facts")
        recent_facts = [f.get("fact", "") for f in facts[:10]]
        parts.append("Recently learned:\n" + "\n".join(f"- {f}" for f in recent_facts))

    if not parts:
        return "No data available for daily digest.", "", sources

    system = (
        "You are creating a daily digest for an AI companion's operator. "
        "Summarize the day's interactions into:\n"
        "1. conversation_highlights — key topics discussed (3-5 bullets)\n"
        "2. mood_trajectory — how emotional state shifted through the day\n"
        "3. new_facts — concrete things learned about the user today\n"
        "4. relationship_notes — anything notable about the connection\n"
        "5. tomorrow_context — what to keep in mind for the next conversation\n"
        "Be concise and specific."
    )
    user = "Build a daily digest from:\n\n" + "\n\n".join(parts)

    result, model = await llm.call(system, user, max_tokens=500, prefer_strong=True)
    return result, model, sources


async def execute() -> str:
    result, _, _ = await run()
    return result
