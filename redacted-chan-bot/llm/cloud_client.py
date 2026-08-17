# redacted-chan-bot/llm/cloud_client.py
import os
import asyncio
import aiohttp
import json
from typing import Optional, Dict, Any

# Model used exclusively for /alpha — fast xAI inference regardless of LLM_PROVIDER
ALPHA_XAI_MODEL = os.getenv("ALPHA_XAI_MODEL", "grok-4-1-fast")
ALPHA_XAI_BASE  = "https://api.x.ai/v1"

# Privacy proxy — when set, ALL completions route through redacted-proxy instead of hitting
# providers directly. Proxy handles provider routing, PII scrubbing, and local logging.
_PROXY_URL   = os.getenv("PROXY_URL", "").rstrip("/")
_PROXY_TOKEN = os.getenv("PROXY_TOKEN", "")


# ── LLM reasoning-leak scrubbing ──────────────────────────────────────────────
# Reasoning models (via the proxy auto-router) sometimes narrate their planning
# into `content` instead of just producing the message — e.g. "Here's a thinking
# process:\n1. Analyze the Request..." or "The user wants me to...". This is
# distinct from <think>-tagged traces (the proxy already strips those); this is
# bare prose. chan speaks in the first person to "master", so these third-person,
# meta references to "the user"/"the request"/"persona" never appear in a genuine
# message and are safe to detect and drop.
import re as _re

_THINK_RE = _re.compile(r"<(think|thinking|reasoning)>.*?</\1>", _re.DOTALL | _re.IGNORECASE)

# Phrases that essentially never occur in a real chan message but are hallmarks of
# leaked chain-of-thought. Presence anywhere flags the text as reasoning.
_REASONING_SIGNALS = (
    "here's a thinking process",
    "here's my thinking process",
    "here is a thinking process",
    "the user wants me to",
    "the user is asking me to",
    "the user is asking for",
    "the user says:",
    "the user also says",
    "analyze the request",
    "analyze user input",
    "analyze user request",
    "persona: redacted-chan",
    "let me re-read",
    "continue exactly from where you left off",
    "looking at the conversation history",
    "looking at my previous response",
    "the previous turn was me",
    "no preamble.",
)


def looks_like_reasoning(text: str) -> bool:
    """True if `text` reads as leaked meta-reasoning rather than a real message."""
    if not text:
        return False
    return any(sig in text.lower() for sig in _REASONING_SIGNALS)


def strip_reasoning(text: str) -> str:
    """Scrub leaked chain-of-thought from an LLM response.

    Removes <think>/<reasoning> blocks, then — if the result still reads as
    reasoning — tries to salvage a trailing genuine message by dropping leading
    reasoning paragraphs. If nothing clean survives, returns "" so callers treat
    it as an empty generation (fallback chain retries / proactive senders skip)
    rather than posting the reasoning verbatim. Never raises.
    """
    if not text:
        return text
    try:
        cleaned = _THINK_RE.sub("", text).strip()
        if not looks_like_reasoning(cleaned):
            return cleaned
        # Salvage: drop leading paragraphs until a clean tail remains.
        parts = _re.split(r"\n\s*\n", cleaned)
        while parts and looks_like_reasoning(parts[0]):
            parts = parts[1:]
        tail = "\n\n".join(parts).strip()
        return tail if (tail and not looks_like_reasoning(tail)) else ""
    except Exception:
        return text


