"""
Cloud LLM Client — Unified multi-provider wrapper (backward-compatible).

Replaces the old CloudLLMClient with the new provider-based system.
"""

import os
import logging
from typing import List, Dict, Any, Optional

from llm.provider_base import ProviderConfig, ProviderEvent
from llm.provider_registry import get_registry
from llm.providers import GroqProvider, AnthropicProvider, OpenRouterProvider, XAIProvider

logger = logging.getLogger(__name__)


# Register all providers on module load
def _register_providers():
    """Register all available providers."""
    registry = get_registry()

    # Groq
    if os.getenv("GROQ_API_KEY"):
        registry.register("groq", GroqProvider, set_default=True)

    # Anthropic
    if os.getenv("ANTHROPIC_API_KEY"):
        registry.register("anthropic", AnthropicProvider)

    # OpenRouter
    if os.getenv("OPENROUTER_API_KEY"):
        registry.register("openrouter", OpenRouterProvider)

    # xAI
    if os.getenv("XAI_API_KEY"):
        registry.register("xai", XAIProvider)


_register_providers()


class CloudLLMClient:
    """
    Unified LLM client supporting multiple providers.

    Usage (backward-compatible):
        client = CloudLLMClient(provider="anthropic")
        response = await client.chat_completion([...])

        # Or use provider-specific config:
        client = CloudLLMClient(provider="openrouter", model="claude-3.5-sonnet")
        async for event in client.stream_message([...]):
            print(event.content)
    """

    def __init__(
        self,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: float = 0.7,
    ):
        """
        Initialize client with provider.

        Args:
            provider: Provider name ("groq", "anthropic", "openrouter", "xai").
                     If None, uses default from env or registry.
            model: Model name. If None, uses provider's default.
            max_tokens: Max output tokens
            temperature: Sampling temperature
        """
        self.registry = get_registry()

        # Determine provider
        if provider is None:
            provider = os.getenv("LLM_PROVIDER", "groq").lower()

        self.provider_name = provider

        if not self.registry.is_available(provider):
            raise ValueError(
                f"Provider '{provider}' not registered. "
                f"Available: {list(self.registry.list_providers().keys())}"
            )

        # Get API key
        api_key = self._get_api_key(provider)
        if not api_key:
            raise ValueError(f"API key for provider '{provider}' not found")

        # Determine model
        if model is None:
            model = self._get_default_model(provider)

        # Create config
        self.config = ProviderConfig(
            api_key=api_key,
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
        )

        # Initialize provider
        self.provider = self.registry.get_provider(provider, self.config)

    def _get_api_key(self, provider: str) -> Optional[str]:
        """Get API key for provider."""
        keys = {
            "groq": "GROQ_API_KEY",
            "anthropic": "ANTHROPIC_API_KEY",
            "openrouter": "OPENROUTER_API_KEY",
            "xai": "XAI_API_KEY",
        }
        key_var = keys.get(provider)
        return os.getenv(key_var, "").strip() if key_var else None

    def _get_default_model(self, provider: str) -> str:
        """Get default model for provider."""
        defaults = {
            "groq": "llama-3.1-8b-instant",
            "anthropic": "claude-3-5-sonnet-20241022",
            "openrouter": "claude-3-5-sonnet-20241022",
            "xai": "grok-2-1212",
        }
        return defaults.get(provider, "gpt-4")

    async def stream_message(
        self,
        messages: List[Dict[str, str]],
        tools: Optional[List[Dict[str, Any]]] = None,
        **kwargs
    ):
        """
        Stream message from provider.

        Yields ProviderEvent objects.
        """
        async for event in self.provider.stream_message(messages, tools, **kwargs):
            yield event

    async def chat_completion(
        self,
        messages: List[Dict[str, str]],
        tools: Optional[List[Dict[str, Any]]] = None,
        **kwargs
    ) -> str:
        """
        Non-streaming chat completion.

        Returns complete text response.
        """
        text = ""
        async for event in self.provider.stream_message(messages, tools, **kwargs):
            if event.type.value == "text_delta":
                text += event.content or ""
        return text

    def __repr__(self) -> str:
        return f"CloudLLMClient({self.provider_name}/{self.config.model})"
