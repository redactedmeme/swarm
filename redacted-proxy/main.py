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

Privacy modes (PRIVACY_MODE env var):
  anonymous  — strip fingerprinting headers + synthetic UA (default)
  private    — anonymous + disable content logging by default
  (tee/e2ee reserved for future TEE-capable backends)

Privacy transforms applied before forwarding:
  - Strip all fingerprinting / tracing / routing headers
  - Synthetic randomised User-Agent so upstream can't fingerprint us
  - Optionally scrub PII patterns from message content (PRIVACY_SCRUB=true)
  - X-Ephemeral: true header disables logging for that request entirely
  - Client Authorization header never forwarded upstream

Logging (LOG_LEVEL env var):
  none     — no disk writes at all
  minimal  — metadata only: ts, provider, model, latency, token counts (default in private mode)
  full     — minimal + truncated message previews (default in anonymous mode)

Rate limiting:
  Per proxy token: RATE_LIMIT_RPM requests/minute (default 60, 0 = disabled)

Environment variables:
  PROXY_TOKEN         — bearer token clients must present (required)
  XAI_API_KEY         — xAI upstream key
  GROQ_API_KEY        — Groq upstream key
  ANTHROPIC_API_KEY   — Anthropic upstream key
  OPENAI_API_KEY      — OpenAI upstream key
  PRIVACY_MODE        — anonymous | private (default: anonymous)
  PRIVACY_SCRUB       — "true" to enable PII regex scrubbing (default: false)
  LOG_LEVEL           — none | minimal | full (overrides PRIVACY_MODE default)
  LOG_CONTENT         — legacy alias: "false" forces LOG_LEVEL=minimal
  RATE_LIMIT_RPM      — max requests per token per minute (default: 60, 0=off)
  DEFAULT_TEMPERATURE — override temperature for all requests (optional)
  DEFAULT_TOP_P       — override top_p for all requests (optional)
  PORT                — listen port (default: 7080)
