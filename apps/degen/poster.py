"""Minimal outbound posting surface for RedactedDegen.

Full-autonomy posting degrades gracefully: if no Telegram token/chat is
configured the "post" is only recorded to the activity log, so the agent still
runs end-to-end without operator provisioning.
"""
from __future__ import annotations

import logging
import os

import aiohttp

logger = logging.getLogger(__name__)

_TOKEN = os.getenv("DEGEN_TG_BOT_TOKEN", "").strip()
_CHAT = os.getenv("DEGEN_TG_CHAT_ID", "").strip()
POST_ENABLED = os.getenv("DEGEN_POST_ENABLED", "true").strip().lower() in ("1", "true", "yes")


def surface() -> str:
    if not POST_ENABLED:
        return "disabled"
    return "telegram" if (_TOKEN and _CHAT) else "log-only"


async def post(text: str) -> bool:
    """Send ``text`` to the configured surface. Returns True if it left the box."""
    if not POST_ENABLED or not (_TOKEN and _CHAT):
        logger.info("[degen post/%s] %s", surface(), text[:280])
        return False
    url = f"https://api.telegram.org/bot{_TOKEN}/sendMessage"
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(url, json={"chat_id": _CHAT, "text": text[:3500],
                                         "disable_web_page_preview": True},
                              timeout=aiohttp.ClientTimeout(total=10)) as r:
                if r.status != 200:
                    logger.warning("[degen post] telegram %s: %s", r.status, await r.text())
                    return False
        return True
    except Exception as e:  # noqa: BLE001
        logger.warning("[degen post] send failed: %s", e)
        return False
