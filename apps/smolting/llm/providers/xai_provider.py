"""
xAI Provider Implementation

Stream-based Grok inference via xAI API (OpenAI-compatible).
"""

import logging
import httpx
import json
from typing import List, Dict, Any, Optional, AsyncIterator

from llm.provider_base import LLMProvider, ProviderConfig, ProviderEvent, EventType

logger = logging.getLogger(__name__)

XAI_BASE = "https://api.x.ai/v1"


class XAIProvider(LLMProvider):
    """
    xAI (Grok) LLM Provider.

    Models: grok-2-1212, grok-beta
    OpenAI-compatible API.
    """

    def __init__(self, config: ProviderConfig):
        super().__init__(config)
        self.base_url = XAI_BASE
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    async def stream_message(
        self,
        messages: List[Dict[str, str]],
        tools: Optional[List[Dict[str, Any]]] = None,
        **kwargs
    ) -> AsyncIterator[ProviderEvent]:
        """
        Stream message from xAI (Grok).
        """
        try:
            # Build request body (OpenAI format)
            request_body = {
                "model": self.model,
                "messages": messages,
                "stream": True,
                "temperature": self.config.temperature,
            }

            if self.config.max_tokens:
                request_body["max_tokens"] = self.config.max_tokens

            if tools:
                request_body["tools"] = [
                    {"type": "function", "function": t} for t in tools
                ]

            # Merge extra kwargs
            request_body.update(kwargs)

            # Stream from xAI
            async with httpx.AsyncClient(timeout=self.config.timeout) as client:
                async with client.stream(
                    "POST",
                    f"{self.base_url}/chat/completions",
                    headers=self.headers,
                    json=request_body,
                ) as response:
                    if response.status_code != 200:
                        error_text = await response.atext()
                        logger.error(f"[xai] HTTP {response.status_code}: {error_text}")
                        yield ProviderEvent(
                            type=EventType.ERROR,
                            error=f"xAI error: {response.status_code}",
                        )
                        return

                    # Process SSE stream
                    async for line in response.aiter_lines():
                        if not line or line.startswith(":"):
                            continue

                        if line.startswith("data: "):
                            data_str = line[6:]
                            if data_str == "[DONE]":
                                break

                            try:
                                data = json.loads(data_str)
                                choice = data.get("choices", [{}])[0]
                                delta = choice.get("delta", {})

                                # Text content
                                if "content" in delta:
                                    content = delta["content"]
                                    if content:
                                        yield ProviderEvent(
                                            type=EventType.TEXT_DELTA,
                                            content=content,
                                        )

                                # Tool calls
                                if "tool_calls" in delta:
                                    for tool_call in delta["tool_calls"]:
                                        yield ProviderEvent(
                                            type=EventType.TOOLCALL_DELTA,
                                            tool_id=tool_call.get("id"),
                                            tool_name=tool_call.get("function", {}).get(
                                                "name"
                                            ),
                                            tool_args=tool_call.get("function", {}).get(
                                                "arguments"
                                            ),
                                        )

                                # Usage (final message)
                                if "usage" in data:
                                    usage = data["usage"]
                                    yield ProviderEvent(
                                        type=EventType.USAGE,
                                        usage={
                                            "input_tokens": usage.get("prompt_tokens", 0),
                                            "output_tokens": usage.get(
                                                "completion_tokens", 0
                                            ),
                                        },
                                    )

                            except json.JSONDecodeError:
                                logger.warning(f"[xai] Failed to parse: {data_str}")

                    # End signal
                    yield ProviderEvent(type=EventType.TEXT_END)

        except httpx.TimeoutException:
            logger.error("[xai] Request timeout")
            yield ProviderEvent(
                type=EventType.ERROR,
                error="xAI request timeout",
            )
        except Exception as e:
            logger.error(f"[xai] Stream error: {e}")
            yield ProviderEvent(
                type=EventType.ERROR,
                error=f"xAI stream error: {str(e)}",
            )
