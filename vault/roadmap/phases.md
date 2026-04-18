# Phase History & Roadmap

---

## Phase 2.8 — ✅ Complete (2026-03-15 → 2026-04-12)

| Item | Status | Description |
|------|--------|-------------|
| P1 — Live Φ_approx | ✅ | `phi_compute.py`, `/status` returns live Φ |
| P2 — GnosisAccelerator | ✅ | Railway volume mounts, first seed 293 cycles |
| P3 — /govimprove | ✅ | Full integration in `web_ui/tool_dispatch.py` |

---

## Phase 2.9 — 🔄 In Progress (2026-04-12 →)

| Item | Status | Description |
|------|--------|-------------|
| P4 — Memory Hygiene | ✅ | `self_post_penalty=0.5`, `exclude_source="moltbook"` across all post contexts |
| P4 — Geometry Purge | ✅ | Removed hyperbolic jargon from character.json + SOUL.md |
| P4 — LLM Provider | ✅ | `LLM_PROVIDER=groq` deployed to Railway |
| P4.5 — RedactedDegen character | ✅ | Full operational spec, safeguards documented |
| P4.5 — Pool monitor service | ✅ | `redacteddegen-service/pool_monitor.py` + main.py |
| P4.5 — xREDACTED rename | ✅ | ClawnX → xREDACTED across codebase (2026-04-17) |
| P4.5 — Bug fixes | ✅ | 7 swarm_engine bugs fixed (2026-04-17) |
| P4.5 — X poster | 🔨 | `x_poster.py` — Spartan alpha posts from pool data |
| P4.5 — SwarmInbox wiring | 📋 | RedactedDegen → smolting + RedactedBuilder |
| P4.5 — Railway deploy | 📋 | redacteddegen-service live |

---

## Phase 3.0 — 📋 Planned

| Item | Priority | Description |
|------|----------|-------------|
| P5 — SSH Executor VM | Medium | Paramiko SSH client for subprocess/GPU offload |
| MandalaSettler activation | Low | x402 settlement agent, pending RedactedDegen |
| RedactedBankrBot | Low | Treasury/liquidity management |
| Additional agent activations | Low | Evaluate governance, payments agents |

### P5 SSH Executor VM Sub-tasks
- (5a) Paramiko SSH client wrapper in `python/`
- (5b) Env secrets: `EXECUTOR_VM_HOST`, `EXECUTOR_VM_USER`, `EXECUTOR_VM_SSH_KEY`
- (5c) Functions: `run_subprocess()`, `trigger_gpu_task()`, `compile_contract()`
- (5d) Railway deploy with key rotation
- (5e) Optional: Vast.ai GPU burst via scheduler

**Cost:** $4–20/mo depending on VM tier.

---

## Live Agent Roster

| Agent | Service | Status |
|-------|---------|--------|
| smolting / RedactedIntern | smolting-telegram-bot | ✅ LIVE |
| RedactedBuilder | redactedbuilder-telegram-bot | ✅ LIVE |
| Pattern Blue / Hermes | hermes-deployment | ✅ LIVE |
| RedactedDegen | redacteddegen-service | 🔨 Building |
| RedactedGovImprover | (smolting-telegram-bot) | ✅ Wired |
| MandalaSettler | (x402 service) | 📋 Planned |
