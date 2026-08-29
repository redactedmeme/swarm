# smolting-telegram-bot/llm/cloud_client.py
import os
import asyncio
import aiohttp
import json
import re as _re
from typing import Optional, Dict, Any

# Model used exclusively for /alpha — fast grok-4-1 inference via Venice API
ALPHA_MODEL = os.getenv("ALPHA_XAI_MODEL", "grok-4-1-fast")
ALPHA_BASE  = os.getenv("ALPHA_API_BASE", "https://api.venice.ai/api/v1")


# ── LLM reasoning-leak scrubbing ──────────────────────────────────────────────
# Reasoning models (deepseek-v4-flash via the proxy auto-router) sometimes narrate
# their planning into `content` ("Here's a thinking process:\n1. Analyze user
# input...") instead of just answering. We disable reasoning at the source; this is
# the conservative backstop. Kept phrase-based (NOT structural) so it never mangles
# a legit smolting reply that happens to use a numbered list or bullets.
_THINK_RE = _re.compile(r"<(think|thinking|reasoning)>.*?</\1>", _re.DOTALL | _re.IGNORECASE)
_REASONING_SIGNALS = (
    "here's a thinking process", "here is a thinking process", "here's my thinking process",
    "let me think through", "let me work through", "let me analyze",
    "the user wants me to", "the user is asking", "the user's request", "user's message",
    "analyze user input", "analyze the user", "analyze the request", "analyze user request",
)


def looks_like_reasoning(text: str) -> bool:
    """True if `text` reads as leaked chain-of-thought rather than a real message.
    Phrase-based only — deliberately conservative to avoid false positives."""
    if not text:
        return False
    low = text.lower()
    return any(sig in low for sig in _REASONING_SIGNALS)


def strip_reasoning(text: str) -> str:
    """Scrub leaked chain-of-thought. Drops <think>/<reasoning> blocks, then — if
    the remainder still reads as reasoning — salvages a trailing genuine message by
    dropping leading reasoning paragraphs. Returns "" if nothing clean survives so
    the fallback chain retries rather than posting CoT. Never raises."""
    if not text:
        return text
    try:
        cleaned = _THINK_RE.sub("", text).strip()
        if not looks_like_reasoning(cleaned):
            return cleaned
        parts = _re.split(r"\n\s*\n", cleaned)
        while parts and looks_like_reasoning(parts[0]):
            parts = parts[1:]
        tail = "\n\n".join(parts).strip()
        return tail if (tail and not looks_like_reasoning(tail)) else ""
    except Exception:
        return text


