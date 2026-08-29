# redacted-proxy/main.py
"""
redacted-proxy — OpenAI-compatible LLM privacy proxy.

Philosophy (inspired by Venice.ai): "You don't have to protect what you do not have."
The proxy's primary job is to ensure upstream providers learn as little as possible
about who is talking to them and what they're saying.

A transparent relay layer sitting between REDACTED swarm bots and upstream LLM providers.
Exposes an OpenAI-compatible API so any client (redacted-chan-bot, smolting, webchat)
can point at it without code changes — just change the base URL and bearer token.

Endpoints:
  POST /v1/chat/completions   — main proxy endpoint (OpenAI-compatible)
  GET  /v1/models             — list available model aliases
  GET  /health                — liveness + provider key status
  GET  /privacy               — current privacy mode, guarantees, what's stored
  GET  /logs                  — recent proxy log (admin auth required)
  GET  /config                — current runtime config
  POST /config                — hot-update config without redeploy

Provider routing (by model name prefix or X-Provider header):
  grok-*          → xAI (api.x.ai)
  llama-*, gemma-*, mixtral-*, qwen-* → Groq (api.groq.com)
  claude-*        → Anthropic
  gpt-*           → OpenAI
  Venice exact names → Venice (api.venice.ai)
  PREFER_VENICE=true → Venice preferred in private/maximum modes

Privacy modes (PRIVACY_MODE env var, default: private):
  anonymous  — strip fingerprinting headers + synthetic UA; full logging possible
  private    — anonymous + metadata-only logging + PII scrub on; disk log opt-in
  maximum    — private + no disk logging ever + memory ring buffer with TTL auto-purge
  zero       — alias for maximum
  tee        — future: route to TEE providers (currently behaves like maximum)
  e2ee       — future: client-side encryption hints (currently behaves like maximum)

Privacy transforms applied before forwarding:
  - Strip all fingerprinting / tracing / routing / browser-telemetry headers
  - Synthetic randomised User-Agent + Accept-Language so upstream can't fingerprint us
  - Optional PII regex scrub of message content (on by default in private/maximum)
  - X-Ephemeral or X-Transient header disables logging for that request entirely
  - Client Authorization header never forwarded upstream

Logging (LOG_LEVEL env var, defaults by mode):
  none     — no disk writes, no ring buffer entries
  minimal  — metadata only: ts, provider, model, latency, token estimates (default in private/max)
  full     — minimal + truncated message previews (default in anonymous only)

Ring buffer TTL (RING_BUFFER_TTL env var, seconds):
  maximum/zero: 300s default — entries auto-purged after 5 minutes
  private:      3600s default — entries auto-purged after 1 hour
  anonymous:    0 (unlimited)

Disk logging (DISK_LOG env var):
  anonymous: true by default
  private:   false by default (opt-in via DISK_LOG=true)
  maximum:   always false, env var ignored

Environment variables:
  PROXY_TOKEN         — bearer token clients must present (required)
  XAI_API_KEY         — xAI upstream key
  GROQ_API_KEY        — Groq upstream key
  ANTHROPIC_API_KEY   — Anthropic upstream key
  OPENAI_API_KEY      — OpenAI upstream key
  VENICE_API_KEY      — Venice upstream key
  PRIVACY_MODE        — anonymous|private|maximum|zero|tee|e2ee (default: private)
  PRIVACY_SCRUB       — "true"/"false" (default: true in private/max, false in anonymous)
  DISK_LOG            — "true"/"false" (default: false in private/max, true in anonymous)
  RING_BUFFER_TTL     — seconds before ring entries are purged (0 = unlimited)
  PREFER_VENICE       — "true" to prefer Venice for private/maximum modes when model matches
  EPHEMERAL_MODE      — "true" to disable all logging globally
  LOG_LEVEL           — none|minimal|full (overrides mode default)
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

try:
    from aiohttp_socks import ProxyConnector
except ImportError:  # optional dep — only required when UPSTREAM_PROXY is set
    ProxyConnector = None

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [proxy] %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────

PROXY_TOKEN         = os.getenv("PROXY_TOKEN", "")
# Name attributed to requests that authenticate with the legacy shared PROXY_TOKEN and
# send no X-Client header. As projects migrate to their own tokens (PROXY_TOKEN_MAP) or
# start sending X-Client, their traffic splits out of this bucket.
PROXY_TOKEN_NAME    = os.getenv("PROXY_TOKEN_NAME", "shared").strip() or "shared"
# Per-project bearer tokens: JSON {"<token>": "<project_name>"}. Each mapped token both
# authenticates AND attributes usage to its project. The shared PROXY_TOKEN still works.
def _load_token_map() -> dict[str, str]:
    raw = os.getenv("PROXY_TOKEN_MAP", "").strip()
    if not raw:
        return {}
    try:
        m = json.loads(raw)
        return {str(k): str(v) for k, v in m.items() if k and v}
    except Exception:
        logger.warning("[proxy] PROXY_TOKEN_MAP invalid JSON — ignoring")
        return {}
_TOKEN_MAP = _load_token_map()
# Admin token for /usage mutations (reset). Defaults to the shared PROXY_TOKEN.
ADMIN_TOKEN         = os.getenv("ADMIN_TOKEN", "").strip() or PROXY_TOKEN
# Per-project usage accounting (requests/tokens/cost) in Redis. Metadata only — no
# prompt/response content — so it is compatible with every privacy mode.
USAGE_ENABLED       = os.getenv("USAGE_ENABLED", "true").lower() not in ("false", "0", "no")
USAGE_PREFIX        = os.getenv("USAGE_PREFIX", "proxy:usage:")
USAGE_DAILY_TTL_DAYS = int(os.getenv("USAGE_DAILY_TTL_DAYS", "90"))
DEFAULT_TEMPERATURE = os.getenv("DEFAULT_TEMPERATURE", "")
DEFAULT_TOP_P       = os.getenv("DEFAULT_TOP_P", "")
RATE_LIMIT_RPM      = int(os.getenv("RATE_LIMIT_RPM", "60"))
PORT                = int(os.getenv("PORT", "7080"))
REDIS_URL           = os.getenv("REDIS_URL", "redis://localhost:6379")
HEARTBEAT_PREFIX    = "swarm:heartbeat:"
HEARTBEAT_TTL       = 600   # 10 min — proxy announces every 3 min so key stays fresh

# Upstream egress proxy — when set, ALL outbound calls to LLM providers are
# routed through this proxy (e.g. socks5h://127.0.0.1:1080 → ss-local →
# mullvad-ch → Mullvad exit) so provider traffic never leaves on the host's
# home IP. socks5h/rdns keeps DNS inside the tunnel (no leak). Empty = direct.
UPSTREAM_PROXY      = os.getenv("UPSTREAM_PROXY", "").strip()

# Providers that must egress DIRECT (bypassing UPSTREAM_PROXY / the Mullvad exit),
# because their edge (Cloudflare) blocks VPN/datacenter IPs. Groq returns
# 403 {"message":"Access denied. Please check your network settings."} for the
# Mullvad exit while the home IP reaches it fine, so Groq egresses direct. Content
# is still PII-scrubbed before forwarding. Comma-separated provider names; add
# "xai" here if xAI proves blocked too. Only matters when UPSTREAM_PROXY is set.
DIRECT_EGRESS_PROVIDERS = {p.strip() for p in
                           os.getenv("DIRECT_EGRESS_PROVIDERS", "groq").split(",") if p.strip()}

# Reasoning effort cap for Groq gpt-oss models — they otherwise burn the whole token
# budget on hidden reasoning and return empty content at the swarm's modest max_tokens.
# "low" leaves room for the answer. Empty string disables the injection.
GROQ_REASONING_EFFORT = os.getenv("GROQ_REASONING_EFFORT", "low").strip()

# Modes that always enforce maximum privacy (no disk, forced scrub)
_MAX_PRIVACY_MODES = {"maximum", "zero", "tee", "e2ee"}


def _is_max_privacy(mode: str) -> bool:
    return mode in _MAX_PRIVACY_MODES


def _default_log_level(privacy_mode: str) -> str:
    env = os.getenv("LOG_LEVEL", "").lower()
    if not env and os.getenv("LOG_CONTENT", "").lower() == "false":
        env = "minimal"
    if env in ("none", "minimal", "full"):
        return env
    if _is_max_privacy(privacy_mode) or privacy_mode == "private":
        return "minimal"
    return "full"  # anonymous


def _default_disk_log(privacy_mode: str) -> bool:
    env = os.getenv("DISK_LOG", "").lower()
    if env == "true":
        return True
    if env == "false":
        return False
    # maximum/zero/tee/e2ee: never write to disk
    if _is_max_privacy(privacy_mode):
        return False
    # private: opt-in — default off
    if privacy_mode == "private":
        return False
    # anonymous: on by default (backward compat)
    return True


def _default_scrub(privacy_mode: str) -> bool:
    env = os.getenv("PRIVACY_SCRUB", "").lower()
    if env == "true":
        return True
    if env == "false":
        return False
    # Scrub on by default for all modes except anonymous
    return privacy_mode != "anonymous"


def _default_ring_ttl(privacy_mode: str) -> int:
    env = os.getenv("RING_BUFFER_TTL", "")
    if env.isdigit():
        return int(env)
    if _is_max_privacy(privacy_mode):
        return 300   # 5 minutes
    if privacy_mode == "private":
        return 3600  # 1 hour
    return 0         # unlimited for anonymous


_raw_mode = os.getenv("PRIVACY_MODE", "private").lower()

_cfg: dict = {
    "privacy_mode":   _raw_mode,
    "privacy_scrub":  _default_scrub(_raw_mode),
    "ephemeral_mode": os.getenv("EPHEMERAL_MODE", "false").lower() == "true",
    "disk_log":       _default_disk_log(_raw_mode),
    "ring_buffer_ttl": _default_ring_ttl(_raw_mode),
    "prefer_venice":  os.getenv("PREFER_VENICE", "false").lower() == "true",
    "log_level":      "",   # filled below
}
_cfg["log_level"] = _default_log_level(_cfg["privacy_mode"])

# Shorthands used internally
def PRIVACY_MODE()   -> str:  return _cfg["privacy_mode"]
def PRIVACY_SCRUB()  -> bool: return _cfg["privacy_scrub"]
def EPHEMERAL_MODE() -> bool: return _cfg["ephemeral_mode"]
def DISK_LOG()       -> bool: return _cfg["disk_log"]
def LOG_LEVEL()      -> str:  return _cfg["log_level"]
def RING_TTL()       -> int:  return _cfg["ring_buffer_ttl"]
def PREFER_VENICE()  -> bool: return _cfg["prefer_venice"]

_DATA_DIR  = Path("/data") if Path("/data").exists() else Path(__file__).parent / "data"
_LOG_PATH  = _DATA_DIR / "proxy_log.jsonl"
_LOG_MAX   = 5000   # entries before rotation

# In-memory ring buffer (last 500 entries) — avoids disk reads on /logs
# Entries are dicts; ts_unix field used for TTL purge
_log_ring: collections.deque = collections.deque(maxlen=500)

# ── Privacy guarantees descriptor ─────────────────────────────────────────────

_PRIVACY_GUARANTEES: dict[str, dict] = {
    "anonymous": {
        "description": "Header stripping + synthetic User-Agent. Full logging possible.",
        "stores_prompts": True,
        "stores_responses": True,
        "disk_log_default": True,
        "pii_scrub_default": False,
        "ring_buffer_ttl_default": "unlimited",
        "upstream_provider_sees": "synthetic UA, no client IP, no trace headers",
        "threat_model": "Defends against upstream provider fingerprinting. Logs on disk.",
    },
    "private": {
        "description": "Header stripping + synthetic UA + metadata-only logging + PII scrub on. No disk logging by default.",
        "stores_prompts": False,
        "stores_responses": False,
        "disk_log_default": False,
        "pii_scrub_default": True,
        "ring_buffer_ttl_default": "3600s",
        "upstream_provider_sees": "synthetic UA, no client IP, no trace headers, PII-scrubbed content",
        "threat_model": "Defends against upstream provider fingerprinting and local log exfiltration. Metadata only in ring buffer.",
    },
    "maximum": {
        "description": "No disk logging ever. Memory ring buffer with 5-min TTL. PII scrub forced on.",
        "stores_prompts": False,
        "stores_responses": False,
        "disk_log_default": False,
        "pii_scrub_default": True,
        "ring_buffer_ttl_default": "300s",
        "upstream_provider_sees": "synthetic UA, no client IP, no trace headers, PII-scrubbed content",
        "threat_model": "Maximum ephemeral-by-default. No persistent storage of any request data. Ring buffer auto-purges after 5 minutes.",
    },
    "zero": {
        "description": "Alias for maximum — zero storage philosophy.",
        "stores_prompts": False,
        "stores_responses": False,
        "disk_log_default": False,
        "pii_scrub_default": True,
        "ring_buffer_ttl_default": "300s",
        "upstream_provider_sees": "synthetic UA, no client IP, no trace headers, PII-scrubbed content",
        "threat_model": "Identical to maximum. Zero storage. Ring buffer auto-purges after 5 minutes.",
    },
    "tee": {
        "description": "[Future] Route to Trusted Execution Environment providers. Currently behaves like maximum.",
        "stores_prompts": False,
        "stores_responses": False,
        "disk_log_default": False,
        "pii_scrub_default": True,
        "ring_buffer_ttl_default": "300s",
        "upstream_provider_sees": "synthetic UA only; TEE attestation in future",
        "threat_model": "Future: hardware-attested confidential compute. Current: equivalent to maximum.",
        "note": "TEE routing not yet implemented — behaves identically to maximum mode.",
    },
    "e2ee": {
        "description": "[Future] End-to-end encrypted client sessions. Currently behaves like maximum.",
        "stores_prompts": False,
        "stores_responses": False,
        "disk_log_default": False,
        "pii_scrub_default": True,
        "ring_buffer_ttl_default": "300s",
        "upstream_provider_sees": "encrypted payload; provider cannot read content",
        "threat_model": "Future: client-side encryption so even proxy operator cannot read prompts. Current: equivalent to maximum.",
        "note": "E2EE not yet implemented — behaves identically to maximum mode.",
    },
}

# ── Rate limiting ─────────────────────────────────────────────────────────────

_rate_buckets: dict[str, collections.deque] = {}


def _check_rate_limit(token: str) -> bool:
    """Return True if request is allowed, False if rate limited."""
    if RATE_LIMIT_RPM <= 0:
        return True
    now = time.monotonic()
    window = 60.0
    bucket = _rate_buckets.setdefault(token, collections.deque())
    while bucket and now - bucket[0] > window:
        bucket.popleft()
    if len(bucket) >= RATE_LIMIT_RPM:
        return False
    bucket.append(now)
    return True


# ── Provider routing ──────────────────────────────────────────────────────────

_PROVIDER_URLS = {
    "xai":        "https://api.x.ai/v1/chat/completions",
    "groq":       "https://api.groq.com/openai/v1/chat/completions",
    "anthropic":  "https://api.anthropic.com/v1/messages",
    "openai":     "https://api.openai.com/v1/chat/completions",
    "venice":     "https://api.venice.ai/api/v1/chat/completions",
    "openrouter": "https://openrouter.ai/api/v1/chat/completions",
}

_PROVIDER_KEYS = {
    "xai":        os.getenv("XAI_API_KEY", ""),
    "groq":       os.getenv("GROQ_API_KEY", ""),
    "anthropic":  os.getenv("ANTHROPIC_API_KEY", ""),
    "openai":     os.getenv("OPENAI_API_KEY", ""),
    "venice":     os.getenv("VENICE_API_KEY", ""),
    "openrouter": os.getenv("OPENROUTER_API_KEY", ""),
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
    "llama-3-3-70b",   # Venice's own llama build (different from Groq's)
})

# Venice equivalents — used when PREFER_VENICE=true in private/maximum modes
# Maps Groq/xAI model names to nearest Venice equivalent
_VENICE_PREFER_MAP: dict[str, str] = {
    "llama-3.3-70b-versatile": "llama-3-3-70b",
    "llama-3.3-70b":           "llama-3-3-70b",
    "mixtral-8x7b-32768":      "mistral-31-24b",
    "mixtral-8x7b":            "mistral-31-24b",
}

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
    "qwen/qwen3.6-27b":         ("groq",      "qwen/qwen3.6-27b"),
    # Anthropic
    "claude-haiku":             ("anthropic", "claude-3-haiku-20240307"),
    "claude-sonnet":            ("anthropic", "claude-sonnet-4-5"),
    "claude-opus":              ("anthropic", "claude-opus-4-5"),
    "claude-3-haiku-20240307":  ("anthropic", "claude-3-haiku-20240307"),
    # OpenAI
    "gpt-4o":                   ("openai",    "gpt-4o"),
    "gpt-4o-mini":              ("openai",    "gpt-4o-mini"),
    # Venice aliases
    "gemma-4-uncensored":                ("venice", "gemma-4-uncensored"),
    "mistral-31-24b":                    ("venice", "mistral-31-24b"),
    "mistral-small-3-2-24b-instruct":    ("venice", "mistral-small-3-2-24b-instruct"),
    "venice-uncensored":                 ("venice", "venice-uncensored"),
    "nous-hermes-3-nitro":               ("venice", "nous-hermes-3-nitro"),
    "lfm-40b":                           ("venice", "lfm-40b"),
    "llama-3-3-70b":                     ("venice", "llama-3-3-70b"),
}

# Failover cascade when primary provider is unavailable
_MODEL_EQUIVALENTS: dict[str, list[str]] = {
    # deepseek (OpenRouter primary) → Groq → Venice → xAI, in order of availability
    "deepseek/deepseek-v4-flash": ["openai/gpt-oss-120b", "openai/gpt-oss-20b", "llama-3-3-70b"],
    "grok-4-1-fast":             ["openai/gpt-oss-120b", "claude-opus", "gpt-4o"],
    "grok-3-fast":               ["openai/gpt-oss-120b", "gemma-4-uncensored"],
    "llama-3.3-70b":             ["llama-3-3-70b", "gpt-4o", "claude-opus"],
    "claude-opus":               ["gpt-4o", "openai/gpt-oss-120b"],
    "claude-sonnet":             ["gpt-4o", "openai/gpt-oss-20b"],
    "claude-haiku":              ["gpt-4o-mini", "openai/gpt-oss-20b"],
    "gpt-4o":                    ["claude-opus", "openai/gpt-oss-120b"],
    "gpt-4o-mini":               ["claude-haiku", "openai/gpt-oss-20b"],
    "gemma-4-uncensored":        ["openai/gpt-oss-120b", "gpt-4o"],
    "nous-hermes-3-nitro":       ["openai/gpt-oss-120b", "gpt-4o"],
}

# Free-first cascade — tried in order before the originally-requested (paid) model.
# Groq free tier is per-model, so budgets stack; ordered by daily budget (8b-instant
# is the volume workhorse at 500K tok/day). OpenRouter ":free" ids follow. The list is
# env-overridable because the OpenRouter free lineup rotates — validate ids against
# https://openrouter.ai/api/v1/models when updating.
# NOTE: this key's Groq lineup no longer includes the llama-3.x / gemma small models
# (they 404 as model_not_found); the live Groq chat models are gpt-oss-{20b,120b} and
# qwen3.6-27b. Keep only live ids here so the cascade doesn't burn round-trips on 404s.
_FREE_CASCADE: list[str] = [m.strip() for m in os.getenv("FREE_CASCADE",
    "openai/gpt-oss-20b,openai/gpt-oss-120b,qwen/qwen3.6-27b,"
    "cohere/north-mini-code:free"
).split(",") if m.strip()]

# Groq's on_demand tier caps tokens-per-minute per model. The swarm's full-context
# prompts run right at the ceiling, so an oversized request fails identically on every
# Groq model — the cheapest fix is not to dial Groq at all when the prompt is clearly
# over. Set to 0 to disable the pre-flight guard.
GROQ_TPM_LIMIT = int(os.getenv("GROQ_TPM_LIMIT", "8000"))

# A provider that is out of credits, or whose key is unauthorized, will be in the same
# state on the next request. Remember such failures for the process lifetime (or
# PROVIDER_COOLDOWN_S) instead of rediscovering them one wasted round-trip at a time.
# This is deliberately provider-level and pattern-based: hardcoding dead model ids is
# what let them hide in _MODEL_EQUIVALENTS after two separate prunes.
PROVIDER_COOLDOWN_S = int(os.getenv("PROVIDER_COOLDOWN_S", "900"))
_PROVIDER_COOLDOWN: dict[str, float] = {}

# Substrings that mean "this provider is unusable right now", as opposed to a transient
# or request-specific failure. Matched case-insensitively against the upstream error.
_HARD_PROVIDER_FAILURES = (
    "used all available credits",
    "monthly spending limit",
    "insufficient_quota",
    "invalid_api_key",
    "unauthorized",
)


def _is_hard_provider_failure(error_text: str) -> bool:
    low = error_text.lower()
    return any(sig in low for sig in _HARD_PROVIDER_FAILURES)


def _provider_in_cooldown(provider: str) -> bool:
    until = _PROVIDER_COOLDOWN.get(provider)
    if until is None:
        return False
    if time.time() >= until:
        del _PROVIDER_COOLDOWN[provider]
        return False
    return True


def _estimate_prompt_tokens(payload: dict) -> int:
    """Conservative chars/4 estimate over messages + tool definitions.

    Deliberately an under-estimate (it ignores role and template overhead), so the
    pre-flight guard only ever skips a provider when the prompt is clearly over the
    limit — a false skip would cost us a healthy free model.
    """
    chars = 0
    for m in payload.get("messages") or []:
        c = m.get("content")
        chars += len(c) if isinstance(c, str) else len(str(c))
    if payload.get("tools"):
        chars += len(json.dumps(payload["tools"]))
    return chars // 4


# Models that should be served free-first (the swarm's standardized defaults). When a
# request names one of these and pins no explicit provider, the free cascade is prepended
# ahead of it, so the paid model is only reached as a genuine last resort.
_CASCADE_MODELS: set[str] = {m.strip() for m in os.getenv("CASCADE_MODELS",
    "deepseek/deepseek-v4-flash").split(",") if m.strip()}

# ── Auto-router ───────────────────────────────────────────────────────────────
# When a request's model is in _AUTO_MODELS, the proxy inspects the prompt, estimates
# difficulty (heuristics, plus a cheap classifier only for the ambiguous middle band),
# and enters the free-first cascade at the cheapest capable tier (cost-first). Opt-in and
# non-breaking: bots send model:"auto"; every other model id behaves exactly as before.
_AUTO_MODELS: set[str] = {m.strip() for m in os.getenv("AUTO_MODELS", "auto").split(",") if m.strip()}
# Empty by default: no cheap non-reasoning model is currently available to act as a
# 1-token difficulty classifier (Groq's llama/gemma small models were removed from the
# key's lineup; the remaining Groq gpt-oss/qwen models are reasoning models that emit
# empty content at tiny budgets; OpenRouter free is daily-rate-limited). With no model
# set, the ambiguous middle band takes the medium tier directly. Set to a non-reasoning
# model id to re-enable classification.
_AUTO_CLASSIFIER_MODEL = os.getenv("AUTO_CLASSIFIER_MODEL", "")
# Score bands: <= EASY_MAX → easy; >= HARD_MIN → hard; in between → classifier decides.
_AUTO_EASY_MAX = int(os.getenv("AUTO_EASY_MAX", "3"))
_AUTO_HARD_MIN = int(os.getenv("AUTO_HARD_MIN", "8"))

def _auto_tiers() -> dict[str, list[str]]:
    raw = os.getenv("AUTO_TIERS", "")
    if raw:
        try:
            return json.loads(raw)
        except Exception:
            logger.warning("[proxy] AUTO_TIERS invalid JSON — using defaults")
    # Cost-first: cheapest capable free model first in each tier. All tiers share the
    # free-cascade tail + paid last resort (appended in _build_auto_chain).
    return {
        "easy":   ["openai/gpt-oss-20b", "qwen/qwen3.6-27b"],
        "medium": ["openai/gpt-oss-120b", "openai/gpt-oss-20b", "qwen/qwen3.6-27b"],
        "hard":   ["openai/gpt-oss-120b", "qwen/qwen3.6-27b"],
        "code":   ["cohere/north-mini-code:free", "openai/gpt-oss-120b"],
    }
_AUTO_TIERS = _auto_tiers()

# Prompt signals for the zero-cost heuristic pass.
_CODE_SIGNALS = ("```", "def ", "function ", "class ", "import ", "traceback", "stack trace",
                 "refactor", "compile", "syntax error", "npm ", "git ", "regex", "sql")
_REASON_SIGNALS = ("prove", "step by step", "step-by-step", "analyz", "analyse", "derive",
                   "reason", "explain why", "algorithm", "complexity", "optimize", "trade-off")
_STRUCT_SIGNALS = ("json", "schema", "yaml", "csv", "table of", "format:")

# Provider pricing (USD per 1M tokens) — estimated; used for cost tracking
_PROVIDER_COSTS: dict[str, dict[str, float]] = {
    "xai": {
        "grok-4-1-fast": {"input": 5.0, "output": 15.0},
        "grok-3-fast": {"input": 1.5, "output": 6.0},
        "grok-3": {"input": 1.0, "output": 4.0},
    },
    "groq": {
        # Free-tier on Groq's Free plan → $0; kept explicit so log lines read $0 on free hits.
        "llama-3.3-70b-versatile": {"input": 0.0, "output": 0.0},
        "llama-3.1-8b-instant": {"input": 0.0, "output": 0.0},
        "gemma2-9b-it": {"input": 0.0, "output": 0.0},
        "mixtral-8x7b-32768": {"input": 0.05, "output": 0.1},
        "openai/gpt-oss-120b": {"input": 0.0, "output": 0.0},
        "openai/gpt-oss-20b": {"input": 0.0, "output": 0.0},
        "qwen/qwen3.6-27b": {"input": 0.0, "output": 0.0},
    },
    "openrouter": {
        # ":free" ids are billed at $0 by OpenRouter.
        "nvidia/nemotron-3.5-lightning:free": {"input": 0.0, "output": 0.0},
        "cohere/north-mini-code:free": {"input": 0.0, "output": 0.0},
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
        "llama-3-3-70b": {"input": 0.05, "output": 0.1},
        "venice-uncensored": {"input": 0.1, "output": 0.1},
    },
}


def _resolve_provider(model: str, explicit_provider: str = "") -> tuple[str, str]:
    """Return (provider, upstream_model) for a given model name."""
    if explicit_provider:
        return explicit_provider.lower(), model

    # Explicit alias table wins first
    if model in _MODEL_ALIASES:
        provider, upstream = _MODEL_ALIASES[model]
        # Venice preference: if private/maximum and PREFER_VENICE and Venice has this model
        if PREFER_VENICE() and _is_max_privacy_or_private() and provider != "venice":
            venice_alt = _VENICE_PREFER_MAP.get(upstream) or _VENICE_PREFER_MAP.get(model)
            if venice_alt and _PROVIDER_KEYS.get("venice"):
                return "venice", venice_alt
        return provider, upstream

    # Venice exact-name set
    if model in _VENICE_MODELS:
        return "venice", model

    # OpenRouter uses org/model ids (e.g. "deepseek/deepseek-v4-flash",
    # "meta-llama/llama-3.1-70b"). Any slash-form id not explicitly aliased above
    # routes to OpenRouter.
    if "/" in model:
        return "openrouter", model

    # Prefix routing
    if model.startswith("grok-"):
        return "xai", model
    if model.startswith(("llama-", "gemma", "mixtral", "qwen-", "deepseek-")):
        # Venice preference for llama/mixtral in private modes
        if PREFER_VENICE() and _is_max_privacy_or_private():
            venice_alt = _VENICE_PREFER_MAP.get(model)
            if venice_alt and _PROVIDER_KEYS.get("venice"):
                return "venice", venice_alt
        return "groq", model
    if model.startswith("claude-"):
        return "anthropic", model
    if model.startswith("gpt-"):
        return "openai", model
    return "groq", model


def _is_max_privacy_or_private() -> bool:
    return PRIVACY_MODE() in {"private", "maximum", "zero", "tee", "e2ee"}


# ── Privacy transforms ────────────────────────────────────────────────────────

# All headers we strip before forwarding — fingerprinting, tracing, routing, browser telemetry
_STRIP_HEADERS = {
    # Identity / routing
    "user-agent", "x-forwarded-for", "x-real-ip", "x-forwarded-proto",
    "x-forwarded-host", "x-forwarded-port", "x-forwarded-scheme",
    "cf-connecting-ip", "cf-ray", "cf-ipcountry", "cf-visitor",
    # Distributed tracing (OpenTelemetry, B3, AWS, GCP, Datadog)
    "x-request-id", "x-correlation-id", "x-amzn-trace-id",
    "x-b3-traceid", "x-b3-spanid", "x-b3-parentspanid", "x-b3-sampled",
    "traceparent", "tracestate",
    "x-datadog-trace-id", "x-datadog-parent-id", "x-datadog-sampling-priority",
    # Browser telemetry / fingerprinting
    "accept-language", "accept-encoding", "accept-charset",
    "dnt", "sec-gpc",
    "sec-ch-ua", "sec-ch-ua-mobile", "sec-ch-ua-platform", "sec-ch-ua-arch",
    "sec-ch-ua-full-version", "sec-ch-ua-full-version-list",
    "sec-fetch-dest", "sec-fetch-mode", "sec-fetch-site", "sec-fetch-user",
    # Referrer / origin / cache hints
    "referer", "origin", "via", "x-cache", "x-cache-hits",
    # Our own auth — never leak to upstream
    "x-proxy-token", "authorization",
    # Misc routing
    "x-real-scheme", "x-envoy-external-address", "x-cluster-client-ip",
}

# PII patterns for optional scrubbing
_PII_PATTERNS = [
    (re.compile(r'\b\d{7,15}\b'), "[ID]"),
    (re.compile(r'@[\w_]{3,32}\b'), "@[user]"),
    (re.compile(r'\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Z|a-z]{2,}\b'), "[email]"),
    (re.compile(r'\b(?:\d{4}[- ]?){3}\d{4}\b'), "[card]"),  # credit card-like
    (re.compile(r'\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b'), "[phone]"),  # US phone
]

# Expanded synthetic UA pool — browser-like, diverse, randomized per request
_UA_POOL = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (X11; Linux x86_64; rv:126.0) Gecko/20100101 Firefox/126.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:124.0) Gecko/20100101 Firefox/124.0",
    "Mozilla/5.0 (Windows NT 11.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 Edg/124.0.0.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4_1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
]

# Accept-Language pool — randomized to prevent fingerprinting via language preference
_ACCEPT_LANG_POOL = [
    "en-US,en;q=0.9",
    "en-GB,en;q=0.9",
    "en-US,en;q=0.8,es;q=0.5",
    "en-US,en;q=0.9,fr;q=0.7",
    "en-AU,en;q=0.9",
    "en-CA,en;q=0.9,fr-CA;q=0.6",
    "en-US,en;q=0.9,de;q=0.6",
    "en-US,en;q=0.8",
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
    """Build minimal clean headers for upstream — synthetic UA + Accept-Language, no fingerprinting."""
    key = _PROVIDER_KEYS.get(provider, "")
    ua  = random.choice(_UA_POOL)
    lang = random.choice(_ACCEPT_LANG_POOL)
    if provider == "anthropic":
        return {
            "x-api-key":           key,
            "anthropic-version":   "2023-06-01",
            "content-type":        "application/json",
            "user-agent":          ua,
            "accept-language":     lang,
        }
    if provider == "openrouter":
        return {
            "Authorization":   f"Bearer {key}",
            "Content-Type":    "application/json",
            "HTTP-Referer":    "https://redacted.ai",
            "X-Title":         "REDACTED Swarm",
            "User-Agent":      ua,
            "Accept-Language": lang,
        }
    return {
        "Authorization":  f"Bearer {key}",
        "Content-Type":   "application/json",
        "User-Agent":     ua,
        "Accept-Language": lang,
    }


# ── Input validation ──────────────────────────────────────────────────────────

def _validate_chat_payload(payload: Any) -> str | None:
    """Return an error string if the payload is invalid, else None."""
    if not isinstance(payload, dict):
        return "payload must be a JSON object"
    messages = payload.get("messages")
    if not isinstance(messages, list) or len(messages) == 0:
        return "messages must be a non-empty array"
    for i, msg in enumerate(messages):
        if not isinstance(msg, dict):
            return f"messages[{i}] must be an object"
        if msg.get("role") not in ("system", "user", "assistant", "tool"):
            return f"messages[{i}].role must be system|user|assistant|tool"
        content = msg.get("content")
        if content is None:
            return f"messages[{i}].content is required"
        if not isinstance(content, (str, list)):
            return f"messages[{i}].content must be string or array"
    model = payload.get("model")
    if model is not None and not isinstance(model, str):
        return "model must be a string"
    temp = payload.get("temperature")
    if temp is not None and not isinstance(temp, (int, float)):
        return "temperature must be a number"
    if temp is not None and not (0.0 <= float(temp) <= 2.0):
        return "temperature must be between 0.0 and 2.0"
    max_tok = payload.get("max_tokens")
    if max_tok is not None and not isinstance(max_tok, int):
        return "max_tokens must be an integer"
    return None


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


_THINK_RE = re.compile(r"<(think|thinking|reasoning)>.*?</\1>", re.DOTALL | re.IGNORECASE)


def _strip_think(s: str) -> str:
    """Strip inline <think>/<reasoning> traces that weaker fallback models leak
    into `content` even when the reasoning param is honored elsewhere."""
    if not s:
        return s
    try:
        return _THINK_RE.sub("", s).strip()
    except Exception:
        return s


def _clean_choices(result: dict) -> dict:
    """Scrub reasoning traces from an OpenAI-shape response in place, and drop any
    separate reasoning field so callers only ever see clean content."""
    try:
        for choice in result.get("choices", []):
            msg = choice.get("message")
            if not isinstance(msg, dict):
                continue
            if isinstance(msg.get("content"), str):
                msg["content"] = _strip_think(msg["content"])
            msg.pop("reasoning", None)
            msg.pop("reasoning_content", None)
    except Exception:
        pass
    return result


def _from_anthropic(result: dict) -> dict:
    text  = _strip_think(result.get("content", [{}])[0].get("text", ""))
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
    try:
        costs = _PROVIDER_COSTS.get(provider, {}).get(model, {"input": 0.0, "output": 0.0})
        return round(
            (input_tokens / 1_000_000) * costs.get("input", 0.0) +
            (output_tokens / 1_000_000) * costs.get("output", 0.0),
            6
        )
    except Exception:
        return 0.0


# ── Local logging ─────────────────────────────────────────────────────────────

def _log_entry(provider: str, model: str, messages: list, response_text: str,
               latency_ms: float, error: str = "", ephemeral: bool = False,
               cost_usd: float = 0.0) -> None:
    """Append a log entry — respects LOG_LEVEL, EPHEMERAL_MODE, disk_log, and X-Ephemeral/X-Transient."""
    if LOG_LEVEL() == "none" or ephemeral or EPHEMERAL_MODE():
        return
    # maximum/zero/tee/e2ee: never log content or write to disk; metadata only
    force_minimal = _is_max_privacy(PRIVACY_MODE())

    try:
        now_unix = time.time()
        entry: dict[str, Any] = {
            "ts":         time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now_unix)),
            "ts_unix":    now_unix,  # used for TTL purge
            "provider":   provider,
            "model":      model,
            "latency_ms": round(latency_ms),
            "turns":      len(messages),
            "privacy_mode": PRIVACY_MODE(),
        }
        prompt_chars = sum(len(str(m.get("content", ""))) for m in messages)
        entry["prompt_tokens_est"]     = prompt_chars // 4
        entry["completion_tokens_est"] = len(response_text) // 4
        entry["cost_usd"]              = cost_usd

        # Content previews only in full mode and only for anonymous (never in private/maximum)
        if LOG_LEVEL() == "full" and not force_minimal and PRIVACY_MODE() == "anonymous":
            entry["messages_preview"] = [
                {"role": m.get("role", "?"), "content": str(m.get("content", ""))[:200]}
                for m in messages[-3:]
            ]
            entry["response_preview"] = response_text[:300]
        if error:
            entry["error"] = error[:200]

        _log_ring.append(entry)

        # Disk write only if DISK_LOG is enabled and not a max-privacy mode
        if DISK_LOG() and not force_minimal:
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


async def _ring_purge_loop() -> None:
    """Periodically remove ring buffer entries older than RING_BUFFER_TTL seconds."""
    while True:
        await asyncio.sleep(60)  # check every minute
        ttl = RING_TTL()
        if ttl <= 0:
            continue
        cutoff = time.time() - ttl
        # Deque doesn't support efficient random access — rebuild from left (oldest) end
        while _log_ring and _log_ring[0].get("ts_unix", 0) < cutoff:
            _log_ring.popleft()


# ── Core proxy ────────────────────────────────────────────────────────────────

def _new_session(direct: bool = False) -> aiohttp.ClientSession:
    """Create a ClientSession for upstream provider calls. When UPSTREAM_PROXY is
    set, route through it (socks5h://… keeps DNS in-tunnel) so provider traffic
    egresses via the Mullvad exit rather than the host's home IP. Unset → direct,
    identical to the previous behavior. Pass direct=True to force a plain session
    that bypasses the proxy (used for providers in DIRECT_EGRESS_PROVIDERS whose
    edge blocks the Mullvad exit — see the Groq case)."""
    if UPSTREAM_PROXY and not direct:
        if ProxyConnector is None:
            raise RuntimeError(
                "UPSTREAM_PROXY is set but aiohttp_socks is not installed — "
                "add aiohttp_socks to requirements and rebuild")
        # aiohttp_socks only knows socks5/socks4/http schemes; the "h" (remote
        # DNS) variants are expressed via rdns=True instead. Normalize so a
        # socks5h:// value (natural to write) doesn't get rejected.
        url = UPSTREAM_PROXY.replace("socks5h://", "socks5://", 1).replace("socks4a://", "socks4://", 1)
        return aiohttp.ClientSession(
            connector=ProxyConnector.from_url(url, rdns=True))
    return aiohttp.ClientSession()


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
        _um_l = upstream_model.lower()
        if provider == "openrouter":
            if "deepseek" in _um_l:
                # deepseek reasoning models return null `content` at small token budgets
                # unless reasoning is disabled — inject centrally so no caller must know.
                body.setdefault("reasoning", {"enabled": False})
        else:
            # `reasoning` is an OpenRouter-specific control; Groq/xAI/OpenAI/Venice reject the
            # request outright ("property 'reasoning' is unsupported"). Callers often send it
            # (it was added for deepseek), which would otherwise fail every Groq candidate and
            # skip the free tier entirely — strip it before forwarding.
            body.pop("reasoning", None)
            if provider == "groq" and ("gpt-oss" in _um_l or _um_l.startswith("qwen")):
                # Groq reasoning models (gpt-oss*, qwen*) otherwise leak <think> traces into
                # `content` (qwen) or emit a separate reasoning field — hide it so callers get
                # clean content. Only these models accept the param (llama/gemma reject it).
                body.setdefault("reasoning_format", "hidden")
            if provider == "groq" and "gpt-oss" in _um_l:
                # gpt-oss spends its token budget on hidden reasoning first, so at the modest
                # max_tokens the swarm requests `content` comes back empty (→ counted as a
                # failure → needless escalation to the paid tier). Capping reasoning effort at
                # "low" leaves room for the actual answer. Validated: low → full content,
                # default/medium → empty. Env-overridable (set GROQ_REASONING_EFFORT="" to skip).
                if GROQ_REASONING_EFFORT:
                    body.setdefault("reasoning_effort", GROQ_REASONING_EFFORT)
        async with session.post(url, json=body, headers=headers, timeout=aiohttp.ClientTimeout(total=90)) as resp:
            result = await resp.json(content_type=None)
            if "choices" not in result:
                raise ValueError(f"{provider} error: {result.get('error', result)}")
            return _clean_choices(result)


# ── Client attribution + usage accounting ─────────────────────────────────────

_CLIENT_SANITIZE = re.compile(r"[^a-z0-9_.-]+")

def _sanitize_client(name: str) -> str:
    """Normalize a client/project label into a safe, bounded Redis-key segment."""
    s = _CLIENT_SANITIZE.sub("-", name.strip().lower())[:64].strip("-")
    return s or "unknown"

def _known_token(token: str) -> bool:
    return bool(token) and (token in _TOKEN_MAP or (PROXY_TOKEN and token == PROXY_TOKEN))

def _resolve_client(token: str, request: web.Request) -> str:
    """Hybrid attribution: a per-project token wins (un-spoofable); otherwise fall back
    to a self-reported X-Client header; otherwise the shared-token bucket, else 'unknown'."""
    if token in _TOKEN_MAP:
        return _sanitize_client(_TOKEN_MAP[token])
    hdr = request.headers.get("X-Client", "").strip()
    if hdr:
        return _sanitize_client(hdr)
    if PROXY_TOKEN and token == PROXY_TOKEN:
        return _sanitize_client(PROXY_TOKEN_NAME)
    return "unknown"

_usage_redis = None  # lazily-created shared async client

async def _usage_redis_client():
    global _usage_redis
    if _usage_redis is None:
        import redis.asyncio as aioredis
        _usage_redis = aioredis.from_url(REDIS_URL, decode_responses=True)
    return _usage_redis


def _extract_usage(result: dict) -> tuple[int, int, bool]:
    """(prompt_tokens, completion_tokens, exact) from an upstream response.

    Handles the OpenAI-style (prompt_tokens/completion_tokens) and Anthropic-style
    (input_tokens/output_tokens) spellings. exact=False means upstream sent no usable
    usage block and the caller should fall back to its own estimate.
    """
    u = result.get("usage") or {}
    if not isinstance(u, dict):
        return 0, 0, False
    pt = u.get("prompt_tokens", u.get("input_tokens"))
    ct = u.get("completion_tokens", u.get("output_tokens"))
    if isinstance(pt, int) and isinstance(ct, int) and (pt > 0 or ct > 0):
        return pt, ct, True
    return 0, 0, False


async def _record_usage(client: str, provider: str, model: str,
                        prompt_tokens: int, completion_tokens: int,
                        cost_usd: float, error: bool = False,
                        exact: bool = True) -> None:
    """Best-effort per-project usage accounting in Redis (metadata only). Never raises."""
    if not USAGE_ENABLED:
        return
    try:
        r = await _usage_redis_client()
        base = f"{USAGE_PREFIX}client:{client}"
        pipe = r.pipeline()
        pipe.sadd(f"{USAGE_PREFIX}clients", client)
        day = time.strftime("%Y-%m-%d", time.gmtime())
        dkey = f"{base}:daily:{day}"
        if error:
            pipe.hincrby(base, "errors", 1)
            # Also roll errors up daily. The lifetime counter alone can't be date-sliced,
            # which made a stale error count indistinguishable from an active one.
            pipe.hincrby(dkey, "errors", 1)
            pipe.expire(dkey, USAGE_DAILY_TTL_DAYS * 86400)
        else:
            pipe.hincrby(base, "requests", 1)
            pipe.hincrby(base, "prompt_tokens", prompt_tokens)
            pipe.hincrby(base, "completion_tokens", completion_tokens)
            pipe.hincrbyfloat(base, "cost_usd", cost_usd)
            pipe.hincrby(f"{base}:models", f"{provider}/{model}", 1)
            # Track how many requests fell back to estimated tokens, so the totals above
            # can be read as "exact unless this is non-zero".
            if not exact:
                pipe.hincrby(base, "estimated_requests", 1)
            pipe.hincrby(dkey, "requests", 1)
            pipe.hincrby(dkey, "prompt_tokens", prompt_tokens)
            pipe.hincrby(dkey, "completion_tokens", completion_tokens)
            pipe.hincrbyfloat(dkey, "cost_usd", cost_usd)
            pipe.expire(dkey, USAGE_DAILY_TTL_DAYS * 86400)
        await pipe.execute()
    except Exception as e:
        logger.debug("[usage] record failed: %s", e)


# ── Auth middleware ───────────────────────────────────────────────────────────

async def _auth_middleware(app, handler):
    async def middleware(request: web.Request):
        if request.path in ("/health", "/v1/models", "/privacy", "/debug/egress"):
            return await handler(request)
        if PROXY_TOKEN or _TOKEN_MAP:
            auth = request.headers.get("Authorization", "")
            token = auth.removeprefix("Bearer ").strip()
            if not _known_token(token):
                return web.json_response(
                    {"error": {"message": "Unauthorized", "type": "auth_error"}}, status=401)
            if not _check_rate_limit(token):
                return web.json_response(
                    {"error": {"message": "Rate limit exceeded", "type": "rate_limit_error"}}, status=429)
            # Attribute this request to a project for usage accounting.
            request["client"] = _resolve_client(token, request)
            request["is_admin"] = bool(ADMIN_TOKEN) and token == ADMIN_TOKEN
        return await handler(request)
    return middleware


# ── Handlers ──────────────────────────────────────────────────────────────────

async def handle_health(request: web.Request) -> web.Response:
    providers_up = {p: bool(k) for p, k in _PROVIDER_KEYS.items()}
    return web.json_response({
        "status":          "ok",
        "privacy_mode":    PRIVACY_MODE(),
        "log_level":       LOG_LEVEL(),
        "privacy_scrub":   PRIVACY_SCRUB(),
        "ephemeral_mode":  EPHEMERAL_MODE(),
        "disk_log":        DISK_LOG(),
        "ring_buffer_ttl": RING_TTL(),
        "prefer_venice":   PREFER_VENICE(),
        "upstream_proxy":  bool(UPSTREAM_PROXY),
        "providers":       providers_up,
    })


async def handle_egress(request: web.Request) -> web.Response:
    """Report the public IP the proxy's upstream calls actually egress from —
    fetched through the SAME session path as provider calls, so it proves whether
    UPSTREAM_PROXY routing (Mullvad) is live, not just that the sidecar works.
    Uses am.i.mullvad.net (not ipinfo.io — which rate-limits shared VPN exits
    with a 429): it isn't throttled and directly confirms the Mullvad exit."""
    try:
        async with _new_session() as s:
            async with s.get("https://am.i.mullvad.net/json",
                             timeout=aiohttp.ClientTimeout(total=15)) as resp:
                info = await resp.json(content_type=None)
        return web.json_response({
            "upstream_proxy":  UPSTREAM_PROXY or None,
            "egress_ip":       info.get("ip"),
            "mullvad_exit":    info.get("mullvad_exit_ip"),
            "exit_hostname":   info.get("mullvad_exit_ip_hostname"),
            "server_type":     info.get("mullvad_server_type"),
            "org":             info.get("organization"),
            "country":         info.get("country"),
            "city":            info.get("city"),
        })
    except Exception as e:
        return web.json_response(
            {"error": str(e), "upstream_proxy": UPSTREAM_PROXY or None}, status=502)


async def handle_privacy(request: web.Request) -> web.Response:
    """Report current privacy mode, guarantees, and what is/isn't stored."""
    mode = PRIVACY_MODE()
    guarantees = _PRIVACY_GUARANTEES.get(mode, {})
    return web.json_response({
        "privacy_mode": mode,
        "guarantees": guarantees,
        "current_settings": {
            "pii_scrub":        PRIVACY_SCRUB(),
            "disk_log":         DISK_LOG(),
            "ring_buffer_ttl":  RING_TTL(),
            "ephemeral_mode":   EPHEMERAL_MODE(),
            "log_level":        LOG_LEVEL(),
            "prefer_venice":    PREFER_VENICE(),
        },
        "available_modes": list(_PRIVACY_GUARANTEES.keys()),
        "philosophy": "You don't have to protect what you do not have.",
        "storage_policy": {
            "prompts_stored_on_disk":    DISK_LOG() and PRIVACY_MODE() == "anonymous",
            "responses_stored_on_disk":  DISK_LOG() and PRIVACY_MODE() == "anonymous",
            "metadata_in_ring_buffer":   LOG_LEVEL() != "none" and not EPHEMERAL_MODE(),
            "ring_buffer_ttl_seconds":   RING_TTL() if RING_TTL() > 0 else "unlimited",
            "ring_buffer_size_cap":      _log_ring.maxlen,
        },
    })


async def handle_config_get(request: web.Request) -> web.Response:
    return web.json_response({
        "privacy_mode":    _cfg["privacy_mode"],
        "log_level":       _cfg["log_level"],
        "privacy_scrub":   _cfg["privacy_scrub"],
        "ephemeral_mode":  _cfg["ephemeral_mode"],
        "disk_log":        _cfg["disk_log"],
        "ring_buffer_ttl": _cfg["ring_buffer_ttl"],
        "prefer_venice":   _cfg["prefer_venice"],
        "valid_privacy_modes": list(_PRIVACY_GUARANTEES.keys()),
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
        if val not in _PRIVACY_GUARANTEES:
            return web.json_response(
                {"error": f"privacy_mode must be one of: {', '.join(_PRIVACY_GUARANTEES)}"}, status=400)
        _cfg["privacy_mode"] = val
        # Auto-adjust dependent settings when mode changes
        if "log_level" not in body:
            _cfg["log_level"] = _default_log_level(val)
        if "privacy_scrub" not in body:
            _cfg["privacy_scrub"] = _default_scrub(val)
        if "disk_log" not in body:
            _cfg["disk_log"] = _default_disk_log(val)
        if "ring_buffer_ttl" not in body:
            _cfg["ring_buffer_ttl"] = _default_ring_ttl(val)
        updated["privacy_mode"] = val

    if "log_level" in body:
        val = str(body["log_level"]).lower()
        if val not in ("none", "minimal", "full"):
            return web.json_response({"error": "log_level must be none|minimal|full"}, status=400)
        _cfg["log_level"] = val
        updated["log_level"] = val

    if "privacy_scrub" in body:
        _cfg["privacy_scrub"] = bool(body["privacy_scrub"])
        updated["privacy_scrub"] = _cfg["privacy_scrub"]

    if "ephemeral_mode" in body:
        _cfg["ephemeral_mode"] = bool(body["ephemeral_mode"])
        updated["ephemeral_mode"] = _cfg["ephemeral_mode"]

    if "disk_log" in body:
        # maximum/zero/tee/e2ee: silently ignore — disk_log is always False
        if not _is_max_privacy(_cfg["privacy_mode"]):
            _cfg["disk_log"] = bool(body["disk_log"])
            updated["disk_log"] = _cfg["disk_log"]

    if "ring_buffer_ttl" in body:
        val = int(body["ring_buffer_ttl"])
        _cfg["ring_buffer_ttl"] = max(0, val)
        updated["ring_buffer_ttl"] = _cfg["ring_buffer_ttl"]

    if "prefer_venice" in body:
        _cfg["prefer_venice"] = bool(body["prefer_venice"])
        updated["prefer_venice"] = _cfg["prefer_venice"]

    logger.info("[proxy] config updated: %s", updated)
    return web.json_response({"ok": True, "updated": updated, "current": dict(_cfg)})


async def handle_models(request: web.Request) -> web.Response:
    models = [
        {"id": alias, "object": "model", "owned_by": prov}
        for alias, (prov, _) in _MODEL_ALIASES.items()
        if _PROVIDER_KEYS.get(prov)
    ]
    return web.json_response({"object": "list", "data": models})


# ── Auto-router helpers ───────────────────────────────────────────────────────

def _heuristic_score(messages: list, payload: dict) -> tuple[int, bool]:
    """Zero-cost difficulty score from prompt shape. Returns (score, code_dominant)."""
    text = "\n".join(str(m.get("content", "")) for m in messages if isinstance(m, dict))
    low = text.lower()
    tokens = len(text) // 4
    score = 0
    if tokens > 400:  score += 1
    if tokens > 1200: score += 2
    if tokens > 3000: score += 3
    if len(messages) > 6: score += 1
    mt = payload.get("max_tokens") or 0
    if isinstance(mt, int) and mt > 1024: score += 1
    if payload.get("response_format") or payload.get("tools") or payload.get("functions"): score += 2
    if any(s in low for s in _STRUCT_SIGNALS): score += 1
    if any(s in low for s in _REASON_SIGNALS): score += 2
    code_hits = sum(1 for s in _CODE_SIGNALS if s in low)
    score += min(code_hits, 3)
    code_dominant = code_hits >= 2 or "```" in low
    return score, code_dominant


async def _classify_difficulty(messages: list, payload: dict) -> tuple[str, bool, bool]:
    """Return (tier, code_dominant, used_llm). Hybrid: heuristics settle the obvious
    cases instantly; only the ambiguous middle band costs one cheap free-model call."""
    score, code_dominant = _heuristic_score(messages, payload)
    if score <= _AUTO_EASY_MAX:
        return "easy", code_dominant, False
    if score >= _AUTO_HARD_MIN:
        return "hard", code_dominant, False
    # Ambiguous middle. Don't add latency before a stream — use the medium tier.
    if payload.get("stream"):
        return "medium", code_dominant, False
    # No classifier configured (AUTO_CLASSIFIER_MODEL="") — skip the extra call and
    # take the medium tier. Reasoning models (Groq gpt-oss/qwen) can't act as a
    # 1-token classifier (hidden reasoning eats the budget → empty content), so
    # there is currently no cheap non-reasoning model to route this to.
    if not _AUTO_CLASSIFIER_MODEL:
        return "medium", code_dominant, False
    last_user = ""
    for m in reversed(messages):
        if isinstance(m, dict) and m.get("role") == "user":
            last_user = str(m.get("content", ""))[:500]
            break
    scrub = PRIVACY_SCRUB() or _is_max_privacy(PRIVACY_MODE())
    preview = _clean_messages([
        {"role": "system", "content": "Classify how hard this request is for an LLM. "
         "Answer with exactly one letter: E for simple/short/casual, H for complex/long/"
         "reasoning/coding. Output only the letter."},
        {"role": "user", "content": last_user},
    ], scrub)
    body = {"model": _AUTO_CLASSIFIER_MODEL, "messages": preview, "max_tokens": 1, "temperature": 0}
    try:
        prov, um = _resolve_provider(_AUTO_CLASSIFIER_MODEL, "")
        async with _new_session(direct=prov in DIRECT_EGRESS_PROVIDERS) as s:
            res = await asyncio.wait_for(_forward(prov, um, body, s), timeout=6)
        letter = (res.get("choices", [{}])[0].get("message", {}).get("content", "") or "").strip().upper()[:1]
        return ("hard" if letter == "H" else "easy"), code_dominant, True
    except Exception as _e:
        logger.warning("[proxy] auto classifier failed (%s) — medium fallback", _e)
        return "medium", code_dominant, False  # still free; failover escalates if needed


class _CascadeExhausted(RuntimeError):
    """Every candidate in the failover chain failed; carries the last upstream error."""


# Models that reliably fail when a request carries tool definitions. Cohere's
# north-mini-code returns INVALID_TOOL_GENERATION on every tool-call request, and it
# leads the "code" tier — so a code-tier tool call always opened with a guaranteed
# failure. Fine as a plain-completion model; just never dial it with tools attached.
_NO_TOOL_MODELS: set[str] = {m.strip() for m in os.getenv(
    "NO_TOOL_MODELS", "cohere/north-mini-code:free").split(",") if m.strip()}


def _build_auto_chain(tier: str, code_dominant: bool,
                      has_tools: bool = False) -> tuple[list[tuple[str, str]], str]:
    """Cost-first candidate chain: tier entry models → shared free tail → paid last resort."""
    key = "code" if (code_dominant and "code" in _AUTO_TIERS) else tier
    entry = _AUTO_TIERS.get(key) or _AUTO_TIERS.get("medium", [])
    _skip = _NO_TOOL_MODELS if has_tools else set()
    chain: list[tuple[str, str]] = [
        _resolve_provider(m, "") for m in entry if m not in _skip]
    for m in _FREE_CASCADE:
        if m in _skip:
            continue
        chain.append(_resolve_provider(m, ""))
    for paid in _CASCADE_MODELS:
        chain.append(_resolve_provider(paid, ""))
    return chain, key


async def handle_chat_completions(request: web.Request) -> web.Response:
    t0 = time.monotonic()

    # X-Ephemeral or X-Transient: true — skip all logging for this request
    ephemeral = (
        request.headers.get("X-Ephemeral", "").lower() == "true" or
        request.headers.get("X-Transient", "").lower() == "true"
    )

    try:
        payload = await request.json()
    except Exception:
        return web.json_response({"error": {"message": "invalid JSON"}}, status=400)

    # Input validation
    validation_err = _validate_chat_payload(payload)
    if validation_err:
        return web.json_response({"error": {"message": validation_err, "type": "invalid_request_error"}}, status=400)

    model    = payload.get("model", "openai/gpt-oss-20b")
    explicit = request.headers.get("X-Provider", "")

    # Auto-router: when model is "auto" (and no provider is pinned), classify the prompt
    # and enter the free-first cascade at the cheapest capable tier. Otherwise: normal
    # resolution + free-first prepend for the swarm's standardized default models.
    auto_tier = ""
    if not explicit and model in _AUTO_MODELS:
        tier, code_dominant, used_llm = await _classify_difficulty(payload.get("messages", []), payload)
        _chain, auto_tier = _build_auto_chain(
            tier, code_dominant, has_tools=bool(payload.get("tools")))
        provider, upstream_model = _chain[0] if _chain else ("groq", "openai/gpt-oss-20b")
        logger.info("[proxy] auto → tier=%s code=%s llm=%s", auto_tier, code_dominant, used_llm)
    else:
        provider, upstream_model = _resolve_provider(model, explicit)
        # Build failover chain: requested model first, then its equivalents — keeping
        # only providers that actually have a key. Free-first: for the swarm's standardized
        # default models, prepend the free cascade so the paid model is only reached once
        # every free option has 429'd/failed. Skipped when a provider is explicitly pinned.
        _chain: list[tuple[str, str]] = []
        if not explicit and model in _CASCADE_MODELS:
            for free_model in _FREE_CASCADE:
                _chain.append(_resolve_provider(free_model, ""))
        _chain.append((provider, upstream_model))
        if not explicit:  # don't override an explicitly-pinned provider
            for equiv in _MODEL_EQUIVALENTS.get(model, []):
                _chain.append(_resolve_provider(equiv, ""))
    # Pre-flight: drop candidates we already know will fail, before spending a
    # round-trip on each. Two independent reasons, both provider-level.
    _est_tokens = _estimate_prompt_tokens(payload)
    _over_tpm = bool(GROQ_TPM_LIMIT) and _est_tokens > GROQ_TPM_LIMIT
    candidates: list[tuple[str, str]] = []
    _seen: set[tuple[str, str]] = set()
    _preskipped: list[str] = []
    for p, m in _chain:
        if (p, m) in _seen:
            continue
        _seen.add((p, m))
        if not _PROVIDER_KEYS.get(p):
            continue
        if _over_tpm and p == "groq":
            _preskipped.append(f"{p}/{m} (est {_est_tokens}tok > TPM {GROQ_TPM_LIMIT})")
            continue
        if _provider_in_cooldown(p):
            _preskipped.append(f"{p}/{m} (provider in cooldown)")
            continue
        candidates.append((p, m))
    if _preskipped:
        logger.info("[proxy] pre-flight skipped %d candidate(s): %s",
                    len(_preskipped), ", ".join(_preskipped))

    # Never strand a request on an empty chain because of a pre-flight guess: if the
    # guards filtered everything out, fall back to the unfiltered set and let the
    # upstream have the final say.
    if not candidates and _chain:
        candidates = [(p, m) for p, m in dict.fromkeys(_chain) if _PROVIDER_KEYS.get(p)]
        if candidates:
            logger.info("[proxy] pre-flight filtered every candidate — using full chain")

    if not candidates:
        return web.json_response(
            {"error": {"message": f"No API key configured for provider: {provider}"}}, status=503)

    if DEFAULT_TEMPERATURE:
        payload.setdefault("temperature", float(DEFAULT_TEMPERATURE))
    if DEFAULT_TOP_P:
        payload.setdefault("top_p", float(DEFAULT_TOP_P))
    if request.headers.get("X-Temperature"):
        try:
            payload["temperature"] = float(request.headers["X-Temperature"])
        except ValueError:
            pass
    if request.headers.get("X-Top-P"):
        try:
            payload["top_p"] = float(request.headers["X-Top-P"])
        except ValueError:
            pass

    # PII scrub — forced on in maximum modes regardless of PRIVACY_SCRUB setting
    scrub = PRIVACY_SCRUB() or _is_max_privacy(PRIVACY_MODE())
    original_messages = payload.get("messages", [])
    payload["messages"] = _clean_messages(original_messages, scrub)

    error_text = ""
    response_text = ""
    try:
        result = None
        # Two lazily-created sessions: proxied (via UPSTREAM_PROXY / Mullvad) and direct
        # (home IP). Providers in DIRECT_EGRESS_PROVIDERS use the direct one because their
        # edge blocks the Mullvad exit (see Groq). Keyed by the `direct` bool.
        _sessions: dict[bool, aiohttp.ClientSession] = {}
        def _session_for(prov: str) -> aiohttp.ClientSession:
            direct = prov in DIRECT_EGRESS_PROVIDERS
            if direct not in _sessions:
                _sessions[direct] = _new_session(direct=direct)
            return _sessions[direct]
        _skip_providers: set[str] = set()
        _fails = 0
        try:
            for _i, (_prov, _um) in enumerate(candidates):
                if _prov in _skip_providers:
                    continue
                try:
                    result = await _forward(_prov, _um, payload, _session_for(_prov))
                    # Some models (esp. reasoning/agentic ":free" ones) return HTTP 200 with
                    # null/empty content — useless as a chat reply. Treat that as a failure so
                    # the cascade escalates, unless the reply carries tool_calls.
                    _msg = (result.get("choices") or [{}])[0].get("message", {}) or {}
                    if not (_msg.get("content") or _msg.get("tool_calls")):
                        raise RuntimeError(f"empty content from {_prov}/{_um}")
                    if _fails > 0:
                        logger.info("[proxy] failover: %s/%s succeeded after %d failure(s)",
                                    _prov, _um, _fails)
                    provider, upstream_model = _prov, _um  # reflect who actually served
                    break
                except Exception as _fe:
                    error_text = str(_fe)
                    _fails += 1
                    logger.warning("[proxy] %s/%s failed: %s", _prov, _um, error_text)
                    # A prompt that overruns the per-minute token limit overruns it on every
                    # model of that provider — the rest of its candidates would fail the same
                    # way, so skip straight past them instead of burning a round-trip each.
                    if "rate_limit_exceeded" in error_text and "Request too large" in error_text:
                        _skip_providers.add(_prov)
                    # Out of credits / bad key: this provider is unusable for everyone,
                    # not just this request. Remember it so the next request skips it
                    # in pre-flight instead of rediscovering it here.
                    elif _is_hard_provider_failure(error_text):
                        _skip_providers.add(_prov)
                        _PROVIDER_COOLDOWN[_prov] = time.time() + PROVIDER_COOLDOWN_S
                        logger.warning("[proxy] provider %s in cooldown for %ds: %s",
                                       _prov, PROVIDER_COOLDOWN_S, error_text[:120])
                    continue
        finally:
            for _s in _sessions.values():
                await _s.close()
        if result is None:
            raise _CascadeExhausted(error_text or "all providers failed")
        response_text = (result.get("choices", [{}])[0].get("message", {}).get("content") or "")
        latency_ms = (time.monotonic() - t0) * 1000
        # Prefer the exact counts upstream already returned — the char/4 heuristic ignores
        # system prompts, roles and template overhead and undercounts badly (a 28-char
        # probe measured 7 estimated vs 78 actual prompt tokens). Fall back to the
        # estimate only when a provider omits the usage block.
        input_tokens, output_tokens, tokens_exact = _extract_usage(result)
        if not tokens_exact:
            prompt_chars = sum(len(str(m.get("content", ""))) for m in original_messages)
            input_tokens = prompt_chars // 4
            output_tokens = len(response_text) // 4
        cost_usd = _estimate_cost_usd(provider, upstream_model, input_tokens, output_tokens)
        logger.info("[proxy] %s/%s → %d chars (%.0fms) $%.6f%s",
                    provider, upstream_model, len(response_text), latency_ms, cost_usd,
                    " [ephemeral]" if (ephemeral or EPHEMERAL_MODE()) else "")
        _log_entry(provider, upstream_model, original_messages, response_text,
                   latency_ms, ephemeral=ephemeral, cost_usd=cost_usd)
        await _record_usage(request.get("client", "unknown"), provider, upstream_model,
                            input_tokens, output_tokens, cost_usd, exact=tokens_exact)
        resp = web.json_response(result)
        resp.headers["X-Privacy-Mode"] = PRIVACY_MODE()
        if auto_tier:
            resp.headers["X-Auto-Tier"] = auto_tier
        return resp

    except Exception as e:
        error_text = str(e)
        latency_ms = (time.monotonic() - t0) * 1000
        if isinstance(e, _CascadeExhausted):
            # Every candidate already logged its own failure; naming one here would
            # pin the last error on whichever model happened to lead the chain.
            logger.warning("[proxy] all %d candidate(s) failed, last error: %s",
                           len(candidates), error_text)
        else:
            # Name the class: a non-cascade exception here is a proxy bug, not an
            # upstream failure, and the two were indistinguishable in the logs.
            logger.warning("[proxy] %s/%s failed (%s): %s",
                           provider, upstream_model, type(e).__name__, error_text)
        _log_entry(provider, upstream_model, original_messages, "",
                   latency_ms, error=error_text, ephemeral=ephemeral)
        await _record_usage(request.get("client", "unknown"), provider, upstream_model,
                            0, 0, 0.0, error=True)
        return web.json_response(
            {"error": {"message": error_text, "provider": provider}}, status=502)


async def handle_logs(request: web.Request) -> web.Response:
    """Return recent proxy log entries — respects current privacy mode."""
    n = min(int(request.query.get("n", "100")), 500)
    entries = list(_log_ring)[-n:]

    # Fall back to disk if ring is empty and disk log is enabled
    if not entries and DISK_LOG() and _LOG_PATH.exists():
        try:
            lines = _LOG_PATH.read_text(encoding="utf-8").splitlines()
            for line in lines[-n:]:
                try:
                    entries.append(json.loads(line))
                except Exception:
                    pass
        except Exception as e:
            return web.json_response({"error": str(e)}, status=500)

    mode = PRIVACY_MODE()
    sensitivity = "none" if mode in _MAX_PRIVACY_MODES else ("low" if mode == "private" else "medium")
    return web.json_response({
        "entries":       entries,
        "total_in_ring": len(_log_ring),
        "privacy_mode":  mode,
        "data_sensitivity": sensitivity,
        "note": "Entries contain metadata only — no prompt/response content." if mode != "anonymous" else "Entries may contain message previews.",
    })


# ── Usage metrics ──────────────────────────────────────────────────────────────

async def handle_usage(request: web.Request) -> web.Response:
    """Per-project usage breakdown (requests/tokens/cost/errors), read from Redis.
    Query params: ?client=<name> to filter one project; ?days=<N> to include the last
    N daily buckets per project. Metadata only — no prompt/response content is stored."""
    if not USAGE_ENABLED:
        return web.json_response({"error": "usage accounting disabled"}, status=404)
    try:
        r = await _usage_redis_client()
        want = request.query.get("client", "").strip()
        clients = [_sanitize_client(want)] if want else sorted(await r.smembers(f"{USAGE_PREFIX}clients"))
        try:
            days = max(0, min(int(request.query.get("days", "0")), 90))
        except ValueError:
            days = 0
        day_keys = [time.strftime("%Y-%m-%d", time.gmtime(time.time() - i * 86400)) for i in range(days)]

        out: dict[str, Any] = {}
        totals = {"requests": 0, "prompt_tokens": 0, "completion_tokens": 0, "cost_usd": 0.0, "errors": 0}
        for c in clients:
            base = f"{USAGE_PREFIX}client:{c}"
            h = await r.hgetall(base)
            if not h:
                continue
            models = await r.hgetall(f"{base}:models")
            rec: dict[str, Any] = {
                "requests":          int(h.get("requests", 0)),
                "prompt_tokens":     int(h.get("prompt_tokens", 0)),
                "completion_tokens": int(h.get("completion_tokens", 0)),
                "cost_usd":          round(float(h.get("cost_usd", 0) or 0), 6),
                "errors":            int(h.get("errors", 0)),
                "models":            {k: int(v) for k, v in models.items()},
            }
            if days:
                daily = {}
                for dk in day_keys:
                    dh = await r.hgetall(f"{base}:daily:{dk}")
                    if dh:
                        daily[dk] = {"requests": int(dh.get("requests", 0)),
                                     "cost_usd": round(float(dh.get("cost_usd", 0) or 0), 6)}
                rec["daily"] = daily
            out[c] = rec
            for k in totals:
                totals[k] += rec.get(k, 0)
        totals["cost_usd"] = round(totals["cost_usd"], 6)
        return web.json_response({
            "clients":      out,
            "totals":       totals,
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        })
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


async def handle_usage_reset(request: web.Request) -> web.Response:
    """Reset usage counters. Admin-token only. ?client=<name> resets one project;
    otherwise all projects are cleared. Requires ?confirm=true."""
    if not request.get("is_admin"):
        return web.json_response({"error": "admin token required"}, status=403)
    if request.query.get("confirm") != "true":
        return web.json_response({"error": "add ?confirm=true to reset"}, status=400)
    try:
        r = await _usage_redis_client()
        want = request.query.get("client", "").strip()
        targets = [_sanitize_client(want)] if want else list(await r.smembers(f"{USAGE_PREFIX}clients"))
        deleted = 0
        for c in targets:
            base = f"{USAGE_PREFIX}client:{c}"
            keys = [base, f"{base}:models"]
            async for dk in r.scan_iter(match=f"{base}:daily:*"):
                keys.append(dk)
            if keys:
                deleted += await r.delete(*keys)
            await r.srem(f"{USAGE_PREFIX}clients", c)
        return web.json_response({"reset": targets, "keys_deleted": deleted})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


# ── Redis heartbeat ────────────────────────────────────────────────────────────

async def _redis_write_hb() -> None:
    """Write proxy heartbeat to Redis every 3 min so webchat shows it online."""
    try:
        import redis.asyncio as aioredis
        r = aioredis.from_url(REDIS_URL, decode_responses=True)
        payload = json.dumps({
            "agent":   "redacted-proxy",
            "ts":      time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "unix":    time.time(),
            "service": "redacted-proxy",
            "role":    "infra",
        })
        await r.set(f"{HEARTBEAT_PREFIX}redacted-proxy", payload, ex=HEARTBEAT_TTL)
        await r.aclose()
        logger.debug("[heartbeat] wrote proxy liveness to redis")
    except Exception as e:
        logger.warning("[heartbeat] redis write failed: %s", e)


async def _heartbeat_loop() -> None:
    while True:
        await _redis_write_hb()
        await asyncio.sleep(180)


# ── Server ────────────────────────────────────────────────────────────────────

async def make_app() -> web.Application:
    app = web.Application(middlewares=[_auth_middleware])
    app.router.add_get("/health",               handle_health)
    app.router.add_get("/privacy",              handle_privacy)
    app.router.add_get("/debug/egress",         handle_egress)
    app.router.add_get("/v1/models",            handle_models)
    app.router.add_post("/v1/chat/completions", handle_chat_completions)
    app.router.add_get("/logs",                 handle_logs)
    app.router.add_get("/usage",                handle_usage)
    app.router.add_post("/usage/reset",         handle_usage_reset)
    app.router.add_get("/config",               handle_config_get)
    app.router.add_post("/config",              handle_config_post)

    async def _on_startup(app):
        asyncio.create_task(_heartbeat_loop())
        asyncio.create_task(_ring_purge_loop())
        logger.info("[heartbeat] started redis liveness pulse")
        if RING_TTL() > 0:
            logger.info("[ring] TTL purge loop started (TTL=%ds)", RING_TTL())

    app.on_startup.append(_on_startup)
    return app


if __name__ == "__main__":
    logger.info(
        "[proxy] starting on port %d | mode=%s log=%s scrub=%s disk=%s ring_ttl=%ds rpm=%d prefer_venice=%s upstream_proxy=%s",
        PORT, PRIVACY_MODE(), LOG_LEVEL(), PRIVACY_SCRUB(), DISK_LOG(),
        RING_TTL(), RATE_LIMIT_RPM, PREFER_VENICE(), UPSTREAM_PROXY or "direct"
    )
    web.run_app(make_app(), port=PORT, host="0.0.0.0")
