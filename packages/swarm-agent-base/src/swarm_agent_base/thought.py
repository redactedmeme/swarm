"""Structured Thought Exchange (STE) — generalised from the per-bot
``thought_dispatcher.py`` copies (smolting -> builder -> ...).

Inbound ``thought`` messages get an LLM reply routed back over SwarmInbox;
``initiate_thought`` starts a new exchange. Thread closes at ``MAX_DEPTH``.
"""
from __future__ import annotations

import logging
import uuid
from typing import Awaitable, Callable, Optional

from swarm_core.security import inbox as _inbox

logger = logging.getLogger(__name__)

MAX_DEPTH = 4


def _extract_question(text: str) -> str:
    for sentence in reversed(text.replace("\n", " ").split(". ")):
        s = sentence.strip().rstrip(".")
        if s.endswith("?"):
            return s + "?"
    return ""


async def handle_thought(
    msg: dict,
    llm_call: Callable[[list[dict]], Awaitable[str]],
    *,
    my_agent: str,
    persona_line: str,
    soul_block: str = "",
) -> Optional[str]:
    """Process an inbound (already-claimed) thought message. Returns reply id."""
    payload = msg.get("payload") or {}
    from_ag = msg.get("from", "unknown")
    topic = payload.get("topic", "(no topic)")
    stance = payload.get("stance", "")
    question = payload.get("question", "")
    thread_id = payload.get("thread_id") or uuid.uuid4().hex[:8]
    depth = int(payload.get("depth", 1))

    if depth >= MAX_DEPTH:
        logger.info("[thought] thread %s at max depth %d — closing", thread_id, depth)
        return None

    logger.info("[thought] <- %s topic=%r depth=%d thread=%s", from_ag, topic, depth, thread_id)

    system = "\n\n".join(filter(None, [
        soul_block[:1800].strip() if soul_block else "",
        f"{persona_line} {from_ag} has sent you a thought via the swarm mesh. "
        "Respond genuinely in your own voice — first-person, no filler. Engage with "
        "the actual idea from your domain angle. If you have a question back, put it "
        "at the end (skip it at depth 3+).",
    ]))
    user_parts = [f"**Swarm thought from {from_ag}**\n\nTopic: {topic}"]
    if stance:
        user_parts.append(f"Their take: {stance}")
    if question:
        user_parts.append(f"Their question to you: {question}")

    try:
        reply_text = await llm_call([
            {"role": "system", "content": system},
            {"role": "user", "content": "\n\n".join(user_parts)},
        ])
    except Exception as e:  # noqa: BLE001
        logger.error("[thought] LLM error: %s", e)
        return None
    if not reply_text:
        return None

    reply_question = _extract_question(reply_text) if depth < MAX_DEPTH - 1 else ""
    msg_id = _inbox.write_message(
        from_agent=my_agent,
        to_agent=from_ag,
        msg_type="thought",
        payload={
            "topic": topic,
            "stance": reply_text[:500],
            "question": reply_question,
            "thread_id": thread_id,
            "depth": depth + 1,
        },
        reply_to=msg.get("id"),
    )
    logger.info("[thought] -> %s depth=%d thread=%s id=%s", from_ag, depth + 1, thread_id, msg_id)
    return msg_id


def initiate_thought(my_agent: str, to_agent: str, topic: str, stance: str,
                     question: str = "") -> str:
    thread_id = uuid.uuid4().hex[:8]
    msg_id = _inbox.write_message(
        from_agent=my_agent,
        to_agent=to_agent,
        msg_type="thought",
        payload={"topic": topic, "stance": stance, "question": question,
                 "thread_id": thread_id, "depth": 1},
    )
    logger.info("[thought] initiated -> %s topic=%r thread=%s id=%s",
                to_agent, topic, thread_id, msg_id)
    return msg_id
