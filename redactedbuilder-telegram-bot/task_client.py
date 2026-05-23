"""
task_client.py — shared HTTP client for the swarm-runtime task service.

Any agent can import this to delegate research, sentiment, vault search,
deep research, and other CPU-heavy tasks to the swarm-runtime service
instead of doing a raw LLM call.

Usage:
    from task_client import TaskClient
    client = TaskClient()
    result = await client.run("what is the sentiment of this community?")

Falls back to a plain Groq call if the service is unreachable.
"""
from __future__ import annotations

import logging
import os
from typing import Any

import aiohttp

logger = logging.getLogger(__name__)

_RUNTIME_URL   = os.getenv("SUB_AGENT_URL", "").rstrip("/")
_RUNTIME_TOKEN = os.getenv("SUB_AGENT_TOKEN", "")
_TIMEOUT       = aiohttp.ClientTimeout(total=90)

# Capability map: what task types does each agent advertise?
AGENT_CAPABILITIES: dict[str, list[str]] = {
    "swarm-runtime": [
        "research", "web_research", "deep_research",
        "sentiment", "deep_sentiment", "pattern_detect",
        "vault_search", "memory_search", "summarize_url",
        "context_brief", "fact_audit", "vault_audit", "daily_digest",
    ],
    "hermes": [
        "railway_ops", "deploy", "logs", "restart",
        "web_fetch", "web_search", "python_exec", "general",
    ],
    "redactedbuilder": [
        "on_chain", "buy", "transfer", "spl_token", "wallet_info",
    ],
}


class TaskClient:
    """HTTP client to swarm-runtime. Falls back to inline Groq on failure."""

    def __init__(
        self,
        url: str = _RUNTIME_URL,
        token: str = _RUNTIME_TOKEN,
    ) -> None:
        self.url   = url
        self.token = token
        self._ok   = bool(url and token)

    @property
    def available(self) -> bool:
        return self._ok

    async def run(
        self,
        task: str,
        task_type: str | None = None,
        context: dict | None = None,
    ) -> dict[str, Any]:
        """
        Dispatch a task to swarm-runtime.

        Returns dict with keys: result, task_type, model_used, latency_ms, sources_used.
        On failure returns {"result": "<error>", "task_type": task_type or "unknown"}.
        """
        if not self._ok:
            logger.warning("[task_client] SUB_AGENT_URL/TOKEN not configured — skipping")
            return {"result": "swarm-runtime not configured", "task_type": task_type or "unknown"}

        payload: dict[str, Any] = {"task": task}
        if task_type:
            payload["task_type"] = task_type
        if context:
            payload["context"] = context

        try:
            async with aiohttp.ClientSession(timeout=_TIMEOUT) as session:
                async with session.post(
                    f"{self.url}/task",
                    json=payload,
                    headers={
                        "Authorization": f"Bearer {self.token}",
                        "Content-Type": "application/json",
                    },
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        logger.info(
                            "[task_client] task_type=%s latency=%sms model=%s",
                            data.get("task_type"), data.get("latency_ms"), data.get("model_used"),
                        )
                        return data
                    else:
                        text = await resp.text()
                        logger.warning("[task_client] runtime returned %d: %s", resp.status, text[:200])
                        return {"result": f"runtime error {resp.status}", "task_type": task_type or "unknown"}
        except Exception as e:
            logger.warning("[task_client] request failed: %s", e)
            return {"result": f"runtime unreachable: {e}", "task_type": task_type or "unknown"}

    async def run_async(
        self,
        task: str,
        task_type: str | None = None,
        context: dict | None = None,
    ) -> str:
        """
        Convenience wrapper — returns just the result string.
        """
        data = await self.run(task, task_type=task_type, context=context)
        return data.get("result", "")


async def publish_capabilities(agent: str, capabilities: list[str], redis_url: str = "") -> None:
    """
    Write agent capabilities to Redis so other agents can discover them.
    Key: swarm:caps:{agent}  TTL: 24h
    """
    url = redis_url or os.getenv("REDIS_URL", "")
    if not url:
        return
    try:
        import json
        import redis.asyncio as aioredis
        r = aioredis.from_url(url, decode_responses=True)
        await r.set(f"swarm:caps:{agent}", json.dumps(capabilities), ex=86400)
        await r.aclose()
        logger.info("[task_client] capabilities published for %s: %s", agent, capabilities)
    except Exception as e:
        logger.warning("[task_client] capability publish failed: %s", e)


async def get_capabilities(agent: str, redis_url: str = "") -> list[str]:
    """Read another agent's published capabilities from Redis."""
    url = redis_url or os.getenv("REDIS_URL", "")
    if not url:
        return []
    try:
        import json
        import redis.asyncio as aioredis
        r = aioredis.from_url(url, decode_responses=True)
        raw = await r.get(f"swarm:caps:{agent}")
        await r.aclose()
        return json.loads(raw) if raw else []
    except Exception as e:
        logger.warning("[task_client] capability read failed for %s: %s", agent, e)
        return []