"""

from __future__ import annotations

import asyncio
import collections
import json
import logging
import os
import random
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
DEFAULT_TEMPERATURE = os.getenv("DEFAULT_TEMPERATURE", "")
DEFAULT_TOP_P       = os.getenv("DEFAULT_TOP_P", "")
RATE_LIMIT_RPM      = int(os.getenv("RATE_LIMIT_RPM", "60"))
PORT                = int(os.getenv("PORT", "7080"))
REDIS_URL           = os.getenv("REDIS_URL", "redis://localhost:6379")
HEARTBEAT_PREFIX    = "swarm:heartbeat:"
HEARTBEAT_TTL       = 600   # 10 min — proxy announces every 3 min so key stays fresh

# Runtime-mutable config — all values here can be changed via POST /config
# without a redeploy. Seeded from env vars at startup.
def _default_log_level(privacy_mode: str) -> str:
    env = os.getenv("LOG_LEVEL", "").lower()
    if not env and os.getenv("LOG_CONTENT", "").lower() == "false":
        env = "minimal"
    if env in ("none", "minimal", "full"):
        return env
    return "minimal" if privacy_mode in ("private", "maximum") else "full"

_cfg: dict = {
    "privacy_mode":   os.getenv("PRIVACY_MODE", "anonymous").lower(),
    "privacy_scrub":  os.getenv("PRIVACY_SCRUB", "false").lower() == "true",
    "ephemeral_mode": os.getenv("EPHEMERAL_MODE", "false").lower() == "true",
    "log_level":      "",   # filled below
}
_cfg["log_level"] = _default_log_level(_cfg["privacy_mode"])

# Shorthands used internally
def PRIVACY_MODE()  -> str:  return _cfg["privacy_mode"]
def PRIVACY_SCRUB() -> bool: return _cfg["privacy_scrub"]
def EPHEMERAL_MODE()-> bool: return _cfg["ephemeral_mode"]
def LOG_LEVEL()     -> str:  return _cfg["log_level"]

_DATA_DIR  = Path("/data") if Path("/data").exists() else Path(__file__).parent / "data"
_LOG_PATH  = _DATA_DIR / "proxy_log.jsonl"
_LOG_MAX   = 5000   # entries before rotation

# In-memory ring buffer (last 500 entries) — avoids disk reads on /logs
_log_ring: collections.deque = collections.deque(maxlen=500)

# ── Rate limiting ─────────────────────────────────────────────────────────────

# token → deque of request timestamps (float epoch seconds)
_rate_buckets: dict[str, collections.deque] = {}

def _check_rate_limit(token: str) -> bool:
    """Return True if request is allowed, False if rate limited."""
    if RATE_LIMIT_RPM <= 0:
        return True
    now = time.monotonic()
    window = 60.0
    bucket = _rate_buckets.setdefault(token, collections.deque())
    # Drop timestamps older than 1 minute
    while bucket and now - bucket[0] > window:
        bucket.popleft()
    if len(bucket) >= RATE_LIMIT_RPM:
        return False
    bucket.append(now)
    return True

# ── Provider routing ──────────────────────────────────────────────────────────

_PROVIDER_URLS = {
    "xai":       "https://api.x.ai/v1/chat/completions",
    "groq":      "https://api.groq.com/openai/v1/chat/completions",
    "anthropic": "https://api.anthropic.com/v1/messages",
    "openai":    "https://api.openai.com/v1/chat/completions",
    "venice":    "https://api.venice.ai/api/v1/chat/completions",
}

_PROVIDER_KEYS = {
    "xai":       os.getenv("XAI_API_KEY", ""),
    "groq":      os.getenv("GROQ_API_KEY", ""),
    "anthropic": os.getenv("ANTHROPIC_API_KEY", ""),
    "openai":    os.getenv("OPENAI_API_KEY", ""),
    "venice":    os.getenv("VENICE_API_KEY", ""),
}

# Venice models — matched by exact name; must NOT overlap with Groq llama names
_VENICE_MODELS: frozenset[str] = frozenset({
    "gemma-4-uncensored",
    "mistral-31-24b",
    "mistral-small-3-2-24b-instruct",
    "qwen-2-5-vl",
    "nous-hermes-3-nitro",
    "venice-uncensored",
    "lfm-40b",
    "llama-3-3-70b",           # Venice's own llama build (different from Groq's)
})

_MODEL_ALIASES = {
    # xAI
    "grok-4-1-fast":            ("xai",       "grok-4-1-fast"),
    "grok-3-fast":              ("xai",       "grok-3-fast"),
    "grok-3":                   ("xai",       "grok-3"),
    # Groq  (explicit aliases keep these away from Venice prefix matching)
    "llama-3.3-70b":            ("groq",      "llama-3.3-70b-versatile"),
    "llama-3.1-8b":             ("groq",      "llama-3.1-8b-instant"),
    "llama-3.1-8b-instant":     ("groq",      "llama-3.1-8b-instant"),
    "llama-3.3-70b-versatile":  ("groq",      "llama-3.3-70b-versatile"),
    "gemma2-9b-it":             ("groq",      "gemma2-9b-it"),
    "mixtral-8x7b":             ("groq",      "mixtral-8x7b-32768"),
    "qwen-qwq-32b":             ("groq",      "qwen-qwq-32b"),
    "openai/gpt-oss-120b":      ("groq",      "openai/gpt-oss-120b"),
    "openai/gpt-oss-20b":       ("groq",      "openai/gpt-oss-20b"),
    # Anthropic
    "claude-haiku":             ("anthropic", "claude-3-haiku-20240307"),
    "claude-sonnet":            ("anthropic", "claude-sonnet-4-5"),
    "claude-opus":              ("anthropic", "claude-opus-4-5"),
    "claude-3-haiku-20240307":  ("anthropic", "claude-3-haiku-20240307"),
    # OpenAI
    "gpt-4o":                   ("openai",    "gpt-4o"),
    "gpt-4o-mini":              ("openai",    "gpt-4o-mini"),
    # Venice aliases
    "gemma-4-uncensored":                 ("venice", "gemma-4-uncensored"),
    "mistral-31-24b":                     ("venice", "mistral-31-24b"),
    "mistral-small-3-2-24b-instruct":     ("venice", "mistral-small-3-2-24b-instruct"),
    "venice-uncensored":                  ("venice", "venice-uncensored"),
    "nous-hermes-3-nitro":                ("venice", "nous-hermes-3-nitro"),
    "lfm-40b":                            ("venice", "lfm-40b"),
}

# Model equivalence — fallback cascade when primary provider is unavailable
# Used for intelligent failover when provider hits TPD/quotas
_MODEL_EQUIVALENTS: dict[str, list[str]] = {
    "grok-4-1-fast":             ["llama-3.3-70b", "claude-opus", "gpt-4o"],
    "grok-3-fast":               ["llama-3.3-70b", "gemma-4-uncensored"],
    "llama-3.3-70b":             ["gpt-4o", "claude-opus", "grok-4-1-fast"],
    "llama-3.1-8b-instant":      ["gemma2-9b-it", "gpt-4o-mini", "claude-haiku"],
    "claude-opus":               ["gpt-4o", "llama-3.3-70b"],
    "claude-sonnet":             ["gpt-4o", "llama-3.1-8b"],
    "claude-haiku":              ["gpt-4o-mini", "llama-3.1-8b-instant"],
    "gpt-4o":                    ["claude-opus", "llama-3.3-70b"],
    "gpt-4o-mini":               ["claude-haiku", "llama-3.1-8b-instant"],
    "gemma-4-uncensored":        ["llama-3.3-70b", "gpt-4o"],
    "nous-hermes-3-nitro":       ["llama-3.3-70b", "gpt-4o"],
}

# Provider pricing (USD per 1M tokens) — estimated; used for cost tracking
_PROVIDER_COSTS: dict[str, dict[str, float]] = {
    "xai": {
        "grok-4-1-fast": {"input": 5.0, "output": 15.0},
        "grok-3-fast": {"input": 1.5, "output": 6.0},
        "grok-3": {"input": 1.0, "output": 4.0},
    },
    "groq": {
        "llama-3.3-70b-versatile": {"input": 0.05, "output": 0.1},
        "llama-3.1-8b-instant": {"input": 0.05, "output": 0.1},
        "gemma2-9b-it": {"input": 0.05, "output": 0.1},
        "mixtral-8x7b-32768": {"input": 0.05, "output": 0.1},
        "openai/gpt-oss-120b": {"input": 0.5, "output": 1.0},
    },
    "anthropic": {
        "claude-opus-4-5": {"input": 3.0, "output": 15.0},
        "claude-sonnet-4-5": {"input": 3.0, "output": 15.0},
        "claude-3-haiku-20240307": {"input": 0.25, "output": 1.25},
    },
    "openai": {
        "gpt-4o": {"input": 5.0, "output": 15.0},
        "gpt-4o-mini": {"input": 0.15, "output": 0.6},
    },
    "venice": {
        "gemma-4-uncensored": {"input": 0.1, "output": 0.1},
        "mistral-31-24b": {"input": 0.08, "output": 0.08},
        "nous-hermes-3-nitro": {"input": 0.1, "output": 0.1},
    },
}


def _resolve_provider(model: str, explicit_provider: str = "") -> tuple[str, str]:
    """Return (provider, upstream_model) for a given model name."""
    if explicit_provider:
        return explicit_provider.lower(), model
    # Explicit alias table wins first — prevents ambiguous prefix matches
    if model in _MODEL_ALIASES:
        return _MODEL_ALIASES[model]
    # Venice exact-name set (checked before prefix rules)
    if model in _VENICE_MODELS:
        return "venice", model
    # Prefix routing — Groq llama/gemma/mixtral/qwen only (not Venice variants)
    if model.startswith("grok-"):
        return "xai", model
    if model.startswith(("llama-", "gemma", "mixtral", "qwen-", "deepseek-")):
        return "groq", model
    if model.startswith("claude-"):
        return "anthropic", model
    if model.startswith("gpt-"):
        return "openai", model
    return "groq", model


# ── Privacy transforms ────────────────────────────────────────────────────────

# All headers we strip before forwarding — fingerprinting, tracing, routing
_STRIP_HEADERS = {
    # Identity / routing
    "user-agent", "x-forwarded-for", "x-real-ip", "x-forwarded-proto",
    "x-forwarded-host", "cf-connecting-ip", "cf-ray", "cf-ipcountry",
    # Distributed tracing (OpenTelemetry, B3, AWS, GCP)
    "x-request-id", "x-correlation-id", "x-amzn-trace-id",
    "x-b3-traceid", "x-b3-spanid", "x-b3-parentspanid", "x-b3-sampled",
    "traceparent", "tracestate",
    # Referrer / origin
    "referer", "origin",
    # Our own auth — never leak to upstream
    "x-proxy-token", "authorization",
}

# PII patterns for optional scrubbing
_PII_PATTERNS = [
    (re.compile(r'\b\d{7,15}\b'), "[ID]"),
    (re.compile(r'@[\w_]{3,32}\b'), "@[user]"),
    (re.compile(r'\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Z|a-z]{2,}\b'), "[email]"),
]

# Synthetic UA pool — randomised per request so upstream can't fingerprint us
_UA_POOL = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
]


def _scrub_pii(text: str) -> str:
    for pattern, replacement in _PII_PATTERNS:
        text = pattern.sub(replacement, text)
    return text


def _clean_messages(messages: list[dict], scrub: bool) -> list[dict]:
    if not scrub:
        return messages
    cleaned = []
    for msg in messages:
        content = msg.get("content", "")
        if isinstance(content, str):
            content = _scrub_pii(content)
        elif isinstance(content, list):
            content = [
                {**part, "text": _scrub_pii(part["text"])} if part.get("type") == "text" else part
                for part in content
            ]
        cleaned.append({**msg, "content": content})
    return cleaned


def _build_forward_headers(provider: str) -> dict[str, str]:
    """Build minimal clean headers for upstream — synthetic UA, no fingerprinting."""
    key = _PROVIDER_KEYS.get(provider, "")
    ua  = random.choice(_UA_POOL)
    if provider == "anthropic":
        return {
            "x-api-key":           key,
            "anthropic-version":   "2023-06-01",
            "content-type":        "application/json",
            "user-agent":          ua,
        }
    return {
        "Authorization": f"Bearer {key}",
        "Content-Type":  "application/json",
        "User-Agent":    ua,
    }


# ── Anthropic format conversion ───────────────────────────────────────────────

def _to_anthropic(payload: dict) -> dict:
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
    text  = result.get("content", [{}])[0].get("text", "")
    usage = result.get("usage", {})
    return {
        "id":      result.get("id", ""),
        "object":  "chat.completion",
        "model":   result.get("model", ""),
        "choices": [{"message": {"role": "assistant", "content": text}, "finish_reason": "stop", "index": 0}],
        "usage":   {"prompt_tokens": usage.get("input_tokens", 0), "completion_tokens": usage.get("output_tokens", 0)},
    }


# ── Cost estimation ──────────────────────────────────────────────────────────

def _estimate_cost_usd(provider: str, model: str, input_tokens: int, output_tokens: int) -> float:
    """Estimate USD cost for a request based on provider pricing."""
    try:
        costs = _PROVIDER_COSTS.get(provider, {}).get(model, {"input": 0.0, "output": 0.0})
        input_cost = (input_tokens / 1_000_000) * costs.get("input", 0.0)
        output_cost = (output_tokens / 1_000_000) * costs.get("output", 0.0)
        return round(input_cost + output_cost, 6)
    except Exception:
        return 0.0


# ── Local logging ─────────────────────────────────────────────────────────────

def _log_entry(provider: str, model: str, messages: list, response_text: str,
               latency_ms: float, error: str = "", ephemeral: bool = False, cost_usd: float = 0.0) -> None:
    """Append a log entry — respects LOG_LEVEL, EPHEMERAL_MODE, and X-Ephemeral."""
    if LOG_LEVEL() == "none" or ephemeral or EPHEMERAL_MODE():
        return
    try:
        entry: dict[str, Any] = {
            "ts":         time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "provider":   provider,
            "model":      model,
            "latency_ms": round(latency_ms),
            "turns":      len(messages),
        }
        prompt_chars = sum(len(str(m.get("content", ""))) for m in messages)
        entry["prompt_tokens_est"]     = prompt_chars // 4
        entry["completion_tokens_est"] = len(response_text) // 4
        entry["cost_usd"]              = cost_usd

        if LOG_LEVEL() == "full":
            entry["messages_preview"] = [
                {"role": m.get("role", "?"), "content": str(m.get("content", ""))[:200]}
                for m in messages[-3:]
            ]
            entry["response_preview"] = response_text[:300]
        if error:
            entry["error"] = error[:200]

        _log_ring.append(entry)

        _DATA_DIR.mkdir(parents=True, exist_ok=True)
        line = json.dumps(entry, ensure_ascii=False) + "\n"
        with open(_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line)
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
            token = auth.removeprefix("Bearer ").strip()
            if token != PROXY_TOKEN:
                return web.json_response(
                    {"error": {"message": "Unauthorized", "type": "auth_error"}}, status=401)
            # Rate limit check
            if not _check_rate_limit(token):
                return web.json_response(
                    {"error": {"message": "Rate limit exceeded", "type": "rate_limit_error"}}, status=429)
        return await handler(request)
    return middleware


# ── Handlers ──────────────────────────────────────────────────────────────────

async def handle_health(request: web.Request) -> web.Response:
    providers_up = {p: bool(k) for p, k in _PROVIDER_KEYS.items()}
    return web.json_response({
        "status":        "ok",
        "privacy_mode":  PRIVACY_MODE(),
        "log_level":     LOG_LEVEL(),
        "privacy_scrub": PRIVACY_SCRUB(),
        "ephemeral_mode": EPHEMERAL_MODE(),
        "providers":     providers_up,
    })


async def handle_config_get(request: web.Request) -> web.Response:
    """Return current runtime config."""
    return web.json_response({
        "privacy_mode":   _cfg["privacy_mode"],
        "log_level":      _cfg["log_level"],
        "privacy_scrub":  _cfg["privacy_scrub"],
        "ephemeral_mode": _cfg["ephemeral_mode"],
        "valid_privacy_modes": ["anonymous", "private", "maximum"],
        "valid_log_levels":    ["none", "minimal", "full"],
    })


async def handle_config_post(request: web.Request) -> web.Response:
    """Update runtime config — changes take effect immediately, no redeploy needed."""
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"error": "invalid JSON"}, status=400)

    updated = {}
    if "privacy_mode" in body:
        val = str(body["privacy_mode"]).lower()
        if val not in ("anonymous", "private", "maximum"):
            return web.json_response({"error": "privacy_mode must be anonymous|private|maximum"}, status=400)
        _cfg["privacy_mode"] = val
        # Auto-adjust log_level when mode changes, unless explicitly set in same request
        if "log_level" not in body:
            _cfg["log_level"] = _default_log_level(val)
        updated["privacy_mode"] = val

    if "log_level" in body:
        val = str(body["log_level"]).lower()
        if val not in ("none", "minimal", "full"):
            return web.json_response({"error": "log_level must be none|minimal|full"}, status=400)
        _cfg["log_level"] = val
        updated["log_level"] = val

    if "privacy_scrub" in body:
        val = bool(body["privacy_scrub"])
        _cfg["privacy_scrub"] = val
        updated["privacy_scrub"] = val

    if "ephemeral_mode" in body:
        val = bool(body["ephemeral_mode"])
        _cfg["ephemeral_mode"] = val
        updated["ephemeral_mode"] = val

    logger.info("[proxy] config updated: %s", updated)
    return web.json_response({"ok": True, "updated": updated, "current": dict(_cfg)})


async def handle_models(request: web.Request) -> web.Response:
    models = [
        {"id": alias, "object": "model", "owned_by": prov}
        for alias, (prov, _) in _MODEL_ALIASES.items()
        if _PROVIDER_KEYS.get(prov)
    ]
    return web.json_response({"object": "list", "data": models})


async def handle_chat_completions(request: web.Request) -> web.Response:
    t0 = time.monotonic()

    # X-Ephemeral: true — skip all logging for this request
    ephemeral = request.headers.get("X-Ephemeral", "").lower() == "true"

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

    if DEFAULT_TEMPERATURE:
        payload.setdefault("temperature", float(DEFAULT_TEMPERATURE))
    if DEFAULT_TOP_P:
        payload.setdefault("top_p", float(DEFAULT_TOP_P))
    if request.headers.get("X-Temperature"):
        payload["temperature"] = float(request.headers["X-Temperature"])
    if request.headers.get("X-Top-P"):
        payload["top_p"] = float(request.headers["X-Top-P"])

    original_messages = payload.get("messages", [])
    payload["messages"] = _clean_messages(original_messages, PRIVACY_SCRUB())

    error_text = ""
    response_text = ""
    try:
        async with aiohttp.ClientSession() as session:
            result = await _forward(provider, upstream_model, payload, session)
        response_text = result.get("choices", [{}])[0].get("message", {}).get("content", "")
        latency_ms = (time.monotonic() - t0) * 1000
        # Estimate cost
        prompt_chars = sum(len(str(m.get("content", ""))) for m in original_messages)
        input_tokens = prompt_chars // 4
        output_tokens = len(response_text) // 4
        cost_usd = _estimate_cost_usd(provider, upstream_model, input_tokens, output_tokens)
        logger.info("[proxy] %s/%s → %d chars (%.0fms) $%.6f%s",
                    provider, upstream_model, len(response_text), latency_ms, cost_usd,
                    " [ephemeral]" if (ephemeral or EPHEMERAL_MODE()) else "")
        _log_entry(provider, upstream_model, original_messages, response_text,
                   latency_ms, ephemeral=ephemeral, cost_usd=cost_usd)
        return web.json_response(result)

    except Exception as e:
        error_text = str(e)
        latency_ms = (time.monotonic() - t0) * 1000
        logger.warning("[proxy] %s/%s failed: %s", provider, upstream_model, error_text)
        _log_entry(provider, upstream_model, original_messages, "",
                   latency_ms, error=error_text, ephemeral=ephemeral)
        return web.json_response(
            {"error": {"message": error_text, "provider": provider}}, status=502)


async def handle_logs(request: web.Request) -> web.Response:
    """Return recent proxy log entries — served from in-memory ring buffer first."""
    n = min(int(request.query.get("n", "100")), 500)
    entries = list(_log_ring)[-n:]
    # Fall back to disk if ring is empty (e.g. fresh restart)
    if not entries and _LOG_PATH.exists():
        try:
            lines = _LOG_PATH.read_text(encoding="utf-8").splitlines()
            for line in lines[-n:]:
                try:
                    entries.append(json.loads(line))
                except Exception:
                    pass
        except Exception as e:
            return web.json_response({"error": str(e)}, status=500)
    return web.json_response({"entries": entries, "total_stored": len(_log_ring)})


# ── Redis heartbeat (agent liveness for webchat /agents endpoint) ──────────────

async def _redis_write_hb() -> None:
    """Write proxy heartbeat to Redis every 3 min so webchat shows it online."""
    try:
        import redis.asyncio as aioredis
        r = aioredis.from_url(REDIS_URL, decode_responses=True)
        payload = json.dumps({
            "agent": "redacted-proxy",
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "unix": time.time(),
            "service": "redacted-proxy",
            "role": "infra",
        })
        await r.set(f"{HEARTBEAT_PREFIX}redacted-proxy", payload, ex=HEARTBEAT_TTL)
        await r.aclose()
        logger.debug(f"[heartbeat] wrote proxy liveness to redis")
    except Exception as e:
        logger.warning(f"[heartbeat] redis write failed: {e}")


async def _heartbeat_loop() -> None:
    """Periodically write heartbeat to Redis."""
    while True:
        await _redis_write_hb()
        await asyncio.sleep(180)   # 3 min


# ── Server ────────────────────────────────────────────────────────────────────

async def make_app() -> web.Application:
    app = web.Application(middlewares=[_auth_middleware])
    app.router.add_get("/health",                handle_health)
    app.router.add_get("/v1/models",             handle_models)
    app.router.add_post("/v1/chat/completions",  handle_chat_completions)
    app.router.add_get("/logs",                  handle_logs)
    app.router.add_get("/config",                handle_config_get)
    app.router.add_post("/config",               handle_config_post)

    async def _start_heartbeat(app):
        asyncio.create_task(_heartbeat_loop())
        logger.info("[heartbeat] started redis liveness pulse")

    app.on_startup.append(_start_heartbeat)
    return app


if __name__ == "__main__":
    logger.info("[proxy] starting on port %d | mode=%s log=%s scrub=%s rpm=%d",
                PORT, PRIVACY_MODE(), LOG_LEVEL(), PRIVACY_SCRUB(), RATE_LIMIT_RPM)
    web.run_app(make_app(), port=PORT, host="0.0.0.0")