class CloudLLMClient:
    """Cloud LLM client supporting multiple providers (OpenAI, Anthropic, Together, xAI/Grok)"""

    def __init__(self, provider: str = None, max_tokens: int = None, temperature: float = 0.7):
        self.provider = (provider or os.getenv("LLM_PROVIDER", "groq")).lower()
        if self.provider == "grok":
            self.provider = "xai"
        self._default_max_tokens = max_tokens
        self._default_temperature = temperature
        self.api_key = self._get_api_key()
        self.base_url = self._get_base_url()
        self._xai_key = os.getenv("XAI_API_KEY", "")

    def _get_api_key(self) -> str:
        """Get API key — proxy token takes precedence if PROXY_URL is set."""
        if os.getenv("PROXY_URL"):
            return os.getenv("PROXY_TOKEN", "")
        keys = {
            "openai": os.getenv("OPENAI_API_KEY"),
            "anthropic": os.getenv("ANTHROPIC_API_KEY"),
            "together": os.getenv("TOGETHER_API_KEY"),
            "xai": os.getenv("XAI_API_KEY"),
            "groq": os.getenv("GROQ_API_KEY"),
            "openrouter": os.getenv("OPENROUTER_API_KEY"),
        }
        return keys.get(self.provider, "") or ""

    def _get_base_url(self) -> str:
        """Get base URL for provider — proxy takes precedence if PROXY_URL is set."""
        proxy = os.getenv("PROXY_URL", "").rstrip("/")
        if proxy:
            return f"{proxy}/v1"
        urls = {
            "openai": "https://api.openai.com/v1",
            "anthropic": "https://api.anthropic.com/v1",
            "together": "https://api.together.xyz/v1",
            "xai": "https://api.x.ai/v1",
            "groq": "https://api.groq.com/openai/v1",
            "openrouter": "https://openrouter.ai/api/v1",
        }
        return urls.get(self.provider, "")
    
    async def chat_completion(self, messages: list, model: str = None, max_tokens: int = None) -> str:
        """Chat completion with cloud LLM"""
        max_tokens = max_tokens or self._default_max_tokens
        # Proxy speaks OpenAI-compatible for all providers
        if os.getenv("PROXY_URL") or self.provider in ("openai", "xai", "groq", "together", "openrouter"):
            return await self._openai_completion(messages, model, max_tokens=max_tokens)
        elif self.provider == "anthropic":
            return await self._anthropic_completion(messages, model, max_tokens=max_tokens)
        else:
            raise ValueError(f"Unsupported provider: {self.provider}. Set LLM_PROVIDER to openai, xai, groq, anthropic, or together.")
    
    async def _openai_completion(self, messages: list, model: str = None, max_tokens: int = None) -> str:
        """OpenAI GPT completion (also used for xAI/Grok OpenAI-compatible API)"""
        if self.provider == "xai":
            model = model or os.getenv("XAI_MODEL", "grok-4-1-fast")
        elif self.provider == "groq":
            model = model or os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")
        elif self.provider == "together":
            model = model or "Qwen/Qwen2.5-7B-Instruct-Turbo"
        elif self.provider == "openrouter":
            model = model or os.getenv("OPENROUTER_MODEL", "deepseek/deepseek-v4-flash")
        else:
            model = model or "gpt-3.5-turbo"

        payload = {
            "model": model,
            "messages": messages,
            "temperature": 0.7,
            "max_tokens": max_tokens or 1000,
        }

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        if self.provider == "openrouter" or os.getenv("PROXY_URL"):
            # deepseek-v4-flash is a reasoning model — disable reasoning so `content`
            # holds the answer instead of chain-of-thought. Sent for the proxy path
            # too: the proxy strips it for providers that reject it (Groq/xAI/OpenAI/
            # Venice), so relying on the proxy's conditional central injection was
            # leaking CoT. strip_reasoning() is the backstop.
            payload["reasoning"] = {"enabled": False}
        if self.provider == "openrouter":
            headers["HTTP-Referer"] = "https://redacted.ai"
            headers["X-Title"] = "REDACTED Swarm"

        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.base_url}/chat/completions",
                json=payload,
                headers=headers
            ) as response:
                result = await response.json()
                if "choices" not in result:
                    raise ValueError(f"API error from {self.provider}: {result.get('error', result)}")
                return strip_reasoning(result["choices"][0]["message"]["content"])

    async def _anthropic_completion(self, messages: list, model: str = None, max_tokens: int = None) -> str:
        """Anthropic Claude completion"""
        model = model or "claude-3-haiku-20240307"
        
        # Convert messages to Claude format
        system_msg = ""
        user_messages = []
        
        for msg in messages:
            if msg["role"] == "system":
                system_msg = msg["content"]
            elif msg["role"] == "user":
                user_messages.append({"role": "user", "content": msg["content"]})
            elif msg["role"] == "assistant":
                user_messages.append({"role": "assistant", "content": msg["content"]})
        
        payload = {
            "model": model,
            "max_tokens": max_tokens or 1000,
            "system": system_msg,
            "messages": user_messages,
        }
        
        headers = {
            "x-api-key": self.api_key,
            "Content-Type": "application/json",
            "anthropic-version": "2023-06-01"
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.base_url}/messages",
                json=payload,
                headers=headers
            ) as response:
                result = await response.json()
                if "content" not in result:
                    raise ValueError(f"Anthropic API error: {result.get('error', result)}")
                return strip_reasoning(result["content"][0]["text"])
    
    async def chat_completion_with_fallback(self, messages: list, max_tokens: int = None) -> str:
        """
        Try providers in order: current → xai → anthropic → groq.
        Skips providers with no API key. Raises if all fail.
        """
        import logging
        _log = logging.getLogger(__name__)

        # Build fallback chain starting from current provider
        _chain = [self.provider] + [p for p in ("openrouter", "groq", "xai", "anthropic") if p != self.provider]

        last_err = None
        for provider in _chain:
            key = {
                "openai": os.getenv("OPENAI_API_KEY"),
                "anthropic": os.getenv("ANTHROPIC_API_KEY"),
                "together": os.getenv("TOGETHER_API_KEY"),
                "xai": os.getenv("XAI_API_KEY"),
                "groq": os.getenv("GROQ_API_KEY"),
                "openrouter": os.getenv("OPENROUTER_API_KEY"),
            }.get(provider, "")
            if not key:
                continue
            try:
                tmp = CloudLLMClient(provider=provider, max_tokens=max_tokens)
                result = await tmp.chat_completion(messages, max_tokens=max_tokens)
                if result:
                    if provider != self.provider:
                        _log.info(f"[llm] fallback succeeded via {provider}")
                    return result
            except Exception as e:
                _log.warning(f"[llm] {provider} failed: {e}")
                last_err = e
        raise RuntimeError(f"all LLM providers failed — last error: {last_err}")

    def switch_provider(self, provider: str) -> bool:
        """
        Hot-swap LLM provider at runtime (session-only, resets on redeploy).
        Returns True if the provider is valid and has a key set.
        """
        provider = provider.lower()
        if provider == "grok":
            provider = "xai"
        valid = ("openai", "anthropic", "together", "xai", "groq", "openrouter")
        if provider not in valid:
            return False
        self.provider = provider
        self.api_key = self._get_api_key()
        self.base_url = self._get_base_url()
        return True

    def current_model(self) -> str:
        """Return the default model name for the active provider."""
        defaults = {
            "xai":        os.getenv("XAI_MODEL", "grok-4-1-fast"),
            "groq":       os.getenv("GROQ_MODEL", "llama-3.1-8b-instant"),
            "together":   "Qwen/Qwen2.5-7B-Instruct-Turbo",
            "openrouter": os.getenv("OPENROUTER_MODEL", "deepseek/deepseek-v4-flash"),
            "openai":     "gpt-3.5-turbo",
            "anthropic": "claude-3-haiku-20240307",
        }
        return defaults.get(self.provider, "unknown")

    async def alpha_completion(self, messages: list, max_tokens: int = 1200) -> str:
        """Always uses grok-4-1-fast via Venice API regardless of LLM_PROVIDER — dedicated for /alpha."""
        alpha_key = os.getenv("VENICE_API_KEY", "") or self._xai_key
        alpha_base = ALPHA_BASE
        if not alpha_key:
            return await self.chat_completion(messages, max_tokens=max_tokens)
        payload = {
            "model": ALPHA_MODEL,
            "messages": messages,
            "temperature": 0.7,
            "max_tokens": max_tokens,
        }
        if "venice" in alpha_base:
            payload["venice_parameters"] = {"include_venice_system_prompt": False}
        headers = {
            "Authorization": f"Bearer {alpha_key}",
            "Content-Type": "application/json",
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{alpha_base}/chat/completions",
                json=payload,
                headers=headers,
            ) as response:
                result = await response.json()
                if "choices" not in result:
                    raise ValueError(f"Alpha LLM error: {result.get('error', result)}")
                return result["choices"][0]["message"]["content"]

    async def _together_completion(self, messages: list, model: str = None) -> str:
        """Together AI completion (mix of open source models)"""
        model = model or "Qwen/Qwen2.5-7B-Instruct-Turbo"
        
        payload = {
            "model": model,
            "messages": messages,
            "temperature": 0.7,
            "max_tokens": 1000
        }
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.base_url}/chat/completions",
                json=payload,
                headers=headers
            ) as response:
                result = await response.json()
                return result["choices"][0]["message"]["content"]
