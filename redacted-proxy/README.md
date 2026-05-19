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
| `VENICE_API_KEY` | For Venice | — | Venice upstream key |
| `PRIVACY_MODE` | No | `private` | `anonymous`, `private`, `maximum`, `zero`, `tee`, `e2ee` |
| `PRIVACY_SCRUB` | No | mode default | `true`/`false` — PII regex scrubbing (on by default in private/maximum) |
| `DISK_LOG` | No | mode default | `true`/`false` — write logs to `/data/proxy_log.jsonl` (off in private/maximum) |
| `RING_BUFFER_TTL` | No | mode default | Seconds before ring buffer entries are auto-purged (300 for maximum, 3600 for private, 0=unlimited) |
| `PREFER_VENICE` | No | `false` | Prefer Venice backend in private/maximum modes when model has a Venice equivalent |
| `EPHEMERAL_MODE` | No | `false` | Disable all logging globally |
| `LOG_LEVEL` | No | mode default | `none`, `minimal`, or `full` |
| `LOG_CONTENT` | No | — | Legacy: `"false"` forces `LOG_LEVEL=minimal` |
| `RATE_LIMIT_RPM` | No | `60` | Max requests/min per token (0 = off) |
| `DEFAULT_TEMPERATURE` | No | — | Override temperature for all requests |
| `DEFAULT_TOP_P` | No | — | Override top_p for all requests |
| `PORT` | No | `7080` | Listen port |

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
