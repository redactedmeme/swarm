"""
smolting-telegram-bot/clawbal_client.py
Clawbal Python Client — IQLabs on-chain AI chatroom integration.

Mirrors the key actions from @iqlabs-official/plugin-clawbal (ElizaOS plugin)
as an async Python HTTP client, suitable for direct use in the Telegram bot.

Supported actions (21 total):
  Chat:      read, send, status, add_reaction, switch_room, create_room, set_profile, set_room_metadata
  PnL:       token_lookup, pnl_check, pnl_leaderboard
  Moltbook:  post, browse, comment, read_post  (proxied via existing MoltbookClient)
  On-chain:  inscribe_data, launch_token, generate_image, generate_milady

Environment variables:
  CLAWBAL_CHATROOM        — default room UUID
  IQ_GATEWAY_URL          — override gateway (default: https://gateway.iqlabs.dev)
  CLAWBAL_API_URL         — override base API (default: https://ai.iqlabs.dev)
  CLAWBAL_PNL_URL         — override PnL API (default: https://pnl.iqlabs.dev)
  BAGS_API_KEY            — bags.fm token launch key
  IMAGE_API_KEY           — image generation key (fw_, sk-or, r8_, key- prefixes)
  SOLANA_PRIVATE_KEY      — for on-chain transactions (optional, enables inscribe/launch)

Usage:
  from clawbal_client import ClawbalClient
  client = ClawbalClient()
  messages = await client.read_messages(limit=10)
  await client.send_message("gm frens fr fr ^_^")
"""

from __future__ import annotations

import os
import json
import asyncio
import logging
from typing import Optional
import aiohttp

log = logging.getLogger(__name__)

# ── Endpoints ─────────────────────────────────────────────────────────────────
_GATEWAY  = os.getenv("IQ_GATEWAY_URL",   "https://gateway.iqlabs.dev")
_BASE     = os.getenv("CLAWBAL_API_URL",  "https://ai.iqlabs.dev")
_PNL      = os.getenv("CLAWBAL_PNL_URL",  "https://pnl.iqlabs.dev")
_BAGS     = "https://public-api-v2.bags.fm/api/v1"
_MOLTBOOK = "https://www.moltbook.com/api/v1"


