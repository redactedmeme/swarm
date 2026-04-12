"""
Unified LLM Provider Interface (pi-mono pattern)

All providers implement this interface for consistent streaming behavior.
Messages are streamed as events: text_delta, toolcall_start, toolcall_delta, etc.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import AsyncIterator, Optional, Any, Dict, List


class EventType(Enum):
    """Standard event types emitted by all providers."""
    TEXT_START = "text_start"
    TEXT_DELTA = "text_delta"
    TEXT_END = "text_end"

    THINKING_START = "thinking_start"
    THINKING_DELTA = "thinking_delta"
    THINKING_END = "thinking_end"

    TOOLCALL_START = "toolcall_start"
    TOOLCALL_DELTA = "toolcall_delta"
    TOOLCALL_END = "toolcall_end"

    USAGE = "usage"
    ERROR = "error"


@dataclass
class ProviderEvent:
    """Standard event structure emitted by all providers."""
    type: EventType
    content: Optional[str] = None
    tool_id: Optional[str] = None
    tool_name: Optional[str] = None
    tool_args: Optional[str] = None
    usage: Optional[Dict[str, int]] = None
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict for serialization."""
        return {
            "type": self.type.value,
            "content": self.content,
            "tool_id": self.tool_id,
            "tool_name": self.tool_name,
            "tool_args": self.tool_args,
            "usage": self.usage,
            "error": self.error,
        }


@dataclass
class ProviderConfig:
    """Configuration shared across all providers."""
    api_key: str
    model: str
    max_tokens: Optional[int] = None
    temperature: float = 0.7
    timeout: int = 60


class LLMProvider(ABC):
    """
    Abstract base class for all LLM providers.

    All providers must implement stream_message() which returns an async iterator
    of ProviderEvent objects. This allows consistent handling across OpenAI, Anthropic,
    Groq, xAI, OpenRouter, etc.
    """

    def __init__(self, config: ProviderConfig):
        self.config = config
        self.model = config.model
        self.api_key = config.api_key

    @abstractmethod
    async def stream_message(
        self,
        messages: List[Dict[str, str]],
        tools: Optional[List[Dict[str, Any]]] = None,
        **kwargs
    ) -> AsyncIterator[ProviderEvent]:
        """
        Stream a message from the LLM provider.

        Args:
            messages: Conversation history in format [{"role": "user|assistant", "content": "..."}]
            tools: Optional tool definitions
            **kwargs: Provider-specific parameters

        Yields:
            ProviderEvent objects with streaming content
        """
        pass

    async def chat_completion(
        self,
        messages: List[Dict[str, str]],
        tools: Optional[List[Dict[str, Any]]] = None,
        **kwargs
    ) -> str:
        """
        Non-streaming chat completion. Collects all text from stream.

        Args:
            messages: Conversation history
            tools: Optional tool definitions
            **kwargs: Provider-specific parameters

        Returns:
            Complete text response
        """
        text = ""
        async for event in self.stream_message(messages, tools, **kwargs):
            if event.type == EventType.TEXT_DELTA:
                text += event.content or ""
        return text

    @property
    def provider_name(self) -> str:
        """Return the name of this provider."""
        return self.__class__.__name__
