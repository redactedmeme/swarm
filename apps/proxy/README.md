# redacted-proxy

OpenAI-compatible LLM privacy proxy for the REDACTED swarm. Sits between swarm bots and upstream LLM providers — strips fingerprinting headers, randomizes user-agents and Accept-Language, scrubs PII, and enforces ephemeral-by-default storage so upstream providers learn as little as possible about who is talking to them and what they're saying.

> **Philosophy:** *"You don't have to protect what you do not have."*

---

## Endpoints

| Method | Path | Auth | Description |
|---|---|---|---|
| `POST` | `/v1/chat/completions` | Bearer token | Main proxy — OpenAI-compatible |
| `GET` | `/v1/models` | None | List available model aliases |
| `GET` | `/health` | None | Liveness + provider key status |
| `GET` | `/privacy` | None | Current privacy mode, guarantees, storage policy |
| `GET` | `/logs?n=100` | Bearer token | Recent proxy log (in-memory ring) |
| `GET` | `/config` | Bearer token | Current runtime config |
| `POST` | `/config` | Bearer token | Hot-update config (no redeploy needed) |
| `GET` | `/usage` | Bearer token | Per-project API usage totals (metadata only) |
| `POST` | `/usage/reset` | Admin token | Reset usage counters |
| `GET` | `/debug/egress` | None | Current upstream egress IP (VPN routing check) |

---

## Privacy Architecture

### Philosophy

The proxy is designed so that even if logs were exfiltrated, they reveal as little as possible. In `private` and `maximum` modes, no prompt or response content is ever stored — only metadata (provider, model, latency, token count estimates). In `maximum`/`zero` mode, even metadata is auto-purged from the in-memory ring buffer after 5 minutes.

### What we store vs. what we don't

| | `anonymous` | `private` (default) | `maximum` / `zero` |
|---|---|---|---|
| Prompts stored on disk | ✅ (if DISK_LOG=true) | ❌ | ❌ |
| Responses stored on disk | ✅ (if DISK_LOG=true) | ❌ | ❌ |
| Metadata in ring buffer | ✅ | ✅ (TTL: 1h) | ✅ (TTL: 5min) |
| Content previews in ring | ✅ | ❌ | ❌ |
| PII scrub applied | opt-in | ✅ default | ✅ forced |
| Disk logging default | ✅ | ❌ | ❌ always |

### Privacy modes

Set via `PRIVACY_MODE` env var or `POST /config`:

| Mode | Description | Disk log | Ring TTL | PII scrub | Notes |
|---|---|---|---|---|---|
| `anonymous` | Header stripping + synthetic UA. Full logging possible. | opt-in (default on) | unlimited | opt-in | For max throughput; backward compat |
| `private` *(default)* | anonymous + metadata-only logging + PII scrub on. | off by default | 1 hour | on | Recommended for all bots |
| `maximum` | private + no disk ever + ring TTL 5 min | always off | 5 min | forced | Maximum ephemeral-by-default |
| `zero` | Alias for maximum | always off | 5 min | forced | "Zero storage" branding |
| `tee` | *Future* — TEE provider routing. Currently = maximum | always off | 5 min | forced | TEE attestation not yet implemented |
| `e2ee` | *Future* — E2EE client sessions. Currently = maximum | always off | 5 min | forced | Client-side encryption not yet implemented |

### Privacy transforms (every request)

1. **Header stripping** — removes 30+ fingerprinting headers: `User-Agent`, `X-Forwarded-For`, `CF-*`, all tracing headers (`traceparent`, `X-B3-*`, `X-Amzn-Trace-Id`, `X-Datadog-*`), `Referer`, `Origin`, `DNT`, `Sec-CH-UA-*`, `Sec-Fetch-*`, `Accept-Language`, `Via`, `X-Cache`, and the client `Authorization`.
2. **Synthetic UA** — randomized browser user-agent injected per request from a pool of 12+ real browser strings.
3. **Synthetic Accept-Language** — randomized language header from a diverse pool to prevent language fingerprinting.
4. **PII scrubbing** — optional (on by default in private/maximum) regex pass over message content. Redacts: long numeric IDs, `@handles`, email addresses, credit-card-like patterns, US phone numbers.
5. **Ephemeral requests** — send `X-Ephemeral: true` or `X-Transient: true` to skip all logging for a single request.
6. **Response header** — `X-Privacy-Mode: <current_mode>` on all completions responses.

