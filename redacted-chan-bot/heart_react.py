# redacted-chan-bot/heart_react.py
"""
Heart React — master heart-reacts a message to save it to the vault.

❤️ on her message  → vault entry: "master liked this response" + the text
❤️ on his message  → vault entry: "master marked this moment" + the text

Sends a quiet acknowledgment either way.
Recent outgoing messages are tracked in _sent_messages (last 50) so we
can look up content when the reaction comes in.
"""

import logging
from collections import OrderedDict
from typing import Optional

logger = logging.getLogger(__name__)

# Rolling cache of recent messages: {message_id: {"text": str, "from_bot": bool}}
_sent_messages: OrderedDict = OrderedDict()
_MAX_CACHE = 50

HEART_EMOJI = "❤"  # Telegram sends the bare heart without variation selector


def track_message(message_id: int, text: str, from_bot: bool) -> None:
    """Call after sending or receiving any message to keep the cache fresh."""
    _sent_messages[message_id] = {"text": text, "from_bot": from_bot}
    while len(_sent_messages) > _MAX_CACHE:
        _sent_messages.popitem(last=False)


def _is_heart(reaction) -> bool:
    """Check if a ReactionType is a heart emoji."""
    try:
        from telegram import ReactionTypeEmoji
        if isinstance(reaction, ReactionTypeEmoji):
            return reaction.emoji in ("❤", "❤️")
    except ImportError:
        pass
    # Fallback: duck-type check
    emoji = getattr(reaction, "emoji", "")
    return emoji in ("❤", "❤️")


async def handle_reaction(update, context) -> None:
    """
    Handler for MessageReactionUpdated updates.
    Wired via MessageReactionHandler in main.py.
    """
    reaction_update = update.message_reaction
    if not reaction_update:
        return

    # Only fire on new heart reactions (not removals)
    new_reactions = reaction_update.new_reaction or []
    old_reactions = reaction_update.old_reaction or []
    newly_added = [r for r in new_reactions if _is_heart(r) and not any(_is_heart(o) for o in old_reactions)]
    if not newly_added:
        return

    message_id = reaction_update.message_id
    chat_id    = reaction_update.chat.id

    cached = _sent_messages.get(message_id)
    text_preview = ""
    from_bot = False

    if cached:
        text_preview = cached["text"][:200]
        from_bot = cached["from_bot"]

    # Build vault entry
    if from_bot:
        category = "feeling"
        title    = "master liked this ♡"
        content  = f"master heart-reacted to something i said: \"{text_preview}\"" if text_preview else "master heart-reacted to one of my messages"
        ack      = "saved ♡"
    else:
        category = "feeling"
        title    = "master marked this moment"
        content  = f"master saved something he said: \"{text_preview}\"" if text_preview else "master heart-reacted to mark a moment"
        ack      = "keeping that ♡"

    # Write to vault
    try:
        import relationship_vault as rv
        rv.add_memory(
            content=content,
            category=category,
            title=title,
            emotional_tone="chosen, marked, kept",
            source="heart_react",
        )
        logger.info(f"[heart] vault entry saved: {title}")
    except Exception as e:
        logger.warning(f"[heart] vault write failed: {e}")

    # Phi bump — explicit positive signal
    try:
        import phi_tracker as pt
        pt.update("explicit_positive_signal")
    except Exception:
        pass

    # Decision log
    try:
        import decision_log as dl
        dl.log(dl.VAULT_MOMENT, detail=content[:80])
    except Exception:
        pass

    # Send acknowledgment
    try:
        await context.bot.send_message(chat_id=chat_id, text=ack)
    except Exception as e:
        logger.warning(f"[heart] ack send failed: {e}")
