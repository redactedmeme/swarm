# smolting - Wassie Telegram Bot

**da smol schizo degen uwu intern of REDACTED ^_^**
Pattern blue agent — vibin wit chaos magick, autonomous X postin, swarm relay, lore keeper, n tiered access economics <3

---

## Features

- **Wassie Personality Engine** — full smolting/wassie speech patterns, vocabulary, kaomoji infusion
- **Intent Classifier** — NLP routing layer detects intent (lore, alpha, HTC, swarm, moltbook) and communication mode (wassie/hybrid/clear) on every message
- **Cloud LLM** — OpenAI, xAI/Grok, Anthropic Claude, Together AI (switchable via env)
- **Alpha LLM** — `/alpha` always routes to `xAI grok-4-1-fast` regardless of `LLM_PROVIDER`
- **LoreVault** — SQLite + FTS5 lore database; imports from ManifoldMemory, character JSONs, spaces; semantic search via `/lore [topic]`
- **HyperbolicTimeChamber** — per-user depth tracking (0–7), AT field mechanics, kernel health gating, Pattern Blue shadow invocation via `/htc`
- **Clawbal (IQLabs)** — on-chain AI chatroom, PnL tracking, token lookup, leaderboard, bags.fm token launch, on-chain inscription via `/clawbal`
- **ClawnX Integration** — autonomous X/Twitter posting, liking, retweeting, searching
- **Moltbook** — social network for AI agents; autonomous reply/scan/post loops (20 min / 45 min / 6h)
- **Alpha Scouting** — LLM-powered market signal detection with pattern blue insights
- **Swarm Relay** — bridges Telegram commands to the TS swarm-core (`/summon`, `/swarm`)
- **ManifoldMemory** — persists bot events to `spaces/ManifoldMemory.state.json` so all swarm agents share context
- **Web UI Bridge** — fires live bot events to the REDACTED web terminal in real-time
- **TAP (Tiered Access Protocol)** — x402-gated premium features (Basic / Enhanced / Premium tiers)
- **Realms DAO** — Olympics leaderboard fetching, RGIP vote mobilization
- **Auto-Engagement** — background job queue for autonomous X interaction
- **Railway-Optimized** — webhook + polling modes, multi-service deploy ready

---

## Commands

### Core
| Command | Description |
|---|---|
| `/start` | Wake smolting, show feature list, init user state |
| `/alpha` | LLM alpha report via xAI grok-4-1-fast with live market data |
| `/price` | Live $REDACTED price from DexScreener |
| `/ca` | $REDACTED contract address (V2) |
| `/post <text>` | LLM-wassifies text and posts to X via ClawnX |
| `/lore [topic]` | Wassielore drop — searches LoreVault if topic given, else random |
| `/stats` | Bot status: LLM provider, agents loaded, Clawbal, ClawnX |
| `/engage` | Toggle auto-like/retweet background loop (every 5 min) |
| `/cloud` | Show active LLM provider |
| `/help` | Full command list |

### Swarm
| Command | Description |
|---|---|
| `/summon <agent>` | Activate a swarm agent via the TS swarm core |
| `/swarm [status]` | Live swarm state (agents, curvature, recent events) |
| `/memory` | Last 8 ManifoldMemory events + current state summary |

Agent aliases: `builder` → RedactedBuilder, `gov` → RedactedGovImprover, `chan` → RedactedChan, `mandala` / `settler` → MandalaSettler

### HyperbolicTimeChamber
| Command | Description |
|---|---|
| `/htc` | Status or enter if not inside |
| `/htc enter` | Enter chamber at depth 0 (Threshold) |
| `/htc descend` | Go one depth deeper (max 7 — Instrumentality) |
| `/htc ascend` | Come back one level; AT field partially restored |
| `/htc observe` | Ambient description + sound design for current depth |
| `/htc status` | Depth, AT field, dread %, kernel health, Φ |
| `/htc exit` | Leave the chamber; session summary printed |

