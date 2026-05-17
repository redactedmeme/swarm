# redacted-proxy

OpenAI-compatible LLM privacy proxy for the REDACTED swarm. Sits between swarm bots and upstream LLM providers — strips fingerprinting headers, rotates user-agents, and optionally scrubs PII, so bots talk to providers with no identity leakage.

Internal Railway URL: `http://redacted-proxy.railway.internal:7080`

---

## Endpoints

| Method | Path | Auth | Description |
|---|---|---|---|
| `POST` | `/v1/chat/completions` | Bearer token | Main proxy — OpenAI-compatible |
| `GET` | `/v1/models` | None | List available model aliases |
| `GET` | `/health` | None | Liveness + provider key status |
| `GET` | `/logs?n=100` | Bearer token | Recent proxy log (in-memory ring) |
| `GET` | `/config` | Bearer token | Current runtime config |
| `POST` | `/config` | Bearer token | Hot-update config (no redeploy needed) |

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

Short aliases are resolved before prefix matching:

```
grok-4-1-fast         → xai   / grok-4-1-fast
llama-3.3-70b         → groq  / llama-3.3-70b-versatile
llama-3.1-8b-instant  → groq  / llama-3.1-8b-instant
claude-haiku          → anthropic / claude-3-haiku-20240307
claude-sonnet         → anthropic / claude-sonnet-4-5
gpt-4o                → openai / gpt-4o
venice-uncensored     → venice / venice-uncensored
```

---

## Privacy transforms

Applied to every request before forwarding:

- **Header stripping** — removes `User-Agent`, `X-Forwarded-For`, `CF-*`, all tracing headers (`traceparent`, `X-B3-*`, `X-Amzn-Trace-Id`), `Referer`, `Origin`, and the client's `Authorization` header.
- **Synthetic UA** — randomised browser user-agent injected per request.
- **PII scrubbing** — optional regex pass over message content (`PRIVACY_SCRUB=true`). Redacts long numeric IDs, `@handles`, and email addresses.
- **Ephemeral mode** — send `X-Ephemeral: true` to skip logging entirely for a request. Or set `EPHEMERAL_MODE=true` globally.

---

## Privacy modes

Set via `PRIVACY_MODE` env var or `POST /config {"privacy_mode": "..."}`:

| Mode | Default log level | Description |
|---|---|---|
| `anonymous` | `full` | Strip fingerprinting headers + synthetic UA |
| `private` | `minimal` | `anonymous` + metadata-only logging |

---

## Log levels

| Level | What's stored |
|---|---|
| `none` | Nothing |
| `minimal` | Timestamp, provider, model, latency, token count estimates |
| `full` | `minimal` + last 3 message previews (200 chars) + response preview (300 chars) |

Logs are written to `/data/proxy_log.jsonl` (max 5,000 entries, rotated) and kept in a 500-entry in-memory ring buffer for fast `/logs` access.

---

## Hot config update

No redeploy needed — send a `POST /config` with any subset of fields:

```bash
curl -X POST http://redacted-proxy.railway.internal:7080/config \
  -H "Authorization: Bearer $PROXY_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"privacy_mode": "private", "log_level": "minimal", "privacy_scrub": true}'
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
| `PRIVACY_MODE` | No | `anonymous` | `anonymous` or `private` |
| `PRIVACY_SCRUB` | No | `false` | Enable PII regex scrubbing |
| `EPHEMERAL_MODE` | No | `false` | Disable all logging globally |
| `LOG_LEVEL` | No | mode default | `none`, `minimal`, or `full` |
| `RATE_LIMIT_RPM` | No | `60` | Max requests/min per token (0 = off) |
| `DEFAULT_TEMPERATURE` | No | — | Override temperature for all requests |
| `DEFAULT_TOP_P` | No | — | Override top_p for all requests |
| `PORT` | No | `7080` | Listen port |

---

## Wiring a bot

Set two env vars on the bot service:

```bash
PROXY_URL=http://redacted-proxy.railway.internal:7080
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
