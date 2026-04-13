"""
Groq Provider Implementation

Stream-based LLM inference via Groq API.
"""

import logging
from typing import List, Dict, Any, Optional, AsyncIterator
from groq import Groq as GroqClient
from groq import APIError

from llm.provider_base import LLMProvider, ProviderConfig, ProviderEvent, EventType

logger = logging.getLogger(__name__)


class GroqProvider(LLMProvider):
    """
    Groq LLM Provider — Fast inference using Groq API.

    Models: llama-3.1-8b-instant, mixtral-8x7b-32768, llama-2-70b-4096
    """

    def __init__(self, config: ProviderConfig):
        super().__init__(config)
        self.client = GroqClient(api_key=self.api_key)

    async def stream_message(
        self,
        messages: List[Dict[str, str]],
        tools: Optional[List[Dict[str, Any]]] = None,
        **kwargs
    ) -> AsyncIterator[ProviderEvent]:
        """
        Stream message from Groq.

        Note: Groq doesn't support function calling in the same way as OpenAI,
        so tools parameter is ignored for now.
        """
        try:
            # Build request params
            request_params = {
                "model": self.model,
                "messages": messages,
                "stream": True,
                "temperature": self.config.temperature,
            }

            if self.config.max_tokens:
                request_params["max_tokens"] = self.config.max_tokens

            # Add any extra kwargs
            request_params.update(kwargs)

            # Stream from Groq
            with self.client.messages.stream(**request_params) as stream:
                text_buffer = ""

                for event in stream:
                    # Groq returns delta events
                    if hasattr(event, "delta") and event.delta:
                        if hasattr(event.delta, "content"):
                            content = event.delta.content
                            if content:
                                text_buffer += content
                                yield ProviderEvent(
                                    type=EventType.TEXT_DELTA,
                                    content=content,
                                )

                # Emit end event with usage
                if hasattr(event, "usage") and event.usage:
                    yield ProviderEvent(
                        type=EventType.TEXT_END,
                        content=None,
                        usage={
                            "input_tokens": event.usage.input_tokens,
                            "output_tokens": event.usage.output_tokens,
                        },
                    )

        except APIError as e:
            logger.error(f"[groq] API error: {e}")
            yield ProviderEvent(
                type=EventType.ERROR,
                error=f"Groq API error: {str(e)}",
            )
        except Exception as e:
            logger.error(f"[groq] Stream error: {e}")
            yield ProviderEvent(
                type=EventType.ERROR,
                error=f"Groq stream error: {str(e)}",
            )
