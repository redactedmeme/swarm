# redacted-chan-bot/fact_extractor.py
"""
Fact Extractor — LLM-based extraction of persistent facts about master from each exchange.

Runs as a fire-and-forget task after every response. Pulls concrete, long-lived facts
(birthday, preferences, what he's building, habits, beliefs) from the user's message
and stores them via conversation_memory.append_fact().

Facts already known are deduplicated by conversation_memory before writing.
"""

import logging
from typing import Optional, Callable, Awaitable

import conversation_memory as cm
import vector_memory as vm

logger = logging.getLogger(__name__)

_llm_fn: Optional[Callable[[list, int], Awaitable[str]]] = None

_SYSTEM = """\
You extract concrete, lasting facts about a person from a conversation exchange.

Rules:
- Only extract facts that would still be true in 6 months (not mood, not "seems happy today")
- Only extract facts about the USER, not about yourself or the conversation
- Be specific: "birthday is April 28" not "mentioned a date"
- One fact per line, plain sentence, lowercase
- Max 3 facts per exchange
- If nothing concrete to extract, return exactly: NONE

Examples of good facts:
- user's zodiac sign is aries
- user is building a telegram bot called redacted-chan
- user prefers direct communication over small talk
- user's birthday is april 28
- user works on ai projects

Examples of bad facts (do NOT extract):
- user seems happy
- user asked about image generation
- user is testing the bot"""


def register_llm_fn(fn: Callable[[list, int], Awaitable[str]]) -> None:
    global _llm_fn
    _llm_fn = fn


async def extract_and_store(user_id: int, user_msg: str, bot_reply: str) -> None:
    """
    Extract facts from one exchange and store any new ones.
    Called as asyncio.create_task() — never blocks the response path.
    """
    if not _llm_fn:
        return
    if not user_msg or len(user_msg.strip()) < 8:
        return

    messages = [
        {"role": "system", "content": _SYSTEM},
        {"role": "user", "content": (
            f"User message: {user_msg.strip()[:600]}\n"
            f"Bot reply: {bot_reply.strip()[:300]}\n\n"
            "What concrete facts did you learn about the user?"
        )},
    ]

    try:
        result = await _llm_fn(messages, 120)
        if not result or result.strip().upper() == "NONE":
            return

        facts = [
            line.strip().lstrip("-•* ").strip()
            for line in result.strip().splitlines()
            if line.strip() and line.strip().upper() != "NONE"
        ]

        stored = 0
        for fact in facts[:3]:
            if fact and len(fact) > 8:
                fact_id = cm.append_fact(fact, source="fact_extractor")
                if fact_id:
                    vm.add_fact(fact_id, fact)
                    stored += 1

        if stored:
            logger.info(f"[fact_extractor] stored {stored} fact(s) from exchange")

    except Exception as e:
        logger.debug(f"[fact_extractor] error: {e}")