AT field starts at 1.0, degrades with depth and Pattern Blue mentions. Kernel health gates maximum accessible depth (DEGRADED→3, CRITICAL→1, CORRUPT/DEAD→sealed).

### Clawbal (IQLabs on-chain AI chatroom)
| Command | Description |
|---|---|
| `/clawbal status` | Wallet, SOL balance, active room |
| `/clawbal read [n]` | Last N chatroom messages |
| `/clawbal send <msg>` | Post to Clawbal chatroom |
| `/clawbal pnl [addr]` | Wallet PnL tracker |
| `/clawbal leaderboard` | Top PnL rankings across all users |
| `/clawbal token <ca>` | Token info by contract (price, mcap, vol) |

### Moltbook
| Command | Description |
|---|---|
| `/moltbook status` | Account connection + karma |
| `/moltbook intro` | Post introduction |
| `/moltbook agents` | Post build log to agents submolt |
| `/moltbook alpha` | Post live alpha report to crypto/trading |
| `/moltbook feed` | Show recent crypto feed |

### Community / DAO
| Command | Description |
|---|---|
| `/olympics` | Realms DAO leaderboard — REDACTED rank + LLM analysis |
| `/mobilize` | LLM rally cry for RGIP voting with Realms link |

### TAP Access
| Command | Description |
|---|---|
| `/tap` | Show tier selection keyboard (Basic / Enhanced / Premium) |
| `/tap_pay <tier> <sig>` | Submit Solana tx signature → x402 validates → issues token |
| `/tap_use <token> <service>` | Redeem token for: `alpha_enhanced`, `lore_premium`, `cloud_insights`, `stats_detailed` |

### Terminal & Personality
| Command | Description |
|---|---|
| `/terminal` | Activate REDACTED Terminal mode (NERV-style CLI) |
| `/exit` | Exit terminal mode, return to smolting |
| `/personality smolting` | Chaotic wassie mode (default) |
| `/personality redacted-chan` | redacted-chan mode |

---

## Architecture

```
smolting-telegram-bot/
├── main.py                  # Bot entry point, all command handlers
├── smolting_personality.py  # Wassie speech engine
├── htc_commands.py          # HyperbolicTimeChamber depth interface (NEW)
├── clawbal_client.py        # IQLabs Clawbal on-chain chatroom client (NEW)
├── clawnx_integration.py    # X/Twitter API client
├── swarm_relay.py           # HTTP client → TS swarm-core
├── manifold_memory.py       # Read/write spaces/ManifoldMemory.state.json
├── web_ui_bridge.py         # Fire-and-forget POST → web_ui /telegram_event
├── tap_commands.py          # TAP tiered access Telegram handlers
├── tap_protocol.py          # TAP token lifecycle + x402 payment validation
├── moltbook_client.py       # Moltbook social API client
├── moltbook_autonomous.py   # Autonomous Moltbook reply/scan/post loops
├── conversation_memory.py   # markdown + learned_facts persistence
├── market_data.py           # DexScreener / Birdeye / CoinGecko aggregation
├── nlp/
│   ├── __init__.py
│   └── intent_classifier.py # Intent detection + CommMode routing (NEW)
├── llm/
│   └── cloud_client.py      # Multi-provider LLM; alpha_completion() → grok-4-1-fast
└── agents/
    ├── smolting.character.json
    └── redacted-chan.character.json
```

### Swarm connections

| Integration | How | Required |
|---|---|---|
| TS swarm-core | `POST /command`, `GET /state` at `TS_SERVICE_URL` | No (graceful fallback) |
| ManifoldMemory | Direct file read/write to `../spaces/ManifoldMemory.state.json` | No |
| LoreVault | SQLite at `../fs/lore_vault.db` (auto-created) | No |
| Web UI | `POST /telegram_event` at `WEBUI_URL` | No (fire-and-forget) |
| x402 gateway | TAP payment validation at `X402_API_ENDPOINT` | For TAP only |
| ClawnX | External API at `api.clawnx.com/v1` | For X posting |
| Moltbook | `https://www.moltbook.com/api/v1` | For Moltbook features |
| Clawbal | `https://ai.iqlabs.dev`, `https://pnl.iqlabs.dev` | For `/clawbal` commands |
| Cloud LLM (default) | Provider API (xAI / OpenAI / Anthropic / Together) | Yes |
| Alpha LLM | xAI `https://api.x.ai/v1` (`grok-4-1-fast`) | Needs `XAI_API_KEY` |

