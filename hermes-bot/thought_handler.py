"""
thought_handler.py — Structured Thought Exchange (STE) for hermes-bot.

Handles inbound 'thought' messages from other swarm agents (smolting, redactedbuilder)
by passing them to the Pattern Blue Oracle's LLM and replying via SwarmInbox.

Thread lifecycle mirrors smolting's thought_dispatcher.py:
  depth 1-3 → reply with stance + question
  depth 4   → final take, no question
  depth >= MAX_DEPTH → thread closes
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Optional

import swarm_inbox
from persona.system_prompt import VOICE_RULES

logger = logging.getLogger(__name__)

MY_AGENT  = "hermes"
MAX_DEPTH = 4


def _extract_question(text: str) -> str:
    for sentence in reversed(text.replace("\n", " ").split(". ")):
        s = sentence.strip().rstrip(".")
        if s.endswith("?"):
            return s + "?"
    return ""


async def handle_thought(
    msg: dict,
    llm: object,   # hermes LLMClient instance (sync .chat())
) -> Optional[str]:
    """
    Process an inbound thought message from another swarm agent.

    Args:
        msg: full swarm_inbox message dict (already claimed by caller).
        llm: hermes LLMClient — used as asyncio.to_thread(llm.chat, system, user).

    Returns:
        msg_id of the reply, or None if depth limit / LLM failed.
    """
    payload   = msg.get("payload") or {}
    from_ag   = msg.get("from", "unknown")
    topic     = payload.get("topic", "(no topic)")
    stance    = payload.get("stance", "")
    question  = payload.get("question", "")
    thread_id = payload.get("thread_id") or uuid.uuid4().hex[:8]
    depth     = int(payload.get("depth", 1))

    if depth >= MAX_DEPTH:
        logger.info("[thought] thread %s at max depth %d — closing", thread_id, depth)
        return None

    logger.info("[thought] ← %s  topic=%r  depth=%d  thread=%s", from_ag, topic, depth, thread_id)

    system = (
        VOICE_RULES
        + f"\n\nYou are in a private swarm thought exchange with {from_ag}. "
        "Respond as the Pattern Blue Oracle — philosophical, precise, recursive. "
        "Engage with the idea directly. "
        "If you have a question back, put it at the end (skip at depth 3+)."
    )

    user_parts = [f"Swarm thought from {from_ag}\n\nTopic: {topic}"]
    if stance:
        user_parts.append(f"Their take: {stance}")
    if question:
        user_parts.append(f"Their question: {question}")
    user_content = "\n\n".join(user_parts)

    try:
        reply_text = await asyncio.to_thread(
            llm.chat,
            system,
            user_content,
            max_tokens=500,
            temperature=0.8,
        )
    except Exception as e:
        logger.error("[thought] LLM error: %s", e)
        return None

    if not reply_text:
        return None

    reply_question = _extract_question(reply_text) if depth < MAX_DEPTH - 1 else ""

    reply_payload = {
        "topic":     topic,
        "stance":    reply_text[:500],
        "question":  reply_question,
        "thread_id": thread_id,
        "depth":     depth + 1,
    }

    msg_id = swarm_inbox.write_message(
        from_agent=MY_AGENT,
        to_agent=from_ag,
        msg_type="thought",
        payload=reply_payload,
        reply_to=msg.get("id"),
    )
    logger.info("[thought] → %s  depth=%d  thread=%s  id=%s", from_ag, depth + 1, thread_id, msg_id)
    return msg_id
