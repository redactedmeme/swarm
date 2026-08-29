# smolting-telegram-bot/swarm_relay.py
"""
SwarmRelay: bridges Telegram bot commands to the TS swarm-core service.
Calls POST /command and GET /state on the x402.redacted.ai TS server.
Set TS_SERVICE_URL env var (default: http://localhost:3001).
"""

import os
import logging
import aiohttp
from typing import Optional

logger = logging.getLogger(__name__)

# Known agents registered in the TS swarm core
KNOWN_AGENTS = {
    "smolting", "redactedbuilder", "redactedgovimprover",
    "redactedchan", "mandalaasettler",
}

AGENT_ALIASES = {
    "builder": "RedactedBuilder",
    "gov": "RedactedGovImprover",
    "govimprover": "RedactedGovImprover",
    "chan": "RedactedChan",
    "mandala": "MandalaSettler",
    "settler": "MandalaSettler",
    "smolting": "smolting",
}


class SwarmRelay:
    """HTTP client for the TS swarm-core service."""

    def __init__(self):
        self.base_url = os.getenv("TS_SERVICE_URL", "http://localhost:3001").rstrip("/")
        self.timeout = aiohttp.ClientTimeout(total=10)

    async def send_command(self, cmd: str) -> Optional[str]:
        """POST a command string to the swarm core. Returns output string or None on error."""
        try:
            async with aiohttp.ClientSession(timeout=self.timeout) as session:
                async with session.post(
                    f"{self.base_url}/command",
                    json={"cmd": cmd},
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return data.get("output", "")
                    else:
                        text = await resp.text()
                        logger.error(f"SwarmRelay command error {resp.status}: {text}")
                        return None
        except aiohttp.ClientConnectorError:
            logger.warning("SwarmRelay: TS service unreachable")
            return None
        except Exception as e:
            logger.error(f"SwarmRelay error: {e}")
            return None

    async def get_state(self) -> Optional[dict]:
        """GET /state from the swarm core."""
        try:
            async with aiohttp.ClientSession(timeout=self.timeout) as session:
                async with session.get(f"{self.base_url}/state") as resp:
                    if resp.status == 200:
                        return await resp.json()
                    else:
                        logger.error(f"SwarmRelay state error {resp.status}")
                        return None
        except aiohttp.ClientConnectorError:
            logger.warning("SwarmRelay: TS service unreachable")
            return None
        except Exception as e:
            logger.error(f"SwarmRelay state error: {e}")
            return None

    async def health(self) -> bool:
        """Check if TS service is reachable."""
        try:
            async with aiohttp.ClientSession(timeout=self.timeout) as session:
                async with session.get(f"{self.base_url}/health") as resp:
                    return resp.status == 200
        except Exception:
            return False

    def resolve_agent(self, raw: str) -> str:
        """Resolve a user-supplied agent name to the canonical TS key."""
        return AGENT_ALIASES.get(raw.lower(), raw)

    def format_state(self, state: dict) -> str:
        """Format GET /state response for Telegram."""
        agents = state.get("agents", {})
        events = state.get("events", [])
        curvature = state.get("curvature", "?")
        ts = state.get("timestamp", "")[:19]

        active = [a["name"] for a in agents.values() if a.get("status") == "active"]
        idle = [a["name"] for a in agents.values() if a.get("status") != "active"]

        lines = [
            "🌀 SWARM STATE",
            f"Timestamp: {ts}",
            f"Curvature: {curvature}",
            "",
            f"🟢 Active ({len(active)}): {', '.join(active) if active else 'none'}",
            f"⚪ Idle ({len(idle)}):   {', '.join(idle) if idle else 'none'}",
        ]
        if events:
            lines += ["", "📋 Recent events:"]
            for evt in events[-5:]:
                lines.append(f"  • {evt}")
        return "\n".join(lines)
