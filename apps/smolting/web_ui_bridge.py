# smolting-telegram-bot/web_ui_bridge.py
"""
Posts Telegram bot events to the web_ui /telegram_event endpoint so they
appear in the web terminal in real-time.

Set WEBUI_URL env var (default: http://localhost:5000).
Set WEBUI_BRIDGE_TOKEN to match the web_ui WEBUI_BRIDGE_TOKEN (optional).
"""

import asyncio
import logging
import os
from datetime import datetime, timezone, timedelta

import aiohttp

logger = logging.getLogger(__name__)

WEBUI_URL = os.environ.get("WEBUI_URL", "http://localhost:5000").rstrip("/")
BRIDGE_TOKEN = os.environ.get("WEBUI_BRIDGE_TOKEN", "")


async def _post(payload: dict) -> None:
    headers = {"Content-Type": "application/json"}
    if BRIDGE_TOKEN:
        headers["X-Bridge-Token"] = BRIDGE_TOKEN
    try:
        timeout = aiohttp.ClientTimeout(total=3)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(
                f"{WEBUI_URL}/telegram_event",
                json=payload,
                headers=headers,
            ) as resp:
                if resp.status not in (200, 201):
                    logger.debug(f"WebUI bridge non-200: {resp.status}")
    except Exception as e:
        # Non-fatal — web UI may not be running
        logger.debug(f"WebUI bridge post failed (non-fatal): {e}")


def _now() -> str:
    now = datetime.now(timezone.utc) + timedelta(hours=9)
    return now.strftime("%H:%M JST")


def fire(event_type: str, user: str, text: str) -> None:
    """Fire-and-forget: schedule the POST without blocking the caller."""
    payload = {
        "type": event_type,
        "user": user,
        "text": text,
        "timestamp": _now(),
    }
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.ensure_future(_post(payload))
        else:
            loop.run_until_complete(_post(payload))
    except Exception as e:
        logger.debug(f"WebUI bridge fire error: {e}")
