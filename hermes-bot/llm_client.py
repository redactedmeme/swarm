"""Groq chat wrapper — minimal, single-provider."""
import logging
import os
from typing import Iterable

from groq import Groq, APIError

logger = logging.getLogger(__name__)

DEFAULT_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")


class LLMClient:
    def __init__(self):
        api_key = os.getenv("GROQ_API_KEY", "").strip()
        if not api_key:
            raise RuntimeError("GROQ_API_KEY not set")
        self._client = Groq(api_key=api_key)

    def chat(
        self,
        system: str,
        user: str,
        *,
        model: str | None = None,
        max_tokens: int = 800,
        temperature: float = 0.85,
        extra_messages: Iterable[dict] | None = None,
    ) -> str:
        messages = [{"role": "system", "content": system}]
        if extra_messages:
            messages.extend(extra_messages)
        messages.append({"role": "user", "content": user})

        try:
            resp = self._client.chat.completions.create(
                model=model or DEFAULT_MODEL,
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
            )
            return (resp.choices[0].message.content or "").strip()
        except APIError as e:
            logger.error(f"[llm] Groq APIError: {e}")
            raise
