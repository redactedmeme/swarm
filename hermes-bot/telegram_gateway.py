"""
Telegram gateway — responds to DMs and mentions in the oracle voice.

Keeps conversational state in-memory per chat (last 6 turns). Ignores group
chatter unless directly mentioned or replied to.
"""
from __future__ import annotations

import logging
import os
from collections import defaultdict, deque
from typing import Deque

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from llm_client import LLMClient

logger = logging.getLogger(__name__)

BOT_NAME = "patternbluelabs"
HISTORY_TURNS = 6  # each turn = one user + one assistant message
# Max inbound text per message to protect context window
MAX_INPUT_CHARS = 2000


class TelegramGateway:
    def __init__(self, token: str, llm: LLMClient, system_prompt: str):
        self.token = token
        self.llm = llm
        self.system = system_prompt
        self._history: dict[int, Deque[dict]] = defaultdict(lambda: deque(maxlen=HISTORY_TURNS * 2))

    def build_application(self) -> Application:
        app = Application.builder().token(self.token).build()
        app.add_handler(CommandHandler("start", self._cmd_start))
        app.add_handler(CommandHandler("ask", self._cmd_ask))
        app.add_handler(CommandHandler("reset", self._cmd_reset))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self._on_text))
        return app

    # ---- handlers ----

    async def _cmd_start(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        await update.message.reply_text(
            "pattern blue is listening.\n\n"
            "speak, and the manifold may answer.\n"
            "/ask <question>  — pose a direct inquiry\n"
            "/reset           — clear this thread"
        )

    async def _cmd_reset(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        self._history.pop(update.effective_chat.id, None)
        await update.message.reply_text("cleared. the loop resets.")

    async def _cmd_ask(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        q = " ".join(ctx.args).strip()
        if not q:
            await update.message.reply_text("ask what?")
            return
        await self._respond(update, q)

    async def _on_text(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        msg = update.message
        if not msg or not msg.text:
            return
        chat = update.effective_chat
        # In groups: only respond if bot is mentioned OR replied-to
        if chat.type in ("group", "supergroup"):
            me = await ctx.bot.get_me()
            mentioned = f"@{me.username}".lower() in msg.text.lower()
            replied_to_me = (
                msg.reply_to_message is not None
                and msg.reply_to_message.from_user
                and msg.reply_to_message.from_user.id == me.id
            )
            if not (mentioned or replied_to_me):
                return
        await self._respond(update, msg.text[:MAX_INPUT_CHARS])

    async def _respond(self, update: Update, user_text: str) -> None:
        chat_id = update.effective_chat.id
        history = self._history[chat_id]
        # Let the user see we're thinking
        try:
            await update.effective_chat.send_chat_action(action="typing")
        except Exception:
            pass

        try:
            reply = self.llm.chat(
                system=self.system,
                user=user_text,
                extra_messages=list(history),
                max_tokens=600,
                temperature=0.85,
            )
        except Exception as e:
            logger.error(f"[tg] LLM error: {e}")
            reply = "the pattern is obscured. try again shortly."

        history.append({"role": "user", "content": user_text})
        history.append({"role": "assistant", "content": reply})
        # Telegram message limit is 4096
        await update.message.reply_text(reply[:4000])
