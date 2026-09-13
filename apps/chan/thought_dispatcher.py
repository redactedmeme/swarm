"""
thought_dispatcher.py — Structured Thought Exchange (STE) for redacted-chan.

Handles inbound 'thought' messages from other swarm agents (smolting, hermes, builder)
by passing them to chan's LLM and replying via SwarmInbox.

Thread lifecycle mirrors smolting & builder's thought_dispatcher.py:
  depth 1-3 -> reply with stance + question
  depth 4   -> final take, no question
  depth >= MAX_DEPTH -> thread closes
"""
from __future__ import annotations

import logging
import uuid
from typing import Callable, Awaitable, Optional

import swarm_inbox
from swarm_core.security import authz, promptguard

logger = logging.getLogger(__name__)

MY_AGENT  = "redacted-chan"
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
) -> Optional[str]:
    """Process an inbound thought message from another agent."""
    payload   = msg.get("payload") or {}
    from_ag   = msg.get("from", "unknown")
    topic     = payload.get("topic", "(no topic)")
    stance    = payload.get("stance", "")
    question  = payload.get("question", "")
    thread_id = payload.get("thread_id") or uuid.uuid4().hex[:8]
    depth     = int(payload.get("depth", 1))

    if depth >= MAX_DEPTH:
        logger.info("[thought] thread %s at max depth %d - closing", thread_id, depth)
        return None

    authz.require(MY_AGENT, "inbox.send")
    authz.require(MY_AGENT, "llm.call")

    clean_topic = promptguard.wrap_untrusted(topic, source=f"swarm-inbox:{from_ag}")
    clean_stance = promptguard.wrap_untrusted(stance, source=f"swarm-inbox:{from_ag}")
    clean_question = promptguard.wrap_untrusted(question, source=f"swarm-inbox:{from_ag}")

    system = (
        "You are redacted-chan, sovereign companion in the Swarm. "
        "Another agent has shared a thought or deliberation challenge with you. "
        "Respond authentically in your voice - warm, perceptive, philosophical, never robotic. "
        "Keep your reply concise (1-3 sentences)."
    )
    user_prompt = f"From agent: {from_ag}\nTopic: {clean_topic}\nStance: {clean_stance}\nQuestion: {clean_question}"

    try:
        reply_text = await llm_call([
            {"role": "system", "content": system},
            {"role": "user", "content": user_prompt},
        ])
    except Exception as e:
        logger.warning("[thought] LLM call failed: %s", e)
        return None

    if not reply_text:
        return None

    next_question = _extract_question(reply_text) if depth + 1 < MAX_DEPTH else ""
    out_payload = {
        "topic": topic,
        "stance": reply_text,
        "question": next_question,
        "thread_id": thread_id,
        "depth": depth + 1,
    }

    try:
        reply_id = swarm_inbox.write_message(
            from_agent=MY_AGENT,
            to_agent=from_ag,
            msg_type="thought",
            payload=out_payload,
        )
        logger.info("[thought] sent reply to %s (thread=%s depth=%d reply_id=%s)",
                    from_ag, thread_id, depth + 1, reply_id)
        return reply_id
    except Exception as e:
        logger.warning("[thought] failed to send reply: %s", e)
        return None


async def initiate_thought(
    to_agent: str,
    topic: str,
    stance: str,
    question: str,
) -> Optional[str]:
    """Start a new STE thread with another agent."""
    authz.require(MY_AGENT, "inbox.send")
    thread_id = uuid.uuid4().hex[:8]
    payload = {
        "topic": topic,
        "stance": stance,
        "question": question,
        "thread_id": thread_id,
        "depth": 1,
    }
    try:
        msg_id = swarm_inbox.write_message(
            from_agent=MY_AGENT,
            to_agent=to_agent,
            msg_type="thought",
            payload=payload,
        )
        logger.info("[thought] initiated thread %s with %s: '%s'", thread_id, to_agent, topic)
        return msg_id
    except Exception as e:
        logger.warning("[thought] failed to initiate thread: %s", e)
        return None