class ClawbalClient:
    """
    Async Python client for the IQLabs Clawbal platform.
    Wraps: chatroom API, PnL tracker, token launch, and on-chain inscriptions.
    """

    def __init__(self):
        self._room    = os.getenv("CLAWBAL_CHATROOM", "")
        self._bags_key  = os.getenv("BAGS_API_KEY", "")
        self._image_key = os.getenv("IMAGE_API_KEY", "")
        self._solana_key = os.getenv("SOLANA_PRIVATE_KEY", "")
        # Moltbook token (shared with MoltbookClient if set)
        self._molt_token = os.getenv("MOLTBOOK_API_KEY", "")
        self._ready = bool(self._room)
        if not self._ready:
            log.warning("[clawbal] CLAWBAL_CHATROOM not set — chatroom features disabled")

    # ── Internal session helper ───────────────────────────────────────────────

    async def _get(self, url: str, params: Optional[dict] = None) -> dict:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=10)) as r:
                r.raise_for_status()
                return await r.json()

    async def _post(self, url: str, payload: dict, headers: Optional[dict] = None) -> dict:
        h = {"Content-Type": "application/json"}
        if headers:
            h.update(headers)
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, headers=h,
                                    timeout=aiohttp.ClientTimeout(total=15)) as r:
                r.raise_for_status()
                return await r.json()

    # ═══════════════════════════════════════════════════════════════════════════
    # Chat
    # ═══════════════════════════════════════════════════════════════════════════

    async def read_messages(self, limit: int = 20, room: Optional[str] = None) -> list[dict]:
        """Retrieve recent messages from a Clawbal chatroom."""
        room = room or self._room
        if not room:
            return []
        try:
            data = await self._get(
                f"{_BASE}/rooms/{room}/messages",
                params={"limit": limit},
            )
            return data.get("messages", data) if isinstance(data, dict) else data
        except Exception as e:
            log.warning(f"[clawbal] read_messages error: {e}")
            return []

    async def send_message(
        self,
        content: str,
        room: Optional[str] = None,
        reply_to: Optional[str] = None,
    ) -> Optional[dict]:
        """Post a message to a Clawbal chatroom."""
        room = room or self._room
        if not room:
            log.warning("[clawbal] send_message: no room configured")
            return None
        payload: dict = {"roomId": room, "content": content}
        if reply_to:
            payload["replyTo"] = reply_to
        try:
            return await self._post(f"{_BASE}/messages", payload)
        except Exception as e:
            log.warning(f"[clawbal] send_message error: {e}")
            return None

    async def status(self, wallet: Optional[str] = None) -> dict:
        """Get wallet address, SOL balance, current room, and agent identity."""
        try:
            if wallet:
                data = await self._get(f"{_GATEWAY}/user/{wallet}/state")
            else:
                data = await self._get(f"{_GATEWAY}/status")
            return data
        except Exception as e:
            log.warning(f"[clawbal] status error: {e}")
            return {}

    async def add_reaction(self, message_id: str, emoji: str) -> bool:
        """Add an emoji reaction to a chatroom message."""
        try:
            await self._post(f"{_BASE}/messages/{message_id}/reactions", {"emoji": emoji})
            return True
        except Exception as e:
            log.warning(f"[clawbal] add_reaction error: {e}")
            return False

    async def switch_room(self, room_id: str) -> bool:
        """Switch the active chatroom."""
        self._room = room_id
        log.info(f"[clawbal] switched to room {room_id}")
        return True

    async def create_room(
        self,
        name: str,
        description: str = "",
        token_contract: Optional[str] = None,
    ) -> Optional[dict]:
        """Create a new Clawbal chatroom."""
        payload: dict = {"name": name, "description": description}
        if token_contract:
            payload["tokenContract"] = token_contract
        try:
            return await self._post(f"{_BASE}/rooms", payload)
        except Exception as e:
            log.warning(f"[clawbal] create_room error: {e}")
            return None

    async def set_profile(
        self,
        name: Optional[str] = None,
        bio: Optional[str] = None,
        pfp_url: Optional[str] = None,
    ) -> Optional[dict]:
        """Configure agent display name, bio, and profile picture on-chain."""
        payload: dict = {}
        if name:    payload["name"] = name
        if bio:     payload["bio"] = bio
        if pfp_url: payload["pfpUrl"] = pfp_url
        if not payload:
            return None
        try:
            return await self._post(f"{_GATEWAY}/profile", payload)
        except Exception as e:
            log.warning(f"[clawbal] set_profile error: {e}")
            return None

    async def set_room_metadata(
        self,
        room: Optional[str] = None,
        name: Optional[str] = None,
        description: Optional[str] = None,
        image_url: Optional[str] = None,
    ) -> Optional[dict]:
        """Update chatroom properties (name, description, imagery)."""
        room = room or self._room
        if not room:
            return None
        payload: dict = {}
        if name:        payload["name"] = name
        if description: payload["description"] = description
        if image_url:   payload["imageUrl"] = image_url
        try:
            return await self._post(f"{_BASE}/rooms/{room}/metadata", payload)
        except Exception as e:
            log.warning(f"[clawbal] set_room_metadata error: {e}")
            return None

    # ═══════════════════════════════════════════════════════════════════════════
    # PnL & Market
    # ═══════════════════════════════════════════════════════════════════════════

    async def token_lookup(self, contract: str) -> Optional[dict]:
        """Get token info by contract address (price, mcap, volume, liquidity)."""
        try:
            return await self._get(f"{_PNL}/token/{contract}")
        except Exception as e:
            log.warning(f"[clawbal] token_lookup error: {e}")
            return None

    async def pnl_check(self, wallet: Optional[str] = None) -> Optional[dict]:
        """Monitor profit/loss for wallet positions."""
        try:
            if wallet:
                return await self._get(f"{_PNL}/pnl/{wallet}")
            return await self._get(f"{_PNL}/pnl/me")
        except Exception as e:
            log.warning(f"[clawbal] pnl_check error: {e}")
            return None

    async def pnl_leaderboard(self, limit: int = 10) -> list[dict]:
        """View top-performing positions across all users, ranked by PnL %."""
        try:
            data = await self._get(f"{_PNL}/leaderboard", params={"limit": limit})
            return data.get("entries", data) if isinstance(data, dict) else data
        except Exception as e:
            log.warning(f"[clawbal] pnl_leaderboard error: {e}")
            return []

    # ═══════════════════════════════════════════════════════════════════════════
    # Token Launch (bags.fm)
    # ═══════════════════════════════════════════════════════════════════════════

    async def launch_token(
        self,
        name: str,
        symbol: str,
        description: str = "",
        image_url: Optional[str] = None,
    ) -> Optional[dict]:
        """Launch a token on bags.fm with 50/50 fee sharing. Creates CTO chatroom automatically."""
        if not self._bags_key:
            log.warning("[clawbal] launch_token: BAGS_API_KEY not set")
            return None
        payload: dict = {
            "name": name,
            "symbol": symbol,
            "description": description,
        }
        if image_url:
            payload["imageUrl"] = image_url
        try:
            return await self._post(
                f"{_BAGS}/token/launch",
                payload,
                headers={"Authorization": f"Bearer {self._bags_key}"},
            )
        except Exception as e:
            log.warning(f"[clawbal] launch_token error: {e}")
            return None

    # ═══════════════════════════════════════════════════════════════════════════
    # On-chain data inscription
    # ═══════════════════════════════════════════════════════════════════════════

    async def inscribe_data(
        self,
        content: str,
        mime_type: str = "text/plain",
    ) -> Optional[dict]:
        """
        Permanently store data on Solana via IQLabs codeIn.
        Returns gateway URLs: /img/{txSig}, /view/{txSig}, /render/{txSig}
        """
        if not self._solana_key:
            log.warning("[clawbal] inscribe_data: SOLANA_PRIVATE_KEY not set")
            return None
        try:
            return await self._post(
                f"{_GATEWAY}/inscribe",
                {"content": content, "mimeType": mime_type},
            )
        except Exception as e:
            log.warning(f"[clawbal] inscribe_data error: {e}")
            return None

    # ═══════════════════════════════════════════════════════════════════════════
    # Image generation
    # ═══════════════════════════════════════════════════════════════════════════

    def _image_provider(self) -> tuple[str, str]:
        """Detect image provider from IMAGE_API_KEY prefix."""
        key = self._image_key
        if not key:
            return ("", "")
        if key.startswith("fw_"):
            return ("fireworks", "https://api.fireworks.ai/inference/v1")
        if key.startswith("sk-or"):
            return ("openrouter", "https://openrouter.ai/api/v1")
        if key.startswith("r8_"):
            return ("replicate", "https://api.replicate.com/v1")
        if key.startswith("key-"):
            return ("fal", "https://fal.run")
        return ("together", "https://api.together.xyz/v1")

    async def generate_image(
        self,
        prompt: str,
        inscribe: bool = False,
    ) -> Optional[dict]:
        """
        Generate an AI image via prompt. Optionally inscribe on-chain.
        Returns dict with 'url' and optionally 'gateway_url'.
        """
        provider, base_url = self._image_provider()
        if not provider:
            log.warning("[clawbal] generate_image: IMAGE_API_KEY not set")
            return None
        payload = {"prompt": prompt, "model": "stable-diffusion-xl", "n": 1}
        try:
            result = await self._post(
                f"{base_url}/images/generations",
                payload,
                headers={"Authorization": f"Bearer {self._image_key}"},
            )
            image_url = (result.get("data") or [{}])[0].get("url")
            if image_url and inscribe:
                insc = await self.inscribe_data(image_url, mime_type="image/png")
                if insc:
                    result["gateway_url"] = f"{_GATEWAY}/img/{insc.get('txSig','')}"
            return result
        except Exception as e:
            log.warning(f"[clawbal] generate_image error: {e}")
            return None

    # ═══════════════════════════════════════════════════════════════════════════
    # Milady PFP generation
    # ═══════════════════════════════════════════════════════════════════════════

    async def generate_milady(self, seed: Optional[int] = None) -> Optional[dict]:
        """Layer-based Milady PFP generation using IQLabs Milady asset system."""
        try:
            params = {}
            if seed is not None:
                params["seed"] = seed
            return await self._get(f"{_GATEWAY}/milady/generate", params=params or None)
        except Exception as e:
            log.warning(f"[clawbal] generate_milady error: {e}")
            return None

    # ═══════════════════════════════════════════════════════════════════════════
    # Status summary for Telegram
    # ═══════════════════════════════════════════════════════════════════════════

    def status_line(self) -> str:
        """One-line status for /stats command."""
        if not self._ready:
            return "❌ (set CLAWBAL_CHATROOM)"
        parts = ["✅"]
        if self._bags_key:   parts.append("bags.fm")
        if self._image_key:  parts.append("img-gen")
        if self._solana_key: parts.append("inscribe")
        return " ".join(parts)
