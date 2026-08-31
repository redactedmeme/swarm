"""
LLM Client — Groq with 3-tier fallback.

  1. openai/gpt-oss-20b  (cheapest, fine for factual work)
  2. llama-3.3-70b-versatile  (stronger reasoning)
  3. llama-3.1-8b-instant  (fast fallback)
"""

import logging
import aiohttp
from config import GROQ_API_KEY, GROQ_BASE_URL, GROQ_MODELS

try:
    from config import LLM_VIA_PROXY
except ImportError:  # pragma: no cover
    LLM_VIA_PROXY = False

logger = logging.getLogger(__name__)


async def call(
    system: str,
    user: str,
    max_tokens: int = 400,
    temperature: float = 0.3,
    prefer_strong: bool = False,
) -> tuple[str, str]:
    """
    Call Groq LLM with fallback chain.
    Returns (response_text, model_used).
    If prefer_strong=True, starts from 70b instead of 20b.
    """
    if not GROQ_API_KEY:
        raise RuntimeError("GROQ_API_KEY / PROXY_TOKEN not set")

    if LLM_VIA_PROXY:
        # let the proxy's cost-first auto-router choose; it maps to real providers
        models = ["auto"]
    else:
        models = GROQ_MODELS if not prefer_strong else GROQ_MODELS[1:]
    payload_base = {
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json",
    }

    for model in models:
        payload = {**payload_base, "model": model}
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{GROQ_BASE_URL}/chat/completions",
                    json=payload,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=25),
                ) as resp:
                    data = await resp.json()
                    if "choices" not in data:
                        raise ValueError(f"groq error: {data.get('error', data)}")
                    return data["choices"][0]["message"]["content"], model
        except Exception as e:
            logger.warning(f"[llm_client] {model} failed: {e}")

    raise RuntimeError("all Groq models failed")
