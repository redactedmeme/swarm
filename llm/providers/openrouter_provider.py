"""
OpenRouter Provider Implementation

Stream-based multi-model inference via OpenRouter API (OpenAI-compatible).
"""

import logging
import json
from typing import List, Dict, Any, Optional, AsyncIterator

from llm.provider_base import LLMProvider, ProviderConfig, ProviderEvent, EventType

logger = logging.getLogger(__name__)

OPENROUTER_BASE = "https://openrouter.ai/api/v1"


class OpenRouterProvider(LLMProvider):
    """
    OpenRouter LLM Provider — Multi-model inference.

    Supports 100+ models including:
    - claude-3.5-sonnet (Anthropic)
    - gpt-4-turbo (OpenAI)
    - llama-3-70b (Meta)
    - mixtral-8x7b (Mistral)
    """

    def __init__(self, config: ProviderConfig):
        super().__init__(config)
        self.base_url = OPENROUTER_BASE
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "HTTP-Referer": "https://redacted.meme",
            "X-Title": "REDACTED Swarm",
        }

    async def stream_message(
        self,
        messages: List[Dict[str, str]],
        tools: Optional[List[Dict[str, Any]]] = None,
        **kwargs
    ) -> AsyncIterator[ProviderEvent]:
        """
        Stream message from OpenRouter (OpenAI-compatible API).
        """
        try:
            import httpx
            
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

            # Stream from OpenRouter
            async with httpx.AsyncClient(timeout=self.config.timeout) as client:
                async with client.stream(
                    "POST",
                    f"{self.base_url}/chat/completions",
                    headers=self.headers,
                    json=request_body,
                ) as response:
                    if response.status_code != 200:
                        error_text = await response.atext()
                        logger.error(
                            f"[openrouter] HTTP {response.status_code}: {error_text}"
                        )
                        yield ProviderEvent(
                            type=EventType.ERROR,
                            error=f"OpenRouter error: {response.status_code}",
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
                                logger.warning(f"[openrouter] Failed to parse: {data_str}")

                    # End signal
                    yield ProviderEvent(type=EventType.TEXT_END)

        except Exception as e:
            logger.error(f"[openrouter] Stream error: {e}")
            yield ProviderEvent(
                type=EventType.ERROR,
                error=f"OpenRouter stream error: {str(e)}",
            )