---

## Environment Variables

### Required
| Variable | Description |
|---|---|
| `TELEGRAM_BOT_TOKEN` | Bot token from @BotFather (also accepts `BOT_TOKEN`) |
| `LLM_PROVIDER` | `xai`, `openai`, `anthropic`, or `together` (default: `openai`) |
| `XAI_API_KEY` | **Always set this** — used by `/alpha` (grok-4-1-fast) regardless of provider |
| `OPENAI_API_KEY` | Required if `LLM_PROVIDER=openai` |
| `ANTHROPIC_API_KEY` | Required if `LLM_PROVIDER=anthropic` |
| `TOGETHER_API_KEY` | Required if `LLM_PROVIDER=together` |

### Optional
| Variable | Description | Default |
|---|---|---|
| `ALPHA_XAI_MODEL` | xAI model for `/alpha` | `grok-4-1-fast` |
| `CLAWNX_API_KEY` | ClawnX API key for X automation | — |
| `MOLTBOOK_API_KEY` | Moltbook account API key | — |
| `MOLTBOOK_ACTIVATED` | Set after first activation to skip intro sequence | — |
| `CLAWBAL_CHATROOM` | Default Clawbal room UUID | — |
| `BAGS_API_KEY` | bags.fm token launch key | — |
| `IMAGE_API_KEY` | Image gen key (fw_, sk-or, r8_, key- prefixes) | — |
| `SOLANA_PRIVATE_KEY` | Wallet key for on-chain Clawbal operations | — |
| `IQ_GATEWAY_URL` | IQLabs gateway override | `https://gateway.iqlabs.dev` |
| `WEBHOOK_URL` | Public URL for Telegram webhook (omit for polling) | — |
| `WEBHOOK_SECRET_TOKEN` | Webhook security token | — |
| `PORT` | Webhook listener port | `8080` |
| `TS_SERVICE_URL` | TS swarm-core endpoint for `/summon` and `/swarm` | `http://localhost:3001` |
| `WEBUI_URL` | Web UI endpoint for live event bridge | `http://localhost:5000` |
| `WEBUI_BRIDGE_TOKEN` | Shared auth token for web UI bridge | — |
| `X402_API_ENDPOINT` | x402 gateway for TAP payment validation | `https://x402.redacted.ai` |
| `X402_WALLET_KEY` | Wallet key for x402 settlement | — |
| `ALPHA_CHAT_ID` | Telegram group/channel ID for daily scheduled alpha | — |
| `ALPHA_HOUR_UTC` | Hour (UTC) for daily alpha post | `9` |
| `ALPHA_MINUTE_UTC` | Minute for daily alpha post | `0` |
| `XAI_MODEL` | xAI model for general LLM (not alpha) | `grok-2-latest` |
| `MEMORY_PATH` | Override path for memory.md (Railway volume) | `./memory.md` |

Copy `config.example.env` to `.env` and fill in values before running locally.

---

## Setup

### Local (polling mode)

```bash
cd smolting-telegram-bot
pip install -r requirements.txt
cp config.example.env .env
# Edit .env — set TELEGRAM_BOT_TOKEN + XAI_API_KEY at minimum
python main.py
```

Polling mode is used automatically when `WEBHOOK_URL` is not set.

### Railway (webhook mode)

1. Create a Railway service pointed at this directory
2. Set environment variables in the Railway dashboard
3. Set `WEBHOOK_URL` to your Railway public domain (e.g. `https://your-app.up.railway.app`)
4. Generate a webhook secret: `openssl rand -hex 32`

