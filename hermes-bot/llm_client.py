"""Groq chat wrapper — with model fallback, 429 backoff, and optional proxy."""
import logging
import os
import time
from typing import Iterable

logger = logging.getLogger(__name__)

DEFAULT_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
FALLBACK_MODEL = os.getenv("GROQ_FALLBACK_MODEL", "llama-3.3-70b-versatile")

# Simple global cooldown: if a model just 429'd, skip it for N seconds.
_model_cooldown_until: dict[str, float] = {}
_COOLDOWN_SECONDS = 60


def _on_cooldown(model: str) -> bool:
    until = _model_cooldown_until.get(model, 0)
    return time.time() < until


def _set_cooldown(model: str) -> None:
    _model_cooldown_until[model] = time.time() + _COOLDOWN_SECONDS


def _make_client():
    """Return an OpenAI-compatible client pointed at proxy or Groq directly."""
    proxy_url = os.getenv("PROXY_URL", "").rstrip("/")
    if proxy_url:
        from openai import OpenAI
        return OpenAI(base_url=proxy_url, api_key=os.getenv("PROXY_TOKEN", ""))
    from groq import Groq
    api_key = os.getenv("GROQ_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("GROQ_API_KEY not set")
    return Groq(api_key=api_key)


class LLMClient:
    def __init__(self):
        self._client = _make_client()

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

        primary = model or DEFAULT_MODEL
        candidates = [primary]
        if FALLBACK_MODEL and FALLBACK_MODEL != primary:
            candidates.append(FALLBACK_MODEL)

        last_err: Exception | None = None
        for m in candidates:
            if _on_cooldown(m):
                logger.info(f"[llm] skipping {m} — in 429 cooldown")
                continue
            try:
                resp = self._client.chat.completions.create(
                    model=m,
                    messages=messages,
                    max_tokens=max_tokens,
                    temperature=temperature,
                )
                return (resp.choices[0].message.content or "").strip()
            except Exception as e:
                status = getattr(e, "status_code", None)
                if status == 429:
                    _set_cooldown(m)
                    logger.warning(f"[llm] {m} 429 — cooling down {_COOLDOWN_SECONDS}s, trying fallback")
                    last_err = e
                    continue
                logger.error(f"[llm] {m} error: {e}")
                raise

        if last_err:
            raise last_err
        raise RuntimeError("[llm] all candidate models in cooldown")
