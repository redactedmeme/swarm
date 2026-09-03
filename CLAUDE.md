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
| `packages/swarm-core/` | Shared library: committee deliberation, BEAM-SCoT, {7,3} hyperbolic kernel, lore vault, agent registry, session store, schedulers, **`swarm_core.security`** (see below). Was `python/` + `kernel/` + `core/` + `llm/`. |
| `packages/swarm-tg/` | Telegram formatting + swarm task client, shared by all four bots. Was `shared/`. |
| `packages/swarm-agent-base/` | Shared autonomous-agent runtime: the heartbeat / SwarmInbox-poll / soul-update / mesh-thought loops (`AgentRuntime`), one LLM client, soul store, activity log. Used by `apps/degen`, `apps/govimprover`. |
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
| `apps/settler/` | Settlement ledger + on-chain burn executor — the only treasury-key holder | umbrel |
| `apps/degen/` | RedactedDegen — Solana LP scout (Raydium/Orca/Meteora → mesh signals) | umbrel |
| `apps/govimprover/` | RedactedGovImprover — Realms DAO proposal architect (draft only) | umbrel |
| `apps/x402/`, `apps/arb-keeper/`, `apps/mcp/` | Dormant / stubs | — |

### Build contexts — the one rule that matters

A service builds with the **repo root** as its Docker context if it imports the
shared packages (`hermes`, `smolting`, `chan`, `refinery`, `runtime`,
`terminal`, `settler`, `degen`, `govimprover`, `builder`), because the image
must `COPY packages/`. Self-contained services (`proxy`, `dashboard`,
`webchat`, `website`) keep their own directory as context so their builds stay
small.

`builder` moved onto the repo root on 2026-09-03. It was self-contained until
`3a56377` turned its `swarm_inbox.py` / `task_client.py` into re-export shims
over `swarm_core` / `swarm_tg` — after which the *next* rebuild of the old
context would have died at `main.py:46` with `ModuleNotFoundError`. The running
container predated the shims, so the breakage stayed latent for two days.

Getting this wrong is the repo's classic outage: a service that builds from the
wrong root picks up the wrong entrypoint and crash-loops. Check
`infra/umbrel/swarm-infra-docker-compose.yml` and the Railway `rootDirectory`
before changing a build.

## Security — `swarm_core.security` (IronClaw model)

Defense-in-depth adopted from [nearai/ironclaw](https://github.com/nearai/ironclaw).
Use these instead of ad-hoc equivalents:

| Import | Use for |
|---|---|
| `leakscan.scan / redact` | catch secret-shaped strings in any outbound text |
| `promptguard.guard / wrap_untrusted` | fence + scan untrusted content (web, chat, tool output, inbox payloads) before it hits a prompt |
| `audit.record / verify_chain` | the tamper-evident audit log — hash-chained JSONL + `swarm:audit` Redis stream |
| `authz.require / is_admin` | capability check before a privileged action; `is_admin` is fail-closed |
| `identity.AgentId` | validate an agent name at a trust boundary |
| `inbox` | signed SwarmInbox (HMAC + route table) — the one bus; `apps/{hermes,builder,smolting,chan}/swarm_inbox.py` are now re-export shims. `complete_message` mirrors the result onto `payload.reply_key` for chan↔hermes |
| `secrets.get_secret` | resolve a secret (cache → tmpfs file → env → Vaultwarden) instead of `os.getenv` |

## Solana — `swarm_core.solana`

| Import | Use for |
|---|---|
| `keystore` | encrypted per-agent wallet store (`data_dir()/agent_wallets.enc`, Fernet + `SWARM_WALLET_KEK`); `generate / get_keypair / get_address / all_addresses` |
| `wallets` | read-only SOL + $REDACTED balances and `manifest()` (RPC via `x402.rpc`) |
| `reserve` | the Swarm SOL Reserve — auto-refuels low agent wallets from inside `apps/settler`. Dry-run unless `RESERVE_EXECUTE=true`; per-agent daily cap + cooldown; `funds.refuel` cap (not approval-gated by design) |

Driven from the `swarm` CLI (`swarm wallets …`, `swarm reserve …`).

Services: `apps/exec-runner` (no-secrets/no-network code sandbox, unix socket) and
`apps/swarm-egress` (per-agent egress allowlist + outbound leak scan). `apps/secrets-init`
is the one-shot Vaultwarden→tmpfs sidecar.

Config: `packages/swarm-core/src/swarm_core/security/{policy,caps,egress}.yaml`.
Rollout is staged via env — `SWARM_INBOX_ENFORCE`, `LLM_DIRECT_FALLBACK`,
`TOOL_DISPATCH_ALLOW_SPAWN`. Remaining cutover steps are in `handoff.md`.

## Docs — pulled in only when relevant

- `docs/architecture/` — kernel bridge, ADR, integration guide, technical overview, full terminal-command reference, full directory tree
- `docs/lore/` — Pattern Blue philosophy, sigil codex, agent alignment, manifesto (reference material, not required reading for code changes)
- `docs/history/` — upgrade log, release notes, consolidation summary (historical, frozen in time)

Start at [`docs/README.md`](docs/README.md) for the full reading order.

## Dev commands

```bash
# Install the shared packages once (editable), then any app can import them
pip install -e packages/swarm-core -e packages/swarm-tg -e packages/swarm-agent-base

# swarm CLI — roster / status / wallets / reserve / delegate / mesh / committee
swarm --help            # (console script from swarm-core; or: python -m swarm_core.cli)
python scripts/build_executables.py   # -> dist/swarm[.exe] + dist/swarm.pyz
python scripts/install_claude_skill.py --project   # installable Claude skill

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
