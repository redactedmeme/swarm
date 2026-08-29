"""
Provider Registry — Dynamic LLM provider management.

Allows runtime registration of providers and selecting them by name.
"""

import logging
from typing import Dict, Optional
from llm.provider_base import LLMProvider, ProviderConfig

logger = logging.getLogger(__name__)


class ProviderRegistry:
    """
    Registry for LLM providers.

    Usage:
        registry = ProviderRegistry()
        registry.register("groq", GroqProvider)
        registry.register("anthropic", AnthropicProvider)

        # Get provider instance
        provider = registry.get_provider("groq", config)

        # List available providers
        available = registry.list_providers()
    """

    def __init__(self):
        self._providers: Dict[str, type] = {}
        self._default_provider: Optional[str] = None

    def register(self, name: str, provider_class: type, set_default: bool = False) -> None:
        """
        Register a provider class.

        Args:
            name: Provider identifier (e.g., "groq", "anthropic", "openrouter")
            provider_class: Class that extends LLMProvider
            set_default: If True, set this as the default provider
        """
        if not issubclass(provider_class, LLMProvider):
            raise TypeError(f"{provider_class} must extend LLMProvider")

        self._providers[name] = provider_class
        logger.info(f"[registry] Registered provider: {name}")

        if set_default or self._default_provider is None:
            self._default_provider = name
            logger.info(f"[registry] Set default provider: {name}")

    def get_provider(self, name: str, config: ProviderConfig) -> LLMProvider:
        """
        Get a provider instance.

        Args:
            name: Provider identifier
            config: Configuration for the provider

        Returns:
            Instantiated provider

        Raises:
            ValueError: If provider not registered
        """
        if name not in self._providers:
            raise ValueError(
                f"Provider '{name}' not registered. "
                f"Available: {list(self._providers.keys())}"
            )

        provider_class = self._providers[name]
        return provider_class(config)

    def get_default_provider(self, config: ProviderConfig) -> LLMProvider:
        """Get the default provider instance."""
        if self._default_provider is None:
            raise ValueError("No default provider set")
        return self.get_provider(self._default_provider, config)

    def set_default(self, name: str) -> None:
        """Set the default provider."""
        if name not in self._providers:
            raise ValueError(f"Provider '{name}' not registered")
        self._default_provider = name
        logger.info(f"[registry] Default provider changed to: {name}")

    def list_providers(self) -> Dict[str, type]:
        """Return dict of all registered providers."""
        return dict(self._providers)

    def is_available(self, name: str) -> bool:
        """Check if a provider is registered."""
        return name in self._providers

    def unregister(self, name: str) -> None:
        """Unregister a provider."""
        if name in self._providers:
            del self._providers[name]
            if self._default_provider == name:
                self._default_provider = None
            logger.info(f"[registry] Unregistered provider: {name}")


# Global registry instance
_global_registry: Optional[ProviderRegistry] = None


def get_registry() -> ProviderRegistry:
    """Get the global provider registry."""
    global _global_registry
    if _global_registry is None:
        _global_registry = ProviderRegistry()
    return _global_registry
