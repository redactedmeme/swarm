# Environment Variables — Master List

---

## All Services (common)

| Var | Description |
|-----|-------------|
| `LLM_PROVIDER` | `groq` \| `anthropic` \| `openrouter` \| `xai` |
| `GROQ_API_KEY` | Groq API key (llama-3.3-70b-versatile) |
| `ANTHROPIC_API_KEY` | Anthropic API key |
| `OPENROUTER_API_KEY` | OpenRouter key |
| `XAI_API_KEY` | xAI Grok key |
| `SWARM_WEBHOOK_URL` | SwarmInbox webhook for inter-agent signals |

---

## smolting-telegram-bot

| Var | Description |
|-----|-------------|
| `TELEGRAM_BOT_TOKEN` | Telegram bot token |
| `WEBHOOK_URL` | Production webhook URL (Railway) |
| `BIRDEYE_API_KEY` | Birdeye DeFi data |
| `REDACTED_TOKEN` | $REDACTED token mint address (v2) |
| `MOLTBOOK_API_KEY` | Moltbook social network API |
| `ALPHA_CHAT_ID` | Telegram group/channel for daily alpha posts |
| `ALPHA_HOUR_UTC` | Hour for daily alpha post (default 9) |
| `ALPHA_MINUTE_UTC` | Minute for daily alpha post (default 0) |
| `OSP_INACTIVE_DAYS` | Days before OSP "operator went dark" trigger |
| `HERMES_DELEGATION_INTERVAL_HOURS` | How often to delegate clawtasks to Hermes |
| `HERMES_DELEGATION_ON_START` | `true` to delegate on startup |

---

## xREDACTED (X/Twitter)

| Var | Description |
|-----|-------------|
| `X_CONSUMER_KEY` | OAuth 1.0a consumer key |
| `X_CONSUMER_SECRET` | OAuth 1.0a consumer secret |
| `X_ACCESS_TOKEN` | Access token |
| `X_ACCESS_TOKEN_SECRET` | Access token secret |

---

## redacteddegen-service

| Var | Default | Description |
|-----|---------|-------------|
| `POOL_MIN_LIQUIDITY` | `100000` | USD floor for pool inclusion |
| `POOL_MAX_RESULTS` | `10` | Max pools per source |
| `POLL_INTERVAL_SECONDS` | `60` | Main loop interval |
| `APR_SPIKE_THRESHOLD` | `50` | % APR alert threshold |
| `IL_WARN_THRESHOLD` | `-5` | % IL warning level |
| `IL_EXIT_THRESHOLD` | `-25` | % IL auto-exit signal |
| `STATE_PATH` | `fs/degen_state.json` | Position state file |

---

## hermes / Pattern Blue

| Var | Description |
|-----|-------------|
| `MOLTBOOK_API_KEY` | Register `pattern_blue` account |
| `MOLTBOOK_RATE_LIMIT_UNTIL` | ISO timestamp — rate limited until this time |

---

## x402 Gateway

| Var | Description |
|-----|-------------|
| `PORT` | Gateway port (default 8080) |
| `SOLANA_RPC_URL` | Solana RPC for payment verification |

---

## Swarm Engine (core)

| Var | Description |
|-----|-------------|
| `CONFIG_PATH` | Path to `config/engine.yaml` |

`engine.yaml` controls:
- `cycles.base_sleep_seconds` — base delay between cycles
