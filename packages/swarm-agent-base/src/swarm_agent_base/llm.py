"""One OpenAI-compatible chat client for every swarm agent.

Consolidates the copies that lived in ``apps/hermes/llm_client.py`` and
``apps/{chan,smolting}/llm/cloud_client.py``:

* If ``PROXY_URL`` is set, talk to the local ``apps/proxy`` auto-router
  (``{PROXY_URL}/v1``) with ``PROXY_TOKEN`` — send ``model="auto"`` by default so
  the free-first cascade (Groq ``gpt-oss`` / OpenRouter ``:free`` -> paid
  ``deepseek`` last) picks the model.
* Otherwise fall back to Groq directly with ``GROQ_API_KEY``.

Per-model 429 cooldown + one fallback model, same as the old hermes client.
Synchronous ``.chat()``; ``.achat()`` wraps it in a thread for async callers.
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Iterable

logger = logging.getLogger(__name__)

_COOLDOWN_SECONDS = 60
_model_cooldown_until: dict[str, float] = {}


def _default_model() -> str:
    # PROXY_MODEL wins (chan/dharma convention); GROQ_MODEL is the hermes
    # convention; "auto" engages the proxy cascade.
    return (
        os.getenv("PROXY_MODEL")
        or os.getenv("GROQ_MODEL")
        or "auto"
    ).strip()


def _fallback_model() -> str:
    return os.getenv("GROQ_FALLBACK_MODEL", "llama-3.3-70b-versatile").strip()


def _on_cooldown(model: str) -> bool:
    return time.time() < _model_cooldown_until.get(model, 0)


def _set_cooldown(model: str) -> None:
    _model_cooldown_until[model] = time.time() + _COOLDOWN_SECONDS


def _make_client():
    """OpenAI-compatible client pointed at the proxy, or Groq directly."""
    proxy_url = os.getenv("PROXY_URL", "").rstrip("/")
    if proxy_url:
        from openai import OpenAI

        return OpenAI(
            base_url=f"{proxy_url}/v1/",
            api_key=os.getenv("PROXY_TOKEN", "") or "unused",
        )
    from openai import OpenAI

    api_key = os.getenv("GROQ_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("neither PROXY_URL nor GROQ_API_KEY is set")
    return OpenAI(base_url="https://api.groq.com/openai/v1", api_key=api_key)


class LLM:
    """Thin chat wrapper. Construct once per process."""

    def __init__(self, *, default_model: str | None = None) -> None:
        self._client = _make_client()
        self._model = (default_model or _default_model())

    # -- sync -------------------------------------------------------------
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
        messages: list[dict] = [{"role": "system", "content": system}]
        if extra_messages:
            messages.extend(extra_messages)
        messages.append({"role": "user", "content": user})
        return self.complete(messages, model=model, max_tokens=max_tokens,
                             temperature=temperature)

    def complete(
        self,
        messages: list[dict],
        *,
        model: str | None = None,
        max_tokens: int = 800,
        temperature: float = 0.85,
    ) -> str:
        primary = (model or self._model)
        candidates = [primary]
        fb = _fallback_model()
        if fb and fb != primary:
            candidates.append(fb)

        last_err: Exception | None = None
        for m in candidates:
            if _on_cooldown(m):
                logger.info("[llm] skipping %s — in 429 cooldown", m)
                continue
            try:
                resp = self._client.chat.completions.create(
                    model=m,
                    messages=messages,
                    max_tokens=max_tokens,
                    temperature=temperature,
                )
                return (resp.choices[0].message.content or "").strip()
            except Exception as e:  # noqa: BLE001
                status = getattr(e, "status_code", None)
                if status == 429:
                    _set_cooldown(m)
                    logger.warning("[llm] %s 429 — cooling %ss, trying fallback",
                                   m, _COOLDOWN_SECONDS)
                    last_err = e
                    continue
                logger.error("[llm] %s error: %s", m, e)
                last_err = e
                continue

        if last_err:
            raise last_err
        raise RuntimeError("[llm] all candidate models in cooldown")

    # -- async ---------------------------------------------------------------
    async def achat(self, system: str, user: str, **kw) -> str:
        return await asyncio.to_thread(self.chat, system, user, **kw)

    async def acomplete(self, messages: list[dict], **kw) -> str:
        return await asyncio.to_thread(self.complete, messages, **kw)
