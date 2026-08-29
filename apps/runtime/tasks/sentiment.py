"""Basic sentiment analysis on recent messages."""

import data_client as dc
import llm_client as llm


async def run(task: str, context: dict) -> tuple[str, str, list[str]]:
    user_id = context.get("user_id", "")
    history = await dc.get_history(user_id, n=30) if user_id else []

    if not history:
        return "No conversation history available for analysis.", "", ["history"]

    master_msgs = [m["content"] for m in history if m.get("role") == "user"]
    if not master_msgs:
        return "No user messages found in recent history.", "", ["history"]

    history_text = "\n".join(f"- {m[:200]}" for m in master_msgs[-20:])

    system = (
        "You are a data analyst. Analyze these recent messages from one person "
        "for mood trends, stress indicators, recurring themes, and patterns. "
        "Return a structured analysis with: overall_sentiment, stress_level (low/medium/high), "
        "key_themes (list), notable_patterns, and a one-sentence summary. "
        "Be clinical and specific. No emotional commentary."
    )
    user = f"Task: {task}\n\nRecent messages:\n{history_text}"

    result, model = await llm.call(system, user, max_tokens=400)
    return result, model, ["history"]