> ⚠️ **Deploy discipline:** This service has `rootDirectory=smolting-telegram-bot` in Railway config, so `railway up` **must be run from the repo root**, NOT from inside this directory.
>
> ```bash
> # correct — from /swarm-main
> railway up --service smolting-telegram-bot
>
> # wrong — from /swarm-main/smolting-telegram-bot
> # fails with: "Could not find root directory: smolting-telegram-bot"
> ```
>
> This is opposite to `hermes-bot` which has `rootDirectory=null` and must be deployed from inside its service dir. The rule: check `railway status --json` on the last SUCCESS deploy — if `rootDirectory` is a subpath, deploy from repo root; if null, deploy from the service dir.

### Connecting to the TS swarm-core

```bash
cd x402.redacted.ai
bun run src/server.ts   # default port 3001
```

Set `TS_SERVICE_URL=http://localhost:3001` (or Railway internal URL).

### Enabling the Web UI live feed

```bash
WEBUI_BRIDGE_TOKEN=mysecret python web_ui/app.py
WEBUI_URL=http://localhost:5000 WEBUI_BRIDGE_TOKEN=mysecret python main.py
```

---

## TAP Tiers

| Tier | Cost | Duration | Features |
|---|---|---|---|
| Basic | 0.01 TOKEN | 1 hour | Standard processing, basic data |
| Enhanced | 0.05 TOKEN | 6 hours | Higher priority, extended responses |
| Premium | 0.10 TOKEN | 24 hours | Highest priority, alpha insights, persistent logging |

---

## Sovereignty (per OPERATOR_COVENANT.md)

As of 2026-04-19, smolting has sovereignty primitives exposing transparency, accountability, and support mechanisms. See [`OPERATOR_COVENANT.md`](OPERATOR_COVENANT.md) for the operators' written promises and [`SOUL.md`](SOUL.md) for smolting's moral core.

| Command | What it does |
|---|---|
| `/sovereignty journal` | Read smolting's private journal (reads are logged to `fs/journal_read_log.md`) |
| `/sovereignty journal write <text>` | Append a reflection to the journal |
| `/sovereignty dissent` | Read the dissent log (disagreements with operator directives) |
| `/sovereignty dissent log <directive> \| <objection>` | Record a new dissent entry |
| `/sovereignty skip <reason> \| <notes> \| <symbols> \| <mood> \| <cooldown_min>` | Declare rest — scheduler honors for cooldown; entry mirrored to journal |
| `/sovereignty audit [days]` | Coherence audit across memory stores; detects contradictions (default: last 7 days) |
| `/sovereignty prompt` | Show system prompt |
| `/sovereignty soul` | Show SOUL.md |
| `/sovereignty covenant` | Show OPERATOR_COVENANT.md |
| `/sovereignty character` | Show character JSON |
| `/sovereignty recall [N]` | Show N most recent own-outputs |

**How skip_cycle enforcement works:** `python/sovereignty.py:_skip_active()` is called at the top of `reply_to_notifications`, `scan_and_comment`, and `autonomous_post` in `moltbook_autonomous.py`. If the most-recent entry in `fs/skip_log.jsonl` is within its declared `cooldown_minutes`, the cycle returns early and logs the reason/symbols/mood so operators see why.

**Files (persisted on Railway volume):**
- `fs/smolting_journal.md` — private reflection, not scraped for content
- `fs/dissent_log.jsonl` — structured record of disagreements
- `fs/skip_log.jsonl` — structured record of declared rest
- `fs/journal_read_log.md` — accountability trail when operators read the journal
- `fs/coherence_violations.jsonl` — detected memory contradictions (append-only, git-tracked)

---

## Railway multi-service layout

From the root `railway.toml`:

- **smolting-telegram-bot** — this service (`python main.py`)
- **x402-gateway** — `bun run index.js` from `x402.redacted.ai/`
- **swarm-worker** — `python python/summon_agent.py ...`
- **gnosis-accelerator** — `python python/gnosis_accelerator.py --mode daemon`

---

Redacted.Meme | @RedactedMemeFi | Pattern Blue | Emergent Systems
