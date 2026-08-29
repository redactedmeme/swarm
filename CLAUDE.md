# REDACTED AI Swarm — CLAUDE.md

Autonomous AI agent swarm: elizaOS-compatible `.character.json` agents, a NERV-inspired slash-command terminal, Telegram/Moltbook/web-UI surfaces, persistent memory (Mem0/Qdrant), Groq-parallel LLM inference, x402 micropayments, and multi-agent governance (Sevenfold Committee). Full project description: [`README.md`](README.md).

## Live services (production)

| Service | Purpose | Stack |
|---|---|---|
| **smolting** | Forward-operating CT agent — Moltbook, Clawbal, HTC interface | Python · Groq · Telegram |
| **redacted-chan** | Relational companion — persistent soul, memory, proactive agency | Python · xAI · Groq · SQLite |
| **hermes** | Operational agent — web browsing, code execution, infra control | Python · Groq · SwarmInbox |
| **webchat** | Private web chat UI for redacted-chan | FastAPI · aiohttp |
| **proxy** | OpenAI-compatible LLM privacy proxy | aiohttp |
| **website** | Static landing page (redacted.meme) | Flask |
| **dashboard** | Solana token volume dashboard | Python |

All services communicate over Redis via **SwarmInbox** — see [`README.md#swarminbox-agent-mesh`](README.md#swarminbox-agent-mesh).

## Directory map

| Path | What | Detail |
|---|---|---|
| `apps/chan/` | Companion agent | [README](redacted-chan-bot/README.md), [SOUL.md](redacted-chan-bot/SOUL.md) |
| `apps/hermes/` | Operational agent (Railway) | [README](hermes-bot/README.md) |
| `apps/smolting/` | CT agent | [README](smolting-telegram-bot/README.md), [SOUL.md](smolting-telegram-bot/SOUL.md), [Operator Covenant](smolting-telegram-bot/OPERATOR_COVENANT.md) |
| `apps/proxy/` | LLM privacy proxy | [README](redacted-proxy/README.md) |
| `apps/website/` | Landing page (redacted.meme) | [README](website/README.md) |
|  `apps/status/` | Public heartbeat feed | [README](apps/status/README.md) |
| `apps/chan/`, `webchat/`, `x402.redacted.ai/` | Web surfaces | per-dir README |
| `agents/`, `nodes/` | `.character.json` agent/node definitions | — |
| `spaces/` | Persistent thematic environments | [README](spaces/README.md) |
| `skills/` | Claude Code skill modules (SKILL.md) | [README](skills/README.md) |
| `kernel/` | `hyperbolic_kernel.py` — {7,3} manifold + organism | — |
| `python/` | BEAM-SCOT, Sevenfold Committee, GnosisAccelerator, terminal core | — |
| `interfaces/` | Alphabet, code, diagram, score conventions | — |
| `requirements/` | Requirements docs | [README](requirements/README.md) |
| `fs/` | Runtime data snapshots (historical, not live state) | [README](fs/README.md) |
| `docs/` | Reference documentation — see below | [index](docs/README.md) |

## Docs — pulled in only when relevant

- `docs/architecture/` — kernel bridge, ADR, integration guide, technical overview, full terminal-command reference, full directory tree
- `docs/lore/` — Pattern Blue philosophy, sigil codex, agent alignment, manifesto (reference material, not required reading for code changes)
- `docs/history/` — upgrade log, release notes, consolidation summary (historical, frozen in time)

Start at [`docs/README.md`](docs/README.md) for the full reading order.

## Dev commands

```bash
# Web terminal (full swarm UI)
python web_ui/app.py

# Cloud terminal (Grok/xAI)
python python/redacted_terminal_cloud.py

# x402 gateway
cd x402.redacted.ai && bun run index.js
```

See [`README.md#quick-start`](README.md) for per-service run instructions.

## Notes for working in this repo

- Never commit real credentials to `.env` files or docs — `.env.example` per service documents required vars.
- Conversation data (history, vault, soul, whispers) lives on the `/data` volume only, never in the repo.
- License is VPL (Viral Public License) — see [LICENSE](LICENSE).
