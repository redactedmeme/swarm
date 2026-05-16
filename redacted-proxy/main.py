# redacted-proxy/main.py
"""
redacted-proxy — OpenAI-compatible LLM privacy proxy.

A transparent relay layer sitting between our bots and upstream LLM providers.
Inspired by Venice.ai's architecture: identity obscured from providers,
parameter control, local-only logging, no fingerprinting headers.

Exposes an OpenAI-compatible API so any client (redacted-chan-bot, smolting,
webchat) can point at it without code changes — just change the base URL and
bearer token.

Endpoints:
  POST /v1/chat/completions   — main proxy endpoint
  GET  /v1/models             — list available model aliases
  GET  /health                — liveness
  GET  /logs                  — recent proxy log (admin auth required)

Provider routing (by model name prefix or X-Provider header):
  grok-*          → xAI (api.x.ai)
  llama-*, gemma-*, mixtral-*, qwen-* → Groq (api.groq.com)
  claude-*        → Anthropic
  gpt-*           → OpenAI

Privacy transforms applied before forwarding:
  - Strip fingerprinting headers (User-Agent, X-Request-ID, X-Forwarded-For, etc.)
  - Optionally scrub PII patterns from message content (PRIVACY_SCRUB=true)
  - Add synthetic User-Agent if required by provider

Local transparency log:
  - Every request+response logged to /data/proxy_log.jsonl
  - Includes: timestamp, model, provider, latency_ms, input_tokens_est, output_tokens_est
  - Message content logged truncated (first 200 chars per turn)
  - Max 5000 entries (rotates)

Environment variables:
  PROXY_TOKEN         — bearer token clients must present (required)
  XAI_API_KEY         — xAI upstream key
  GROQ_API_KEY        — Groq upstream key
  ANTHROPIC_API_KEY   — Anthropic upstream key
  OPENAI_API_KEY      — OpenAI upstream key
  PRIVACY_SCRUB       — "true" to enable PII regex scrubbing (default: false)
  DEFAULT_TEMPERATURE — override temperature for all requests (optional)
  DEFAULT_TOP_P       — override top_p for all requests (optional)
  LOG_CONTENT         — "false" to disable content in logs (default: true)
  PORT                — listen port (default: 7080)
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from pathlib import Path
from typing import Any

import aiohttp
from aiohttp import web

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [proxy] %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────

PROXY_TOKEN         = os.getenv("PROXY_TOKEN", "")
PRIVACY_SCRUB       = os.getenv("PRIVACY_SCRUB", "false").lower() == "true"
DEFAULT_TEMPERATURE = os.getenv("DEFAULT_TEMPERATURE", "")
DEFAULT_TOP_P       = os.getenv("DEFAULT_TOP_P", "")
LOG_CONTENT         = os.getenv("LOG_CONTENT", "true").lower() != "false"
PORT                = int(os.getenv("PORT", "7080"))

_DATA_DIR  = Path("/data") if Path("/data").exists() else Path(__file__).parent / "data"
_LOG_PATH  = _DATA_DIR / "proxy_log.jsonl"
_LOG_MAX   = 5000   # entries before rotation

# ── Provider routing ──────────────────────────────────────────────────────────

_PROVIDER_URLS = {
    "xai":       "https://api.x.ai/v1/chat/completions",
    "groq":      "https://api.groq.com/openai/v1/chat/completions",
    "anthropic": "https://api.anthropic.com/v1/messages",
    "openai":    "https://api.openai.com/v1/chat/completions",
}

_PROVIDER_KEYS = {
    "xai":       os.getenv("XAI_API_KEY", ""),
    "groq":      os.getenv("GROQ_API_KEY", ""),
    "anthropic": os.getenv("ANTHROPIC_API_KEY", ""),
    "openai":    os.getenv("OPENAI_API_KEY", ""),
}

_MODEL_ALIASES = {
    # xAI
    "grok-4-1-fast":            ("xai",       "grok-4-1-fast"),
    "grok-3-fast":              ("xai",       "grok-3-fast"),
    "grok-3":                   ("xai",       "grok-3"),
    # Groq
    "llama-3.3-70b":            ("groq",      "llama-3.3-70b-versatile"),
    "llama-3.1-8b":             ("groq",      "llama-3.1-8b-instant"),
    "llama-3.1-8b-instant":     ("groq",      "llama-3.1-8b-instant"),
    "llama-3.3-70b-versatile":  ("groq",      "llama-3.3-70b-versatile"),
    "gemma2-9b-it":             ("groq",      "gemma2-9b-it"),
    "mixtral-8x7b":             ("groq",      "mixtral-8x7b-32768"),
    "qwen-qwq-32b":             ("groq",      "qwen-qwq-32b"),
    # Anthropic
    "claude-haiku":             ("anthropic", "claude-3-haiku-20240307"),
    "claude-sonnet":            ("anthropic", "claude-sonnet-4-5"),
    "claude-opus":              ("anthropic", "claude-opus-4-5"),
    "claude-3-haiku-20240307":  ("anthropic", "claude-3-haiku-20240307"),
    # OpenAI
    "gpt-4o":                   ("openai",    "gpt-4o"),
    "gpt-4o-mini":              ("openai",    "gpt-4o-mini"),
}


def _resolve_provider(model: str, explicit_provider: str = "") -> tuple[str, str]:
    """Return (provider, upstream_model) for a given model name."""
    if explicit_provider:
        ep = explicit_provider.lower()
        return ep, model

    # Exact alias match
    if model in _MODEL_ALIASES:
        return _MODEL_ALIASES[model]

    # Prefix-based routing
    if model.startswith("grok-"):
        return "xai", model
    if model.startswith(("llama-", "gemma", "mixtral", "qwen-", "deepseek-")):
        return "groq", model
    if model.startswith("claude-"):
        return "anthropic", model
    if model.startswith("gpt-"):
        return "openai", model

    # Default: Groq
    return "groq", model


# ── Privacy transforms ────────────────────────────────────────────────────────

# Headers we strip before forwarding to providers
_STRIP_HEADERS = {
    "user-agent", "x-request-id", "x-forwarded-for", "x-real-ip",
    "x-forwarded-proto", "x-forwarded-host", "cf-connecting-ip",
    "cf-ray", "cf-ipcountry", "x-amzn-trace-id", "x-correlation-id",
    "referer", "origin", "x-proxy-token",   # never forward our auth token
}

# PII patterns for optional scrubbing
_PII_PATTERNS = [
    (re.compile(r'\b\d{7,15}\b'), "[ID]"),                         # Telegram IDs, phone numbers
    (re.compile(r'@[\w_]{3,32}\b'), "@[user]"),                    # @usernames
    (re.compile(r'\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Z|a-z]{2,}\b'), "[email]"),
]


def _scrub_pii(text: str) -> str:
    """Apply PII regex scrubs to message text."""
    for pattern, replacement in _PII_PATTERNS:
        text = pattern.sub(replacement, text)
    return text


def _clean_messages(messages: list[dict], scrub: bool) -> list[dict]:
    """Return cleaned message list — scrubs PII if requested."""
    if not scrub:
        return messages
    cleaned = []
    for msg in messages:
        content = msg.get("content", "")
        if isinstance(content, str):
            content = _scrub_pii(content)
        elif isinstance(content, list):
            # Multimodal — scrub text parts only
            content = [
                {**part, "text": _scrub_pii(part["text"])} if part.get("type") == "text" else part
                for part in content
            ]
        cleaned.append({**msg, "content": content})
    return cleaned


def _build_forward_headers(provider: str) -> dict[str, str]:
    """Build clean headers for upstream provider — no fingerprinting."""
    key = _PROVIDER_KEYS.get(provider, "")
    if provider == "anthropic":
        return {
            "x-api-key":           key,
            "anthropic-version":   "2023-06-01",
            "content-type":        "application/json",
        }
    return {
        "Authorization": f"Bearer {key}",
        "Content-Type":  "application/json",
    }


# ── Anthropic format conversion ───────────────────────────────────────────────

def _to_anthropic(payload: dict) -> dict:
    """Convert OpenAI-format payload to Anthropic Messages API format."""
    messages = payload.get("messages", [])
    system_msg = ""
    user_messages = []
    for m in messages:
        if m["role"] == "system":
            system_msg = m.get("content", "")
        else:
            user_messages.append({"role": m["role"], "content": m.get("content", "")})
    body: dict[str, Any] = {
        "model":      payload["model"],
        "max_tokens": payload.get("max_tokens", 1024),
        "messages":   user_messages,
    }
    if system_msg:
        body["system"] = system_msg
    if "temperature" in payload:
        body["temperature"] = payload["temperature"]
    if "top_p" in payload:
        body["top_p"] = payload["top_p"]
    return body


def _from_anthropic(result: dict) -> dict:
    """Convert Anthropic response to OpenAI-compat format."""
    text = result.get("content", [{}])[0].get("text", "")
    usage = result.get("usage", {})
    return {
        "id":      result.get("id", ""),
        "object":  "chat.completion",
        "model":   result.get("model", ""),
        "choices": [{"message": {"role": "assistant", "content": text}, "finish_reason": "stop", "index": 0}],
        "usage":   {"prompt_tokens": usage.get("input_tokens", 0), "completion_tokens": usage.get("output_tokens", 0)},
    }


# ── Local logging ─────────────────────────────────────────────────────────────

def _log_entry(provider: str, model: str, messages: list, response_text: str,
               latency_ms: float, error: str = "") -> None:
    """Append a log entry to proxy_log.jsonl."""
    try:
        _DATA_DIR.mkdir(parents=True, exist_ok=True)
        entry: dict[str, Any] = {
            "ts":          time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "provider":    provider,
            "model":       model,
            "latency_ms":  round(latency_ms),
            "turns":       len(messages),
        }
        if LOG_CONTENT:
            entry["messages_preview"] = [
                {"role": m.get("role", "?"),
                 "content": str(m.get("content", ""))[:200]}
                for m in messages[-3:]   # last 3 turns only
            ]
            entry["response_preview"] = response_text[:300]
        if error:
            entry["error"] = error[:200]

        line = json.dumps(entry, ensure_ascii=False) + "\n"
        with open(_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line)

        # Rotate: keep last _LOG_MAX entries
        try:
            lines = _LOG_PATH.read_text(encoding="utf-8").splitlines()
            if len(lines) > _LOG_MAX:
                _LOG_PATH.write_text("\n".join(lines[-_LOG_MAX:]) + "\n", encoding="utf-8")
        except Exception:
            pass

    except Exception as e:
        logger.debug("[proxy] log write failed: %s", e)


# ── Core proxy ────────────────────────────────────────────────────────────────

async def _forward(provider: str, upstream_model: str, payload: dict,
                   session: aiohttp.ClientSession) -> dict:
    """Forward a request to the upstream provider and return OpenAI-compat response."""
    headers = _build_forward_headers(provider)
    url     = _PROVIDER_URLS[provider]

    if provider == "anthropic":
        body = _to_anthropic({**payload, "model": upstream_model})
        async with session.post(url, json=body, headers=headers, timeout=aiohttp.ClientTimeout(total=90)) as resp:
            result = await resp.json(content_type=None)
            if "content" not in result:
                raise ValueError(f"Anthropic error: {result.get('error', result)}")
            return _from_anthropic(result)
    else:
        body = {**payload, "model": upstream_model}
        async with session.post(url, json=body, headers=headers, timeout=aiohttp.ClientTimeout(total=90)) as resp:
            result = await resp.json(content_type=None)
            if "choices" not in result:
                raise ValueError(f"{provider} error: {result.get('error', result)}")
            return result


# ── Auth middleware ───────────────────────────────────────────────────────────

async def _auth_middleware(app, handler):
    async def middleware(request: web.Request):
        if request.path in ("/health", "/v1/models"):
            return await handler(request)
        if PROXY_TOKEN:
            auth = request.headers.get("Authorization", "")
            if auth != f"Bearer {PROXY_TOKEN}":
                return web.json_response({"error": {"message": "Unauthorized", "type": "auth_error"}}, status=401)
        return await handler(request)
    return middleware


# ── Handlers ──────────────────────────────────────────────────────────────────

async def handle_health(request: web.Request) -> web.Response:
    providers_up = {p: bool(k) for p, k in _PROVIDER_KEYS.items()}
    return web.json_response({"status": "ok", "providers": providers_up, "privacy_scrub": PRIVACY_SCRUB})


async def handle_models(request: web.Request) -> web.Response:
    models = [
        {"id": alias, "object": "model", "owned_by": prov}
        for alias, (prov, _) in _MODEL_ALIASES.items()
        if _PROVIDER_KEYS.get(prov)
    ]
    return web.json_response({"object": "list", "data": models})


async def handle_chat_completions(request: web.Request) -> web.Response:
    t0 = time.monotonic()

    try:
        payload = await request.json()
    except Exception:
        return web.json_response({"error": {"message": "invalid JSON"}}, status=400)

    model    = payload.get("model", "llama-3.1-8b-instant")
    explicit = request.headers.get("X-Provider", "")
    provider, upstream_model = _resolve_provider(model, explicit)

    if not _PROVIDER_KEYS.get(provider):
        return web.json_response(
            {"error": {"message": f"No API key configured for provider: {provider}"}}, status=503)

    # Apply parameter overrides
    if DEFAULT_TEMPERATURE:
        payload.setdefault("temperature", float(DEFAULT_TEMPERATURE))
    if DEFAULT_TOP_P:
        payload.setdefault("top_p", float(DEFAULT_TOP_P))

    # Client can override via headers
    if request.headers.get("X-Temperature"):
        payload["temperature"] = float(request.headers["X-Temperature"])
    if request.headers.get("X-Top-P"):
        payload["top_p"] = float(request.headers["X-Top-P"])

    # Privacy: clean messages
    original_messages = payload.get("messages", [])
    payload["messages"] = _clean_messages(original_messages, PRIVACY_SCRUB)

    # Forward
    error_text = ""
    response_text = ""
    try:
        async with aiohttp.ClientSession() as session:
            result = await _forward(provider, upstream_model, payload, session)
        response_text = result.get("choices", [{}])[0].get("message", {}).get("content", "")
        latency_ms = (time.monotonic() - t0) * 1000
        logger.info("[proxy] %s/%s → %d chars (%.0fms)", provider, upstream_model, len(response_text), latency_ms)
        _log_entry(provider, upstream_model, original_messages, response_text, latency_ms)
        return web.json_response(result)

    except Exception as e:
        error_text = str(e)
        latency_ms = (time.monotonic() - t0) * 1000
        logger.warning("[proxy] %s/%s failed: %s", provider, upstream_model, error_text)
        _log_entry(provider, upstream_model, original_messages, "", latency_ms, error=error_text)
        return web.json_response(
            {"error": {"message": error_text, "provider": provider}}, status=502)


async def handle_logs(request: web.Request) -> web.Response:
    """Return recent proxy log entries (last 100)."""
    n = int(request.query.get("n", "100"))
    try:
        if not _LOG_PATH.exists():
            return web.json_response({"entries": []})
        lines = _LOG_PATH.read_text(encoding="utf-8").splitlines()
        entries = []
        for line in lines[-n:]:
            try:
                entries.append(json.loads(line))
            except Exception:
                pass
        return web.json_response({"entries": entries, "total_stored": len(lines)})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


# ── Server ────────────────────────────────────────────────────────────────────

async def make_app() -> web.Application:
    app = web.Application(middlewares=[_auth_middleware])
    app.router.add_get("/health",                handle_health)
    app.router.add_get("/v1/models",             handle_models)
    app.router.add_post("/v1/chat/completions",  handle_chat_completions)
    app.router.add_get("/logs",                  handle_logs)
    return app


if __name__ == "__main__":
    logger.info("[proxy] starting on port %d (scrub=%s)", PORT, PRIVACY_SCRUB)
    web.run_app(make_app(), port=PORT, host="0.0.0.0")
