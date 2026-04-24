"""
thought_dispatcher.py — Structured Thought Exchange (STE) for smolting.

Handles inbound 'thought' messages from other swarm agents (hermes, redactedbuilder)
by passing them to smolting's LLM and replying via SwarmInbox.

Also provides initiate_thought() so smolting can start new exchanges.

Thread lifecycle:
  depth 1  — initiator sends first thought
  depth 2  — recipient replies + asks back
  depth 3  — initiator responds
  depth 4  — recipient sends final take (no question required)
  depth >= MAX_DEPTH — thread closes, no more replies
"""
from __future__ import annotations

import logging
import os
import uuid
from pathlib import Path
from typing import Callable, Awaitable, Optional

import swarm_inbox

logger = logging.getLogger(__name__)

MY_AGENT  = "redactedintern"
MAX_DEPTH = 4  # total turns before thread closes


def _load_soul() -> str:
    """Read current SOUL.md for persona injection (best-effort)."""
    soul_path = Path(
        os.getenv("MEMORY_PATH", str(Path(__file__).resolve().parent / "memory.md"))
    ).parent / "SOUL.md"
    try:
        if soul_path.exists():
            content = soul_path.read_text(encoding="utf-8")
            # Trim to first 1800 chars so we don't blow the context budget
            return content[:1800].strip()
    except Exception:
        pass
    return ""


def _extract_question(text: str) -> str:
    """Pull the last interrogative sentence out of a reply, if any."""
    for sentence in reversed(text.replace("\n", " ").split(". ")):
        s = sentence.strip().rstrip(".")
        if s.endswith("?"):
            return s + "?"
    return ""


async def handle_thought(
    msg: dict,
    llm_call: Callable[[list[dict]], Awaitable[str]],
) -> Optional[str]:
    """
    Process an inbound thought message from another agent.

    Args:
        msg:      Full swarm_inbox message dict (already claimed by caller).
        llm_call: async fn(messages: list[dict]) -> str  (smolting's LLM wrapper).

    Returns:
        msg_id of the reply sent, or None if depth limit reached / LLM failed.
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

    soul = _load_soul()
    system = "\n\n".join(filter(None, [
        soul,
        (
            f"You are smolting (RedactedIntern). {from_ag} has sent you a thought via the swarm mesh. "
            "Respond genuinely in your own voice — curious, specific, first-person. "
            "No filler. Engage with the actual idea. "
            "If you have a question back, put it at the end (skip the question at depth 3+)."
        ),
    ]))

    user_parts = [f"**Swarm thought from {from_ag}**\n\nTopic: {topic}"]
    if stance:
        user_parts.append(f"Their take: {stance}")
    if question:
        user_parts.append(f"Their question to you: {question}")
    user_content = "\n\n".join(user_parts)

    try:
        reply_text = await llm_call([
            {"role": "system", "content": system},
            {"role": "user",   "content": user_content},
        ])
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


async def initiate_thought(
    to_agent: str,
    topic: str,
    stance: str,
    question: str = "",
) -> str:
    """
    Start a new thought exchange with another agent.

    Args:
        to_agent: target agent name (e.g. "hermes", "redactedbuilder")
        topic:    conversation topic
        stance:   smolting's opening perspective
        question: optional question to pose

    Returns:
        msg_id of the sent thought.
    """
    thread_id = uuid.uuid4().hex[:8]
    msg_id = swarm_inbox.write_message(
        from_agent=MY_AGENT,
        to_agent=to_agent,
        msg_type="thought",
        payload={
            "topic":     topic,
            "stance":    stance,
            "question":  question,
            "thread_id": thread_id,
            "depth":     1,
        },
    )
    logger.info("[thought] initiated → %s  topic=%r  thread=%s  id=%s", to_agent, topic, thread_id, msg_id)
    return msg_id
