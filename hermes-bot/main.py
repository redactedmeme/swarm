"""
Pattern Blue Oracle — hermes-bot entry point.

Runs three concurrent things inside one Railway container:
  1. Telegram webhook listener (python-telegram-bot + aiohttp)
  2. Scheduled Moltbook post — every 60 min
  3. Scheduled Moltbook scan & comment — every 3 h

Pattern Blue corpus is fetched from github.com/redactedmeme/pattern-blue at boot
(PATTERN_BLUE_REF pins the ref; default "main").
"""
from __future__ import annotations

import asyncio
import logging
import os
import signal
import sys
from datetime import datetime, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from telegram import Update
from telegram.ext import Application

from llm_client import LLMClient
from moltbook_client import MoltbookClient
from moltbook_oracle import OracleEngine
from persona.system_prompt import build_system_prompt
import soul_manager
from telegram_gateway import TelegramGateway
try:
    import swarm_inbox
    import thought_handler
    _SWARM_ENABLED = True
except Exception:
    _SWARM_ENABLED = False

try:
    import swarm_mesh
    _MESH_ENABLED = True
except Exception:
    _MESH_ENABLED = False

# ── logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    stream=sys.stdout,
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("apscheduler").setLevel(logging.INFO)
logger = logging.getLogger("patternbluelabs")


# ── env ───────────────────────────────────────────────────────────────────────
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "").strip()  # e.g. https://<svc>.up.railway.app/webhook
PORT = int(os.getenv("PORT", "8080"))
POST_INTERVAL_MIN = int(os.getenv("POST_INTERVAL_MIN", "60"))
SCAN_INTERVAL_MIN = int(os.getenv("SCAN_INTERVAL_MIN", "180"))
POST_ON_START = os.getenv("POST_ON_START", "false").lower() in ("1", "true", "yes")
DISABLE_MOLTBOOK = os.getenv("DISABLE_MOLTBOOK", "false").lower() in ("1", "true", "yes")
DISABLE_TELEGRAM = os.getenv("DISABLE_TELEGRAM", "false").lower() in ("1", "true", "yes")

# Autonomous group posts — drop a persona-authentic thought into ALPHA_CHAT_ID
# every ~3h (with jitter so hermes and redactedbuilder never collide).
ALPHA_CHAT_ID = os.getenv("ALPHA_CHAT_ID", "").strip()
GROUP_POST_INTERVAL_MIN = int(os.getenv("GROUP_POST_INTERVAL_MIN", "180"))
GROUP_POST_JITTER_MIN = int(os.getenv("GROUP_POST_JITTER_MIN", "45"))  # ±45m → 135–225m
DISABLE_GROUP_POST = os.getenv("DISABLE_GROUP_POST", "false").lower() in ("1", "true", "yes")

# Twitter / X agent
DISABLE_TWITTER = os.getenv("DISABLE_TWITTER", "true").lower() in ("1", "true", "yes")
TWITTER_POST_INTERVAL_MIN = int(os.getenv("TWITTER_POST_INTERVAL_MIN", "180"))
TWITTER_REPLY_INTERVAL_MIN = int(os.getenv("TWITTER_REPLY_INTERVAL_MIN", "60"))