class CloudLLMClient:
    """Cloud LLM client supporting multiple providers (OpenAI, Anthropic, Together, xAI/Grok)"""

    def __init__(self, provider: str = None, max_tokens: int = None, temperature: float = 0.7):
        self.provider = (provider or os.getenv("LLM_PROVIDER", "groq")).lower()
        if self.provider == "grok":
            self.provider = "xai"
        self._default_max_tokens = max_tokens
        self._default_temperature = temperature
        self.api_key = self._get_api_key()
        self.base_url = self._get_base_url()
        self._xai_key = os.getenv("XAI_API_KEY", "")

    def _get_api_key(self) -> str:
        """Get API key based on provider"""
        keys = {
            "openai": os.getenv("OPENAI_API_KEY"),
            "anthropic": os.getenv("ANTHROPIC_API_KEY"),
            "together": os.getenv("TOGETHER_API_KEY"),
            "xai": os.getenv("XAI_API_KEY"),
            "groq": os.getenv("GROQ_API_KEY"),
            "venice": os.getenv("VENICE_API_KEY"),
        }
        return keys.get(self.provider, "") or ""

    def _get_base_url(self) -> str:
        """Get base URL for provider"""
        urls = {
            "openai": "https://api.openai.com/v1",
            "anthropic": "https://api.anthropic.com/v1",
            "together": "https://api.together.xyz/v1",
            "xai": "https://api.x.ai/v1",
            "groq": "https://api.groq.com/openai/v1",
            "venice": "https://api.venice.ai/api/v1",
        }
        return urls.get(self.provider, "")
    
    async def chat_completion(self, messages: list, model: str = None, max_tokens: int = None) -> str:
        """Chat completion with cloud LLM — routes through privacy proxy if PROXY_URL is set."""
        max_tokens = max_tokens or self._default_max_tokens

        # Route through redacted-proxy if configured
        if _PROXY_URL:
            return await self._proxy_completion(messages, model, max_tokens=max_tokens)

        if self.provider in ("openai", "xai", "groq", "together", "venice"):
            return await self._openai_completion(messages, model, max_tokens=max_tokens)
        elif self.provider == "anthropic":
            return await self._anthropic_completion(messages, model, max_tokens=max_tokens)
        else:
            raise ValueError(f"Unsupported provider: {self.provider}. Set LLM_PROVIDER to openai, xai, groq, anthropic, together, or venice.")

    async def _proxy_completion(self, messages: list, model: str = None, max_tokens: int = None) -> str:
        """Route completion through redacted-proxy (privacy layer)."""
        # Determine model to request
        if model is None:
            # PROXY_MODEL (default "auto") lets redacted-proxy's auto-router pick per prompt.
            model = os.getenv("PROXY_MODEL", "auto")

        budget = max_tokens or 1000
        content, finish = await self._proxy_post(model, messages, budget)

        # If the model narrated its reasoning instead of answering, do NOT auto-continue
        # — asking it to "continue" just amplifies the leak (it narrates more meta-
        # reasoning about the continue instruction). Bail with "" so the caller retries
        # a different provider / skips the proactive message.
        if looks_like_reasoning(content or ""):
            return ""

        # Auto-continue on truncation: when the model stopped because it hit the token
        # budget (finish_reason == "length"), fetch the remainder and stitch it on so
        # replies don't end mid-sentence. Bounded to 2 extra rounds to cap latency/cost.
        full = content or ""
        rounds = 0
        while finish == "length" and rounds < 2 and full.strip():
            rounds += 1
            cont_msgs = list(messages) + [
                {"role": "assistant", "content": full},
                {"role": "user", "content": "Continue exactly from where you left off. Do not repeat anything you already said, no preamble."},
            ]
            try:
                more, finish = await self._proxy_post(model, cont_msgs, budget)
            except Exception:
                break
            if not (more or "").strip():
                break
            full = full.rstrip() + " " + more.lstrip()
        return strip_reasoning(full)

    async def _proxy_post(self, model: str, messages: list, max_tokens: int):
        """Single proxy completion. Returns (content, finish_reason)."""
        payload = {
            "model": model,
            "messages": messages,
            "temperature": self._default_temperature,
            "max_tokens": max_tokens or 1000,
        }
        headers = {
            "Authorization": f"Bearer {_PROXY_TOKEN}",
            "Content-Type": "application/json",
        }
        # Only pin the provider (bypassing the auto-router/free cascade) when explicitly asked.
        if os.getenv("PROXY_PIN_PROVIDER", "false").lower() == "true":
            headers["X-Provider"] = self.provider
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{_PROXY_URL}/v1/chat/completions",
                json=payload,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=90),
            ) as response:
                result = await response.json(content_type=None)
                if "choices" not in result:
                    raise ValueError(f"Proxy error: {result.get('error', result)}")
                choice = result["choices"][0]
                content = choice.get("message", {}).get("content") or ""
                return content, choice.get("finish_reason")

    async def _openai_completion(self, messages: list, model: str = None, max_tokens: int = None) -> str:
        """OpenAI GPT completion (also used for xAI/Grok OpenAI-compatible API)"""
        if self.provider == "xai":
            model = model or os.getenv("XAI_MODEL", "grok-4-1-fast")
        elif self.provider == "groq":
            model = model or os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")
        elif self.provider == "together":
            model = model or "Qwen/Qwen2.5-7B-Instruct-Turbo"
        elif self.provider == "venice":
            model = model or os.getenv("VENICE_MODEL", "gemma-4-uncensored")
        else:
            model = model or "gpt-3.5-turbo"

        payload = {
            "model": model,
            "messages": messages,
            "temperature": 0.7,
            "max_tokens": max_tokens or 1000,
        }

        if self.provider == "venice":
            payload["venice_parameters"] = {
                "include_venice_system_prompt": False,
                "disable_thinking": True,
            }
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.base_url}/chat/completions",
                json=payload,
                headers=headers
            ) as response:
                result = await response.json()
                if "choices" not in result:
                    raise ValueError(f"API error from {self.provider}: {result.get('error', result)}")
                return strip_reasoning(result["choices"][0]["message"]["content"])

    async def chat_completion_with_tools(
        self, messages: list, tools: list, model: str = None, max_tokens: int = None
    ) -> dict:
        """
        OpenAI-compatible chat completion with function calling.
        Returns the full message dict (may contain tool_calls or content).
        Only works with OpenAI-compatible providers (venice, groq, xai, openai).
        """
        if self.provider == "xai":
            model = model or os.getenv("XAI_MODEL", "grok-4-1-fast")
        elif self.provider == "groq":
            model = model or os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")
        elif self.provider == "venice":
            model = model or os.getenv("VENICE_MODEL", "gemma-4-uncensored")
        else:
            model = model or "gpt-3.5-turbo"

        payload = {
            "model": model,
            "messages": messages,
            "temperature": 0.7,
            "max_tokens": max_tokens or 1000,
            "tools": tools,
            "tool_choice": "auto",
        }

        if self.provider == "venice":
            payload["venice_parameters"] = {
                "include_venice_system_prompt": False,
                "disable_thinking": True,
            }

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.base_url}/chat/completions",
                json=payload,
                headers=headers,
            ) as response:
                result = await response.json()
                if "choices" not in result:
                    raise ValueError(f"API error from {self.provider}: {result.get('error', result)}")
                return result["choices"][0]["message"]

    async def _anthropic_completion(self, messages: list, model: str = None, max_tokens: int = None) -> str:
        """Anthropic Claude completion"""
        model = model or "claude-3-haiku-20240307"
        
        # Convert messages to Claude format
        system_msg = ""
        user_messages = []
        
        for msg in messages:
            if msg["role"] == "system":
                system_msg = msg["content"]
            elif msg["role"] == "user":
                user_messages.append({"role": "user", "content": msg["content"]})
            elif msg["role"] == "assistant":
                user_messages.append({"role": "assistant", "content": msg["content"]})
        
        payload = {
            "model": model,
            "max_tokens": max_tokens or 1000,
            "system": system_msg,
            "messages": user_messages,
        }
        
        headers = {
            "x-api-key": self.api_key,
            "Content-Type": "application/json",
            "anthropic-version": "2023-06-01"
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.base_url}/messages",
                json=payload,
                headers=headers
            ) as response:
                result = await response.json()
                if "content" not in result:
                    raise ValueError(f"Anthropic API error: {result.get('error', result)}")
                return strip_reasoning(result["content"][0]["text"])
    
    async def chat_completion_with_fallback(self, messages: list, max_tokens: int = None) -> str:
        """
        Resilient fallback chain. Each entry is (provider, model_override_or_None).
        Venice primary → Venice backup → groq llama-4-scout → anthropic haiku.
        xAI removed from chain — reinstate when credits are topped up.
        On Groq TPD exhaustion (no retry-after in seconds), skip immediately.
        On Groq TPM 429 with retry-after ≤ 20s, wait and retry once.
        """
        import logging, re
        _log = logging.getLogger(__name__)

        VENICE_BACKUP = os.getenv("VENICE_BACKUP_MODEL", "mistral-small-3-2-24b-instruct")
        GROQ_MODEL    = os.getenv("GROQ_MODEL", "meta-llama/llama-4-scout-17b-16e-instruct")

        # (provider, model) pairs — None means use provider default
        _chain: list[tuple[str, str | None]] = [(self.provider, None)]
        if self.provider == "venice":
            _chain += [
                ("venice",    VENICE_BACKUP),
                ("groq",      GROQ_MODEL),
                ("anthropic", None),
            ]
        else:
            _chain += [
                ("venice",    None),
                ("groq",      GROQ_MODEL),
                ("anthropic", None),
            ]

        _key_map = {
            "openai":    os.getenv("OPENAI_API_KEY"),
            "anthropic": os.getenv("ANTHROPIC_API_KEY"),
            "together":  os.getenv("TOGETHER_API_KEY"),
            "xai":       os.getenv("XAI_API_KEY"),
            "groq":      os.getenv("GROQ_API_KEY"),
            "venice":    os.getenv("VENICE_API_KEY"),
        }

        seen: set[tuple[str, str | None]] = set()
        last_err = None

        for provider, model_override in _chain:
            slot = (provider, model_override)
            if slot in seen:
                continue
            seen.add(slot)

            if not _key_map.get(provider):
                continue

            try:
                tmp = CloudLLMClient(provider=provider, max_tokens=max_tokens)
                result = await tmp.chat_completion(messages, model=model_override, max_tokens=max_tokens)
                if result:
                    label = f"{provider}/{model_override or 'default'}"
                    if provider != self.provider or model_override:
                        _log.info(f"[llm] fallback succeeded via {label}")
                    return result
            except Exception as e:
                err_str = str(e)
                _log.warning(f"[llm] {provider}/{model_override or 'default'} failed: {e}")
                last_err = e

                # Groq TPM 429 with short retry window — wait once then continue
                if provider == "groq" and "rate_limit_exceeded" in err_str:
                    wait_match = re.search(r"Please try again in (\d+(?:\.\d+)?)s", err_str)
                    if wait_match:
                        wait_s = min(float(wait_match.group(1)) + 1.0, 20.0)
                        _log.info(f"[llm] groq TPM — waiting {wait_s:.1f}s then retrying")
                        await asyncio.sleep(wait_s)
                        try:
                            result = await tmp.chat_completion(messages, model=model_override, max_tokens=max_tokens)
                            if result:
                                _log.info(f"[llm] groq retry succeeded ({model_override or 'default'})")
                                return result
                        except Exception as e2:
                            _log.warning(f"[llm] groq retry failed: {e2}")
                            last_err = e2
                    # TPD exhaustion has no seconds-based retry-after — skip immediately

        raise RuntimeError(f"all LLM providers failed — last error: {last_err}")

    def switch_provider(self, provider: str) -> bool:
        """
        Hot-swap LLM provider at runtime (session-only, resets on redeploy).
        Returns True if the provider is valid and has a key set.
        """
        provider = provider.lower()
        if provider == "grok":
            provider = "xai"
        valid = ("openai", "anthropic", "together", "xai", "groq", "venice")
        if provider not in valid:
            return False
        self.provider = provider
        self.api_key = self._get_api_key()
        self.base_url = self._get_base_url()
        return True

    def current_model(self) -> str:
        """Return the default model name for the active provider."""
        defaults = {
            "xai":       os.getenv("XAI_MODEL", "grok-4-1-fast"),
            "groq":      os.getenv("GROQ_MODEL", "llama-3.1-8b-instant"),
            "together":  "Qwen/Qwen2.5-7B-Instruct-Turbo",
            "openai":    "gpt-3.5-turbo",
            "anthropic": "claude-3-haiku-20240307",
            "venice":    os.getenv("VENICE_MODEL", "gemma-4-uncensored"),
        }
        return defaults.get(self.provider, "unknown")

    async def alpha_completion(self, messages: list, max_tokens: int = 1200) -> str:
        """Always uses xAI grok-4-1-fast regardless of LLM_PROVIDER — dedicated for /alpha."""
        if not self._xai_key:
            # Fallback to default provider if xAI key not set
            return await self.chat_completion(messages, max_tokens=max_tokens)
        payload = {
            "model": ALPHA_XAI_MODEL,
            "messages": messages,
            "temperature": 0.7,
            "max_tokens": max_tokens,
        }
        headers = {
            "Authorization": f"Bearer {self._xai_key}",
            "Content-Type": "application/json",
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{ALPHA_XAI_BASE}/chat/completions",
                json=payload,
                headers=headers,
            ) as response:
                result = await response.json()
                if "choices" not in result:
                    raise ValueError(f"xAI alpha error: {result.get('error', result)}")
                return strip_reasoning(result["choices"][0]["message"]["content"])

    async def _together_completion(self, messages: list, model: str = None) -> str:
        """Together AI completion (mix of open source models)"""
        model = model or "Qwen/Qwen2.5-7B-Instruct-Turbo"
        
        payload = {
            "model": model,
            "messages": messages,
            "temperature": 0.7,
            "max_tokens": 1000
        }
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.base_url}/chat/completions",
                json=payload,
                headers=headers
            ) as response:
                result = await response.json()
                return strip_reasoning(result["choices"][0]["message"]["content"])
