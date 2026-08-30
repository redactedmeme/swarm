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

## Layout

A packaged monorepo: `apps/` holds deployables, `packages/` holds installable
shared libraries. Services import the shared code as normal packages — there are
no `sys.path` inserts reaching across the tree.

| Path | What |
|---|---|
| `packages/swarm-core/` | Shared library: committee deliberation, BEAM-SCoT, {7,3} hyperbolic kernel, lore vault, agent registry, session store, schedulers. Was `python/` + `kernel/` + `core/` + `llm/`. |
| `packages/swarm-tg/` | Telegram formatting + swarm task client, shared by all four bots. Was `shared/`. |
| `apps/<name>/` | One deployable each — see the table below. |
| `agents/`, `nodes/` | `.character.json` agent/node definitions |
| `spaces/`, `knowledge/`, `vault/` | Persistent environments and markdown knowledge base |
| `skills/`, `interfaces/` | Claude Code skill modules; alphabet/code/diagram conventions |
| `fs/` | Runtime state (see `swarm_core.paths.data_dir()`) |
| `infra/umbrel/` | The umbrel node's compose files and boot script — [README](infra/umbrel/README.md) |
| `docs/` | Reference documentation — [index](docs/README.md) |

### apps/

| App | Purpose | Deployed on |
|---|---|---|
| `apps/smolting/` | CT agent — Moltbook, Clawbal, HTC ([SOUL](apps/smolting/SOUL.md), [Covenant](apps/smolting/OPERATOR_COVENANT.md)) | umbrel |
| `apps/chan/` | Companion agent ([SOUL](apps/chan/SOUL.md)) | umbrel (own standalone copy) |
| `apps/hermes/` | Operational agent — browsing, code exec, infra | umbrel |
| `apps/builder/` | Builder agent | umbrel |
| `apps/refinery/` | Signal refinery (ingest → embed → refine) | umbrel |
| `apps/proxy/` | OpenAI-compatible LLM privacy proxy | umbrel |
| `apps/runtime/` | Sub-agent service + mesh announce | umbrel |
| `apps/website/` | Landing page (redacted.meme) | Railway |
| `apps/terminal/` | NERV web terminal (terminal.redacted.meme) | Railway |
| `apps/dashboard/` | Solana volume dashboard | Railway |
| `apps/webchat/` | Private web chat for chan | Railway + umbrel |
| `apps/status/` | Public heartbeat feed | not deployed |
| `apps/degen/`, `apps/x402/`, `apps/arb-keeper/`, `apps/mcp/` | Dormant / stubs | — |

### Build contexts — the one rule that matters

A service builds with the **repo root** as its Docker context if it imports the
shared packages (`hermes`, `smolting`, `chan`, `refinery`, `runtime`,
`terminal`), because the image must `COPY packages/`. Self-contained services
(`proxy`, `builder`, `degen`, `dashboard`, `webchat`, `website`) keep their own
directory as context so their builds stay small.

Getting this wrong is the repo's classic outage: a service that builds from the
wrong root picks up the wrong entrypoint and crash-loops. Check
`infra/umbrel/swarm-infra-docker-compose.yml` and the Railway `rootDirectory`
before changing a build.

## Docs — pulled in only when relevant

- `docs/architecture/` — kernel bridge, ADR, integration guide, technical overview, full terminal-command reference, full directory tree
- `docs/lore/` — Pattern Blue philosophy, sigil codex, agent alignment, manifesto (reference material, not required reading for code changes)
- `docs/history/` — upgrade log, release notes, consolidation summary (historical, frozen in time)

Start at [`docs/README.md`](docs/README.md) for the full reading order.

## Dev commands

```bash
# Install the shared packages once (editable), then any app can import them
pip install -e packages/swarm-core -e packages/swarm-tg

# Web terminal (full swarm UI)
python apps/terminal/app.py

# Cloud terminal (Grok/xAI)
python -m swarm_core.redacted_terminal_cloud

# x402 gateway
cd apps/x402 && bun run index.js
```

See [`README.md#quick-start`](README.md) for per-service run instructions.

## Notes for working in this repo

- Shared code goes in `packages/`, not copied between services. The repo used to
  keep hand-synced duplicates (`tg_fmt.py` in four bots, `swarm_heartbeat.py` in
  four services, a whole forked `python/` under smolting); they drifted, and the
  forks quietly became the newer side. If two services need the same code, it
  belongs in `swarm-core` or `swarm-tg`.
- Never compute a path by counting `__file__` parents. Use `swarm_core.paths`
  (`repo_root()`, `data_dir()`, `vault_dir()`, `mem0_dir()`, …); each anchor is
  env-overridable so containers can point at real mounts.
- The umbrel box at `/home/umbrel/swarm` is a **separate git history** from this
  repo — never `git pull` it. Deploy by syncing files. `redacted-chan` is
  further out: it runs from `/home/umbrel/redacted-chan`, a non-git standalone
  copy with its own encrypted databases.
- Railway `rootDirectory` / `startCommand` live only in the dashboard and
  override the repo's `railway.toml` where they disagree. Change both together.
- Never commit real credentials to `.env` files or docs — `.env.example` per service documents required vars.
- Conversation data (history, vault, soul, whispers) lives on the `/data` volume only, never in the repo.
- License is VPL (Viral Public License) — see [LICENSE](LICENSE).