### Threat model

**What we defend against:**
- Upstream provider fingerprinting (browser UA, Accept-Language, tracing headers, IP via X-Forwarded-For)
- Local log exfiltration (no content stored in private/maximum modes)
- PII leakage to providers (regex scrub)
- Request correlation (synthetic UA rotated per-request)

**What we do NOT defend against (out of scope):**
- Upstream provider logging of the content itself (you trust the provider's privacy policy; Venice.ai is a stronger choice for private/maximum modes)
- Network-level traffic analysis
- Compromised proxy process memory (for that, use TEE mode when implemented)
- Client-side plaintext (for that, use e2ee mode when implemented)

### Venice as preferred backend

[Venice.ai](https://venice.ai) provides additional privacy guarantees at the provider level — they do not log prompts server-side. When `PREFER_VENICE=true`, the proxy will automatically reroute compatible models to Venice in `private`/`maximum` modes:

| Original model | Venice equivalent |
|---|---|
| `llama-3.3-70b-versatile` | `llama-3-3-70b` |
| `llama-3.3-70b` | `llama-3-3-70b` |
| `mixtral-8x7b` | `mistral-31-24b` |

Using Venice + `maximum` mode gives you two independent layers of privacy: the proxy strips fingerprinting metadata, and Venice doesn't log content.

---

## Provider routing

Model names are matched in this order: alias table → Venice exact-name set → prefix rules.

| Model prefix / name | Provider |
|---|---|
| `grok-*` | xAI |
| `llama-*`, `gemma*`, `mixtral-*`, `qwen-*`, `deepseek-*` | Groq |
| `claude-*` | Anthropic |
| `gpt-*` | OpenAI |
| Venice exact names (e.g. `gemma-4-uncensored`, `venice-uncensored`) | Venice |

Force a provider with the `X-Provider: groq` request header.

### Aliases

```
grok-4-1-fast         → xai   / grok-4-1-fast
llama-3.3-70b         → groq  / llama-3.3-70b-versatile
llama-3.1-8b-instant  → groq  / llama-3.1-8b-instant
claude-haiku          → anthropic / claude-3-haiku-20240307
claude-sonnet         → anthropic / claude-sonnet-4-5
gpt-4o                → openai / gpt-4o
venice-uncensored     → venice / venice-uncensored
llama-3-3-70b         → venice / llama-3-3-70b
```

---

## Log levels

| Level | What's stored |
|---|---|
| `none` | Nothing |
| `minimal` | Timestamp, provider, model, latency, token count estimates (no content) |
| `full` | `minimal` + last 3 message previews (200 chars) + response preview (300 chars) — **anonymous mode only** |

The `full` level never stores content previews in `private` or `maximum` modes, regardless of the `LOG_LEVEL` setting.

Logs are kept in a 500-entry in-memory ring buffer. In `private` mode, entries auto-purge after 1 hour. In `maximum`/`zero` mode, entries auto-purge after 5 minutes. Disk writes only occur in `anonymous` mode with `DISK_LOG=true`.

---

## Hot config update

No redeploy needed:

```bash
# Switch to maximum privacy
curl -X POST $PROXY_URL/config \
  -H "Authorization: Bearer $PROXY_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"privacy_mode": "maximum"}'

# Enable Venice preference
curl -X POST $PROXY_URL/config \
  -H "Authorization: Bearer $PROXY_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"prefer_venice": true}'
```

---

## Environment variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `PROXY_TOKEN` | Yes | — | Bearer token all clients must present |
| `XAI_API_KEY` | For xAI | — | xAI upstream key |
| `GROQ_API_KEY` | For Groq | — | Groq upstream key |
| `ANTHROPIC_API_KEY` | For Anthropic | — | Anthropic upstream key |
| `OPENAI_API_KEY` | For OpenAI | — | OpenAI upstream key |
| `OPENROUTER_API_KEY` | For OpenRouter | — | OpenRouter upstream key (slash-form + `:free` models) |
| `VENICE_API_KEY` | For Venice | — | Venice upstream key |
| `CASCADE_MODELS` | No | `deepseek/deepseek-v4-flash` | Comma-separated model ids served **free-first**: the free cascade is tried before the requested (paid) model |
| `FREE_CASCADE` | No | see below | Comma-separated ordered free models tried ahead of a `CASCADE_MODELS` request (Groq free tier + OpenRouter `:free`). Update as OpenRouter's free lineup rotates |
| `AUTO_MODELS` | No | `auto` | Model ids that trigger the auto-router (prompt-difficulty routing). Bots send `model:"auto"` to opt in |
| `AUTO_CLASSIFIER_MODEL` | No | *(empty — disabled)* | Cheap free model used to judge the ambiguous middle band. Empty means the ambiguous band settles to `medium` with no extra LLM hop |
| `AUTO_TIERS` | No | built-in | JSON `{tier: [model,…]}` overriding the easy/medium/hard/code entry lists |
| `AUTO_EASY_MAX` / `AUTO_HARD_MIN` | No | `3` / `8` | Heuristic score thresholds: `≤EASY_MAX`→easy, `≥HARD_MIN`→hard, between→classifier |
| `GROQ_TPM_LIMIT` | No | `8000` | Groq's on_demand tokens-per-minute ceiling. A prompt estimated above it skips **all** Groq candidates in pre-flight rather than failing on one. `0` disables the guard — raise it if the Groq tier is upgraded |
| `PROVIDER_COOLDOWN_S` | No | `900` | After a hard provider failure (exhausted credits, bad key), skip that provider entirely for this many seconds instead of rediscovering it per request |
| `NO_TOOL_MODELS` | No | `cohere/north-mini-code:free` | Comma-separated models never dialed when a request carries `tools` (north-mini returns `INVALID_TOOL_GENERATION` on every tool call) |
| `PRIVACY_MODE` | No | `private` | `anonymous`, `private`, `maximum`, `zero`, `tee`, `e2ee` |
| `PRIVACY_SCRUB` | No | mode default | `true`/`false` — PII regex scrubbing (on by default in private/maximum) |
| `DISK_LOG` | No | mode default | `true`/`false` — write logs to `/data/proxy_log.jsonl` (off in private/maximum) |
| `RING_BUFFER_TTL` | No | mode default | Seconds before ring buffer entries are auto-purged (300 for maximum, 3600 for private, 0=unlimited) |
| `PREFER_VENICE` | No | `false` | Prefer Venice backend in private/maximum modes when model has a Venice equivalent |
| `EPHEMERAL_MODE` | No | `false` | Disable all logging globally |
| `LOG_LEVEL` | No | mode default | `none`, `minimal`, or `full` |
| `LOG_CONTENT` | No | — | Legacy: `"false"` forces `LOG_LEVEL=minimal` |
| `RATE_LIMIT_RPM` | No | `60` | Max requests/min per token (0 = off) |
| `CREDITS_PER_1K_TOKENS` | No | `100` | $REDACTED charged per 1k LLM tokens. Same env var name as `swarm_core.tokens` so the proxy and settler can't drift |
| `CREDITS_ENFORCE` | No | `false` | When true, a client whose `credits:balance` is ≤ 0 gets a **402** on `/v1/chat/completions`. Off = balance still moves, would-be refusals logged |
| `CREDITS_EXEMPT` | No | — | Comma-separated client names never hard-blocked (the swarm's own bots). They still debit |
| `CREDITS_TOPUP_HINT` | No | built-in | Human string returned in the 402 body |
| `PROXY_TOKEN_MAP` | No | — | JSON `{"<token>": "<project>"}` — per-project bearer tokens that both authenticate and attribute usage |
| `PROXY_TOKEN_NAME` | No | `shared` | Bucket name for traffic using the legacy shared `PROXY_TOKEN` with no `X-Client` header |
| `ADMIN_TOKEN` | No | `PROXY_TOKEN` | Token required for `/usage/reset` |
| `USAGE_ENABLED` | No | `true` | Per-project usage accounting in Redis (metadata only) |
| `USAGE_PREFIX` | No | `proxy:usage:` | Redis key prefix for usage counters |
| `USAGE_DAILY_TTL_DAYS` | No | `90` | Retention for the per-day usage rollups |
| `DIRECT_EGRESS_PROVIDERS` | No | `groq` | Providers that bypass `UPSTREAM_PROXY` and egress direct — Groq's edge blocks VPN/datacenter IPs |
| `GROQ_REASONING_EFFORT` | No | `low` | Caps reasoning effort on Groq `gpt-oss` models so they leave room for an actual answer. Empty disables the injection |
| `UPSTREAM_PROXY` | No | — | Upstream egress proxy (e.g. Mullvad via gluetun). Empty = direct |
| `DEFAULT_TEMPERATURE` | No | — | Override temperature for all requests |
| `DEFAULT_TOP_P` | No | — | Override top_p for all requests |
| `PORT` | No | `7080` | Listen port |

### Free-first cascade

When a request names a model in `CASCADE_MODELS` (default `deepseek/deepseek-v4-flash`, the swarm's
standardized model) and pins no `X-Provider`, the proxy tries every model in `FREE_CASCADE` first,
then the originally-requested (paid) model as a last resort. Any 429/failure falls through to the
next candidate. Providers with no configured key are skipped — so the **Groq tier only activates if
`GROQ_API_KEY` is set**, and the OpenRouter `:free` tier needs `OPENROUTER_API_KEY`.

Default `FREE_CASCADE` (Groq free tier first, then OpenRouter `:free`):

```
openai/gpt-oss-20b,openai/gpt-oss-120b,qwen/qwen3.6-27b,cohere/north-mini-code:free
```

Keep only **live** ids here — a dead model costs a wasted round-trip on every request that
reaches it. Validate with an actual completion, not `GET /v1/models` (Groq returns 403 for
keys without the `models:read` scope).

The OpenRouter `:free` lineup rotates — validate ids against `https://openrouter.ai/api/v1/models`
when editing. Pin a provider with `X-Provider: <name>` to bypass the cascade entirely.

### Auto-router (`model: "auto"`)

Send `model: "auto"` and the proxy inspects the prompt, estimates difficulty, and enters the
free-first cascade at the cheapest capable tier (**cost-first**). Classification is **hybrid**:
zero-cost heuristics (prompt size, turns, code/JSON/reasoning signals, requested `max_tokens`)
settle the obvious cases instantly; only the ambiguous middle band costs one cheap call to
`AUTO_CLASSIFIER_MODEL` (a free Groq model). Streaming requests skip the classifier to avoid added
latency.

Each tier (`easy` / `medium` / `hard`, plus a `code` override when code signals dominate) lists the
cheapest capable free models first, then falls through the shared `FREE_CASCADE` tail and finally the
paid `CASCADE_MODELS` — so a tier can escalate on failure and paid is always last resort. Empty/null
responses (common from reasoning `:free` models) count as failures and trigger failover. The chosen
tier is returned in the `X-Auto-Tier` response header. An `X-Provider` pin bypasses auto entirely.

---

## API usage tracking

Every request is accounted per project in Redis — **metadata only** (counts, tokens, cost,
model mix). No prompt or response content is ever written, so this works in every privacy
mode including `maximum`. Disable with `USAGE_ENABLED=false`.

Attribution comes from the bearer token via `PROXY_TOKEN_MAP`, or from an explicit
`X-Client: <project>` header. Traffic on the legacy shared `PROXY_TOKEN` with no header
lands in the `PROXY_TOKEN_NAME` bucket (default `shared`).

```bash
curl -s $PROXY_URL/usage -H "Authorization: Bearer $PROXY_TOKEN"
```

Keys written, per client:

| Key | Fields |
|---|---|
| `proxy:usage:clients` | set of known client names |
| `proxy:usage:client:<name>` | `requests`, `errors`, `prompt_tokens`, `completion_tokens`, `cost_usd`, `estimated_requests` |
| `proxy:usage:client:<name>:models` | request count per `provider/model` |
| `proxy:usage:client:<name>:daily:<YYYY-MM-DD>` | `requests`, `prompt_tokens`, `completion_tokens`, `cost_usd` (expires after `USAGE_DAILY_TTL_DAYS`) |

### Token accuracy

Token counts come from the **exact `usage` block the upstream provider returns**, handling
both the OpenAI (`prompt_tokens`/`completion_tokens`) and Anthropic
(`input_tokens`/`output_tokens`) spellings. `cost_usd` is derived from those counts.

Only when a provider omits `usage` does the proxy fall back to a `chars / 4` estimate, and
every such request increments `estimated_requests` — so the totals can be read as *exact
unless that field is non-zero*. The estimate is a poor substitute (it ignores system
prompts, roles and template overhead — a 28-char probe measures 7 estimated vs 78 actual
prompt tokens), which is why it is the fallback rather than the default.

`errors` counts requests where **every** candidate in the failover chain failed; a request
that recovers on a later candidate counts as a normal request.

---

## $REDACTED credits

Every `/v1/chat/completions` response debits the client's Redis balance by
`(prompt + completion tokens) / 1000 × CREDITS_PER_1K_TOKENS` and pushes the
spend to `credits:spend:queue`, which `apps/settler` turns into an on-chain
burn-split settlement — so proxied inference flows through the same 50/30/20
split and burn as any other paid job.

| Key | Type | Meaning |
|---|---|---|
| `credits:balance:<client>` | string float | Remaining $REDACTED. Credited by deposits, debited per request |
| `credits:debited:<client>` | string float | Lifetime $REDACTED debited |
| `credits:spend:queue` | list | Per-request spend entries the settler drains |

**Top up:** send $REDACTED to the treasury with an SPL Memo
`redacted-credits:<client>`. `apps/settler` parses the memo and credits the
balance 1:1 with the sticker price (the burn happens as the credit is *spent*,
not on deposit).

**Enforcement** is off by default (`CREDITS_ENFORCE=false`): balances still
move and a would-be refusal is logged once/min/client, but nothing is blocked.
With it on, a client at ≤ 0 (and not in `CREDITS_EXEMPT`) gets:

```json
{"error": {"message": "Insufficient $REDACTED credits — top up to continue",
           "type": "insufficient_credits", "balance": -123.45, "top_up": "…"}}
```

`GET /usage` reports `credits_balance` / `credits_debited` per client and a
top-level `credits` block (`rate_per_1k_tokens`, `enforced`, `exempt`).

---

## Wiring a bot

Set two env vars on the bot service:

```bash
PROXY_URL=<internal service URL>
PROXY_TOKEN=<value of redacted-proxy PROXY_TOKEN>
```

Then point the OpenAI client base URL at `$PROXY_URL/v1`. The proxy handles auth to upstream providers — the bot only needs `PROXY_TOKEN`.

**Currently wired:** `redacted-chan-bot`, `hermes-bot`, `smolting-telegram-bot`

---

## Request headers (client → proxy)

| Header | Effect |
|---|---|
| `Authorization: Bearer <token>` | Required auth |
| `X-Provider: groq` | Force a specific provider |
| `X-Temperature: 0.7` | Override temperature for this request |
| `X-Top-P: 0.9` | Override top_p for this request |
| `X-Ephemeral: true` | Skip logging for this request |
| `X-Transient: true` | Alias for X-Ephemeral (Venice-style naming) |

## Response headers (proxy → client)

| Header | Value |
|---|---|
| `X-Privacy-Mode` | Current privacy mode (`anonymous`, `private`, `maximum`, etc.) |
