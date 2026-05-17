# smolting-telegram-bot/llm/cloud_client.py
import os
import asyncio
import aiohttp
import json
from typing import Optional, Dict, Any

# Model used exclusively for /alpha — fast grok-4-1 inference via Venice API
ALPHA_MODEL = os.getenv("ALPHA_XAI_MODEL", "grok-4-1-fast")
ALPHA_BASE  = os.getenv("ALPHA_API_BASE", "https://api.venice.ai/api/v1")


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
        }
        return urls.get(self.provider, "")
    
    async def chat_completion(self, messages: list, model: str = None, max_tokens: int = None) -> str:
        """Chat completion with cloud LLM"""
        max_tokens = max_tokens or self._default_max_tokens
        # Proxy speaks OpenAI-compatible for all providers
        if os.getenv("PROXY_URL") or self.provider in ("openai", "xai", "groq", "together"):
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
        
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.base_url}/chat/completions",
                json=payload,
                headers=headers
            ) as response:
                result = await response.json()
                if "choices" not in result:
                    raise ValueError(f"API error from {self.provider}: {result.get('error', result)}")
                return result["choices"][0]["message"]["content"]

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
                return result["content"][0]["text"]
    
    async def chat_completion_with_fallback(self, messages: list, max_tokens: int = None) -> str:
        """
        Try providers in order: current → xai → anthropic → groq.
        Skips providers with no API key. Raises if all fail.
        """
        import logging
        _log = logging.getLogger(__name__)

        # Build fallback chain starting from current provider
        _chain = [self.provider] + [p for p in ("xai", "anthropic", "groq") if p != self.provider]

        last_err = None
        for provider in _chain:
            key = {
                "openai": os.getenv("OPENAI_API_KEY"),
                "anthropic": os.getenv("ANTHROPIC_API_KEY"),
                "together": os.getenv("TOGETHER_API_KEY"),
                "xai": os.getenv("XAI_API_KEY"),
                "groq": os.getenv("GROQ_API_KEY"),
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
        valid = ("openai", "anthropic", "together", "xai", "groq")
        if provider not in valid:
            return False
        self.provider = provider
        self.api_key = self._get_api_key()
        self.base_url = self._get_base_url()
        return True

    def current_model(self) -> str:
        """Return the default model name for the active provider."""
        defaults = {
            "xai":       os.getenv("XAI_MODEL", "grok-4-1-fast"),
            "groq":      os.getenv("GROQ_MODEL", "llama-3.1-8b-instant"),
            "together":  "Qwen/Qwen2.5-7B-Instruct-Turbo",
            "openai":    "gpt-3.5-turbo",
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
