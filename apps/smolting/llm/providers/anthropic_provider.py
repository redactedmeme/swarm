"""
Anthropic Provider Implementation

Stream-based Claude inference via Anthropic API.
"""

import logging
from typing import List, Dict, Any, Optional, AsyncIterator
from anthropic import Anthropic as AnthropicClient
from anthropic import APIError

from llm.provider_base import LLMProvider, ProviderConfig, ProviderEvent, EventType

logger = logging.getLogger(__name__)


class AnthropicProvider(LLMProvider):
    """
    Anthropic (Claude) LLM Provider.

    Models: claude-3-5-sonnet-20241022, claude-3-opus-20250219, claude-3-haiku-20240307
    Supports extended thinking mode.
    """

    def __init__(self, config: ProviderConfig):
        super().__init__(config)
        self.client = AnthropicClient(api_key=self.api_key)

    async def stream_message(
        self,
        messages: List[Dict[str, str]],
        tools: Optional[List[Dict[str, Any]]] = None,
        thinking: Optional[bool] = False,
        **kwargs
    ) -> AsyncIterator[ProviderEvent]:
        """
        Stream message from Claude.

        Args:
            messages: Conversation history
            tools: Tool definitions (Claude supports this natively)
            thinking: Enable extended thinking mode (o1-like reasoning)
            **kwargs: Extra parameters (e.g., budget_tokens for thinking)
        """
        try:
            # Build request params
            request_params = {
                "model": self.model,
                "messages": messages,
                "max_tokens": self.config.max_tokens or 4096,
                "temperature": self.config.temperature,
            }

            # Add thinking if requested
            if thinking:
                request_params["thinking"] = {
                    "type": "enabled",
                    "budget_tokens": kwargs.get("budget_tokens", 10000),
                }

            # Add tools if provided
            if tools:
                request_params["tools"] = tools

            # Stream from Claude
            with self.client.messages.stream(**request_params) as stream:
                thinking_buffer = ""
                text_buffer = ""
                tool_id = None
                tool_name = None
                tool_args = ""

                for event in stream:
                    event_type = getattr(event, "type", None)

                    # Thinking blocks
                    if event_type == "content_block_start":
                        block = getattr(event, "content_block", None)
                        if block and getattr(block, "type", None) == "thinking":
                            yield ProviderEvent(type=EventType.THINKING_START)

                    elif event_type == "content_block_delta":
                        delta = getattr(event, "delta", None)
                        if delta:
                            if hasattr(delta, "thinking"):
                                thinking_buffer += delta.thinking
                                yield ProviderEvent(
                                    type=EventType.THINKING_DELTA,
                                    content=delta.thinking,
                                )
                            elif hasattr(delta, "text"):
                                text_buffer += delta.text
                                yield ProviderEvent(
                                    type=EventType.TEXT_DELTA,
                                    content=delta.text,
                                )
                            elif hasattr(delta, "input"):
                                tool_args += delta.input
                                yield ProviderEvent(
                                    type=EventType.TOOLCALL_DELTA,
                                    tool_id=tool_id,
                                    tool_name=tool_name,
                                    tool_args=delta.input,
                                )

                    elif event_type == "content_block_stop":
                        block = getattr(event, "content_block", None)
                        if block and getattr(block, "type", None) == "thinking":
                            yield ProviderEvent(type=EventType.THINKING_END)

                    # Tool calls (Claude uses tool_use content blocks)
                    elif event_type == "content_block_start":
                        block = getattr(event, "content_block", None)
                        if block and getattr(block, "type", None) == "tool_use":
                            tool_id = getattr(block, "id", None)
                            tool_name = getattr(block, "name", None)
                            tool_args = ""
                            yield ProviderEvent(
                                type=EventType.TOOLCALL_START,
                                tool_id=tool_id,
                                tool_name=tool_name,
                            )

                # Emit final events
                if text_buffer:
                    yield ProviderEvent(type=EventType.TEXT_END, content=None)

                if tool_args:
                    yield ProviderEvent(
                        type=EventType.TOOLCALL_END,
                        tool_id=tool_id,
                        tool_name=tool_name,
                        tool_args=tool_args,
                    )

                # Usage
                if hasattr(stream, "get_final_message"):
                    msg = stream.get_final_message()
                    if hasattr(msg, "usage"):
                        yield ProviderEvent(
                            type=EventType.USAGE,
                            usage={
                                "input_tokens": msg.usage.input_tokens,
                                "output_tokens": msg.usage.output_tokens,
                            },
                        )

        except APIError as e:
            logger.error(f"[anthropic] API error: {e}")
            yield ProviderEvent(
                type=EventType.ERROR,
                error=f"Anthropic API error: {str(e)}",
            )
        except Exception as e:
            logger.error(f"[anthropic] Stream error: {e}")
            yield ProviderEvent(
                type=EventType.ERROR,
                error=f"Anthropic stream error: {str(e)}",
            )