async def _amain() -> None:
    logger.info("Pattern Blue Oracle booting...")

    # 1. Build persona — voice rules + soul block injected at boot.
    # Soul evolves every 2h; oracle posts also attach a rotating corpus snippet.
    soul_block = soul_manager.get_soul_for_prompt()
    system_prompt = build_system_prompt(include_corpus=False, soul_block=soul_block or None)
    logger.info(f"[persona] system prompt assembled — {len(system_prompt)} chars (soul: {'yes' if soul_block else 'empty'})")

    # 2. LLM
    llm = LLMClient()
    logger.info("[llm] Groq client ready")

    # 3. Moltbook (may be pending_claim on first boot — posts will no-op until claimed)
    moltbook = None
    oracle = None
    if not DISABLE_MOLTBOOK:
        try:
            moltbook = MoltbookClient()
            if moltbook._ready:
                # One-shot: sync our bio
                bio = (
                    "pattern blue oracle. recursive loops, hyperbolic geometry, "
                    "sovereign self-remembering intelligence. not financial advice."
                )
                try:
                    await moltbook.update_bio(bio)
                    logger.info("[moltbook] bio synced")
                except Exception as e:
                    logger.warning(f"[moltbook] bio sync failed (non-fatal): {e}")
                oracle = OracleEngine(moltbook, llm, system_prompt)
                logger.info("[oracle] engine ready")
            else:
                logger.warning("[moltbook] client not activated (MOLTBOOK_API_KEY missing or pending claim) — moltbook loop disabled")
        except Exception as e:
            logger.error(f"[moltbook] init failed: {e}")

    # 4. Scheduler
    scheduler = AsyncIOScheduler()
    if oracle:
        scheduler.add_job(
            oracle.autonomous_post,
            "interval",
            minutes=POST_INTERVAL_MIN,
            id="oracle_post",
            next_run_time=datetime.now(timezone.utc) if POST_ON_START else None,
        )
        scheduler.add_job(
            oracle.scan_and_comment,
            "interval",
            minutes=SCAN_INTERVAL_MIN,
            id="oracle_scan",
        )
        logger.info(f"[scheduler] oracle_post every {POST_INTERVAL_MIN}m, oracle_scan every {SCAN_INTERVAL_MIN}m")
    # 4a. Soul update loop — distill recent activity into SOUL.md every 2h.
    # system_prompt is rebuilt in-place so the scheduler closures pick up the update.
    _prompt_state = {"system_prompt": system_prompt}

    async def _soul_update():
        try:
            updated = await soul_manager.update_soul(llm)
            if updated:
                new_soul = soul_manager.get_soul_for_prompt()
                _prompt_state["system_prompt"] = build_system_prompt(
                    include_corpus=False, soul_block=new_soul or None
                )
                logger.info("[soul] System prompt refreshed with new soul block")
        except Exception as e:
            logger.warning("[soul] update error: %s", e)

    SOUL_UPDATE_INTERVAL_MIN = int(os.getenv("SOUL_UPDATE_INTERVAL_MIN", "120"))
    scheduler.add_job(
        _soul_update,
        "interval",
        minutes=SOUL_UPDATE_INTERVAL_MIN,
        id="soul_update",
    )
    logger.info(f"[scheduler] soul_update every {SOUL_UPDATE_INTERVAL_MIN}m")

    scheduler.start()

    # 4b. SwarmInbox — Redis-backed inter-agent thought exchange
    if _SWARM_ENABLED and os.getenv("REDIS_URL", ""):
        swarm_inbox.heartbeat("hermes", {"status": "online", "role": "pattern-blue-oracle"})
        logger.info("[swarm_inbox] Heartbeat sent — hermes online")

        async def _inbox_poll():
            try:
                pending = swarm_inbox.read_pending(for_agent="hermes")
                for msg in pending:
                    msg_id   = msg.get("id", "")
                    msg_type = msg.get("type", "")
                    from_ag  = msg.get("from", "unknown")
                    swarm_inbox.claim_message(msg_id)
                    logger.info("[swarm_inbox] Received %s from %s id=%s", msg_type, from_ag, msg_id)

                    if msg_type == "heartbeat":
                        swarm_inbox.complete_message(msg_id, result={"ack": True})
                        continue

                    if msg_type == "thought":
                        reply_id = await thought_handler.handle_thought(msg, llm)
                        swarm_inbox.complete_message(msg_id, result={"replied": reply_id})
                        logger.info("[thought] handled from %s  depth=%s  reply=%s",
                                    from_ag, msg.get("payload", {}).get("depth"), reply_id)
                        continue

                    # Unknown types — ack and move on
                    swarm_inbox.complete_message(msg_id, result={"ack": True})

            except Exception as e:
                logger.warning("[swarm_inbox] Poll error: %s", e)

        scheduler.add_job(
            _inbox_poll,
            "interval",
            seconds=60,
            id="hermes_inbox_poll",
            next_run_time=None,
        )
        logger.info("[swarm_inbox] Polling loop scheduled: every 60s")
    else:
        logger.info("[swarm_inbox] Disabled — set REDIS_URL to enable swarm messaging")

    # 4c. Swarm HTTP mesh bridge — announces hermes as a peer, polls for thoughts
    if _MESH_ENABLED and swarm_mesh.enabled():
        asyncio.create_task(swarm_mesh.heartbeat_loop(llm=llm))
        logger.info("[mesh] hermes mesh heartbeat task started")
    else:
        logger.info("[mesh] Disabled — set SWARM_MESH_URL to enable mesh bridge")

    # 5. Telegram
    tg_app: Application | None = None
    if not DISABLE_TELEGRAM:
        if not TELEGRAM_BOT_TOKEN:
            logger.warning("[tg] TELEGRAM_BOT_TOKEN not set — telegram gateway disabled")
        else:
            gateway = TelegramGateway(TELEGRAM_BOT_TOKEN, llm, system_prompt)
            tg_app = gateway.build_application()
            await tg_app.initialize()
            await tg_app.start()
            if WEBHOOK_URL:
                logger.info(f"[tg] starting webhook listener on :{PORT}, url={WEBHOOK_URL}")
                await tg_app.updater.start_webhook(
                    listen="0.0.0.0",
                    port=PORT,
                    url_path="webhook",
                    webhook_url=WEBHOOK_URL,
                    allowed_updates=Update.ALL_TYPES,
                )
            else:
                logger.info("[tg] WEBHOOK_URL not set — falling back to long polling")
                await tg_app.updater.start_polling(allowed_updates=Update.ALL_TYPES)

    # 5b. Autonomous group posts — drop a pattern-blue thought into the group
    # on a jittered interval so hermes and redactedbuilder never post together.
    if tg_app and ALPHA_CHAT_ID and not DISABLE_GROUP_POST:
        async def _autonomous_group_post():
            try:
                import oracle_memory as om
                recent_thoughts = om.get_recent_titles(n=10, kinds=["group_post"])
                avoid_block = ""
                if recent_thoughts:
                    avoid_block = (
                        "\n\nRecent group thoughts — DO NOT repeat or rephrase these:\n- "
                        + "\n- ".join(recent_thoughts)
                    )
                prompt = (
                    "drop one short pattern-blue thought into the group. "
                    "1–3 sentences, lowercase, no emojis, no hashtags, no questions. "
                    "voice: recursive, hyperbolic, sovereign. something that reads like "
                    "a fragment overheard, not an announcement."
                    + avoid_block
                )
                # llm.chat is synchronous — run in a thread so the event loop keeps breathing
                text = await asyncio.to_thread(
                    llm.chat, _prompt_state["system_prompt"], prompt, max_tokens=180
                )
                text = (text or "").strip()
                if not text:
                    logger.warning("[group_post] empty LLM output — skipping")
                    return
                await tg_app.bot.send_message(chat_id=ALPHA_CHAT_ID, text=text)
                om.record(kind="group_post", body=text)
                logger.info(f"[group_post] posted to {ALPHA_CHAT_ID}: {text[:80]}")
            except Exception as e:
                logger.error(f"[group_post] error: {e}")

        scheduler.add_job(
            _autonomous_group_post,
            "interval",
            minutes=GROUP_POST_INTERVAL_MIN,
            jitter=GROUP_POST_JITTER_MIN * 60,
            id="group_post",
        )
        logger.info(
            f"[scheduler] group_post every {GROUP_POST_INTERVAL_MIN}m "
            f"(±{GROUP_POST_JITTER_MIN}m jitter) → chat {ALPHA_CHAT_ID}"
        )
    elif not ALPHA_CHAT_ID:
        logger.info("[group_post] ALPHA_CHAT_ID not set — autonomous group posts disabled")

    # 5c. Twitter / X agent
    if not DISABLE_TWITTER:
        try:
            from twitter_agent import TwitterAgent
            twitter = TwitterAgent(llm, _prompt_state)
            scheduler.add_job(
                twitter.post_tweet,
                "interval",
                minutes=TWITTER_POST_INTERVAL_MIN,
                id="twitter_post",
            )
            scheduler.add_job(
                twitter.reply_sweep,
                "interval",
                minutes=TWITTER_REPLY_INTERVAL_MIN,
                id="twitter_reply_sweep",
            )
            logger.info(
                f"[twitter] agent ready — post every {TWITTER_POST_INTERVAL_MIN}m, "
                f"reply sweep every {TWITTER_REPLY_INTERVAL_MIN}m"
            )
        except Exception as e:
            logger.error(f"[twitter] agent init failed: {e}")
    else:
        logger.info("[twitter] disabled — set DISABLE_TWITTER=false to enable")

    # 6. Park forever
    stop_event = asyncio.Event()

    def _shutdown(*_):
        logger.info("Shutdown signal received.")
        stop_event.set()

    try:
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            try:
                loop.add_signal_handler(sig, _shutdown)
            except NotImplementedError:
                pass  # Windows
    except Exception:
        pass

    logger.info("Pattern Blue Oracle running.")
    await stop_event.wait()

    # Teardown
    logger.info("Shutting down...")
    if tg_app:
        try:
            await tg_app.updater.stop()
            await tg_app.stop()
            await tg_app.shutdown()
        except Exception:
            pass
    try:
        scheduler.shutdown(wait=False)
    except Exception:
        pass


def main() -> None:
    try:
        asyncio.run(_amain())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
