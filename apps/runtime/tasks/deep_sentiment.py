"""Deep sentiment — full emotional analysis using heatmap + mood + anticipation."""

import asyncio
import data_client as dc
import llm_client as llm


async def run(task: str, context: dict) -> tuple[str, str, list[str]]:
    user_id = context.get("user_id", "")

    coros = [dc.get_heatmap(n=50), dc.get_mood(), dc.get_anticipation()]
    if user_id:
        coros.append(dc.get_history(user_id, n=30))
    results = await asyncio.gather(*coros)
    heatmap, mood_data, ant_data = results[0], results[1], results[2]
    history = results[3] if user_id else []

    sources = []
    context_parts = []

    if heatmap:
        sources.append("heatmap")
        recent = heatmap[-10:]
        avg_valence = sum(f.get("valence", 0) for f in recent) / len(recent) if recent else 0
        avg_arousal = sum(f.get("arousal", 0) for f in recent) / len(recent) if recent else 0
        context_parts.append(
            f"Heatmap ({len(heatmap)} frames total):\n"
            f"  Recent avg valence: {avg_valence:.2f}, arousal: {avg_arousal:.2f}\n"
            f"  Last 5 moods: {', '.join(f.get('mood', '?') for f in heatmap[-5:])}"
        )

    if mood_data.get("mood"):
        sources.append("mood")
        context_parts.append(f"Current mood baseline: {mood_data['mood']} — {mood_data.get('modifier', '')}")

    if ant_data.get("state"):
        sources.append("anticipation")
        context_parts.append(f"Silence state: {ant_data['state']} ({ant_data.get('hours_since', 0)}h since last message)")

    if history:
        sources.append("history")
        master_msgs = [m["content"][:150] for m in history if m.get("role") == "user"][-15:]
        context_parts.append("Recent messages:\n" + "\n".join(f"- {m}" for m in master_msgs))

    if not context_parts:
        return "Insufficient data for deep sentiment analysis.", "", sources

    system = (
        "You are an emotional intelligence analyst. Perform a multi-dimensional "
        "sentiment analysis using the provided data sources. Return:\n"
        "1. overall_sentiment (positive/neutral/negative + intensity 0-10)\n"
        "2. stress_level (low/medium/high) with evidence\n"
        "3. emotional_trajectory (improving/stable/declining over recent frames)\n"
        "4. baseline_comparison (how current state compares to average)\n"
        "5. key_themes (recurring emotional patterns)\n"
        "6. actionable_insight (one sentence — what to be aware of)\n"
        "Be clinical and evidence-based. Reference specific data points."
    )
    user = f"Task: {task}\n\nData sources:\n" + "\n\n".join(context_parts)

    result, model = await llm.call(system, user, max_tokens=500, prefer_strong=True)
    return result, model, sources
