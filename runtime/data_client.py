"""
Data Client — async HTTP client for the redacted-chan-bot data proxy.

All calls degrade gracefully: if the proxy is unreachable, methods
return empty defaults so tasks can still run (with less context).
"""

import logging
import aiohttp
from config import DATA_PROXY_URL, DATA_PROXY_TOKEN

logger = logging.getLogger(__name__)

_TIMEOUT = aiohttp.ClientTimeout(total=10)


async def _get(path: str, params: dict = None) -> dict:
    if not DATA_PROXY_URL:
        return {}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{DATA_PROXY_URL}{path}",
                params=params or {},
                headers={"Authorization": f"Bearer {DATA_PROXY_TOKEN}"},
                timeout=_TIMEOUT,
            ) as resp:
                if resp.status != 200:
                    logger.warning(f"[data_client] {path} returned {resp.status}")
                    return {}
                return await resp.json()
    except Exception as e:
        logger.warning(f"[data_client] {path} failed: {e}")
        return {}


async def get_vault(query: str, n: int = 5) -> str:
    data = await _get("/proxy/vault", {"query": query, "n": str(n)})
    return data.get("text", "")


async def get_vault_entries(category: str = None, n: int = 10) -> list[dict]:
    params = {"n": str(n)}
    if category:
        params["category"] = category
    data = await _get("/proxy/vault/entries", params)
    return data.get("entries", [])


async def get_memory(query: str, n: int = 8) -> list[str]:
    data = await _get("/proxy/memory", {"query": query, "n": str(n)})
    return data.get("excerpts", [])


async def get_vector(query: str, n: int = 5) -> list[dict]:
    data = await _get("/proxy/vector", {"query": query, "n": str(n)})
    return data.get("results", [])


async def get_vector_facts(query: str, n: int = 10) -> list[str]:
    data = await _get("/proxy/vector/facts", {"query": query, "n": str(n)})
    return data.get("facts", [])


async def get_facts(limit: int = 50) -> list[dict]:
    data = await _get("/proxy/facts", {"limit": str(limit)})
    return data.get("facts", [])


async def get_heatmap(n: int = 50) -> list[dict]:
    data = await _get("/proxy/heatmap", {"n": str(n)})
    return data.get("frames", [])


async def get_mood() -> dict:
    data = await _get("/proxy/mood")
    return data if data else {"mood": "supportive", "modifier": ""}


async def get_anticipation() -> dict:
    data = await _get("/proxy/anticipation")
    return data if data else {"state": "present", "hours_since": 0}


async def get_history(user_id: str, n: int = 30) -> list[dict]:
    data = await _get("/proxy/history", {"user_id": user_id, "n": str(n)})
    return data.get("messages", [])
