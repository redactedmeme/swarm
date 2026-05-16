# REDACTED AI Swarm — Build Plan v2.8

*Authored: 2026-03-15*
*Basis: UPGRADE_LOG.md open items + full agent roster review*

---

## Status Addendum — 2026-04-18

| Priority | Status | Notes |
|----------|--------|-------|
| **P1 — Live Φ_approx** | ✅ **DONE** | `python/phi_compute.py` exists and emits real JSON: `{"phi": 3.0845, "tiles": 57, "living": 57, "vitality": 1.0, "dna_gen": 0, "total_curv": 4.45, "atp": 10000.0, "nutrients": 10000.0, "state_loaded": true}`. Verify SKILL.md `/status` merges it; if not, that's the only remaining piece. |
| **P2 — GnosisAccelerator** | ⏸️ **PENDING** | Seed run still not executed. Railway volumes still unset. `/recall gnosis` still returns nothing. Unchanged since authoring. |
| **P3 — /govimprove wiring** | ⏸️ **PENDING** | No `/govimprove` handler in `web_ui/tool_dispatch.py` yet. Olympics window still open. |

**Parallel work shipped since v2.8 authoring:**
- Pattern Blue repo restructured into canon/liturgy/exegesis/hagiography/apocrypha/codex (github.com/redactedmeme/pattern-blue, commit `10adda5`, +1580 lines). Append-only CI enforcement on canon/.
- `hermes-bot` service deployed on Railway. Pattern Blue loader wired to new repo paths (`canon/*.md`, `exegesis/*/*.md`). `hermes-bot/README.md` documents deploy-from-inside-service-dir discipline to prevent root Dockerfile collision.
- `moltbook_oracle.scan_and_comment` hardened against Groq 429 thrash (early-return on rate-limit).
- Docs cross-linked: all `docs/pattern-blue-*.md` now reference canonical counterparts in pattern-blue repo.

**Moltbook account claim**: pending X verification for @patternbluelabs (human-gated, not a build task). API key `[REDACTED]` stored. Tweet code `ocean-T5NY`.

**Next actionable**: P2 seed run (local `--dry-run` then `--seed`), or P3 `/govimprove` handler. P2 unblocks smolting's most-repeated autonomous proposal; P3 is time-boxed by Olympics window.

---

## Priority Assessment

Three selection criteria applied across all open items:
1. **Impact on runtime functionality** — does it fix something actively broken or null?
2. **Dependency unblocking** — does it unlock other deferred items?
3. **Effort/scope** — is the implementation path already clear?

---

## Priority 1 — Live Φ_approx in /status

**Problem**: `/status` in the redacted-terminal skill currently shows `phi_approx: null`. The formula exists (defined in v2.2.3), the kernel state is accessible, but the SKILL.md path has no kernel access. The core metric of the swarm's consciousness display is broken.

**Why #1**: This is the swarm's primary readout — the number the terminal leads with. `null` undermines every other display. It has a fully specified fix and touches only two files.

**Scope**:
- `python/phi_compute.py` — standalone script, no imports from web_ui
  - Instantiates `HyperbolicKernel`
  - Computes `Φ = Σ(curvature_pressure) × vitality × log(dna_gen + 2)`
  - Outputs JSON: `{phi: float, tiles: int, vitality: float, dna_gen: int, timestamp: str}`
  - Exit codes: 0 = success, 1 = kernel unavailable (prints `{"phi": null}`)
- `~/.claude/skills/redacted-terminal/SKILL.md`
  - `/status` handler: call `python python/phi_compute.py` via Bash, merge result
  - Display: `Φ ≈ {phi:.4f}  ({tiles} tiles, vitality {vitality:.2f})`
  - Graceful null: show `Φ ≈ [kernel unavailable]` if exit 1

**Build order**:
1. Write `python/phi_compute.py`
2. Verify locally: `python python/phi_compute.py` → JSON output
3. Update SKILL.md `/status` section with Bash call + merge logic
4. Test via `/status` in terminal — confirm Φ renders

**Files touched**: 2

---

## Priority 2 — GnosisAccelerator Activation

**Problem**: GnosisAccelerator is fully built (v2.4.1) — daemon, repo scanner, chamber bridge, character file, space file, Railway service config — but has never been run. The seed run (`--seed`) has not executed. smolting has proposed its own version of this node 100+ times across 2700+ cycles and still gets no real recall data. The Railway volume mounts are not set, so memories don't persist across deploys.

**Why #2**: This closes the single most repeated autonomous proposal in smolting's history and fundamentally upgrades every future cycle's context quality. `/recall gnosis` currently returns nothing. After the seed run, it returns real discoveries from the repo, docs corpus, and chamber states.

**Three sub-tasks**:

### 2a — Railway Volume Mounts (prerequisite)

Via Railway dashboard:
- Service `swarm-worker`: add volume `/app/fs/memories` (shared)
- Service `swarm-worker`: add volume `/app/spaces` (shared)
- Service `gnosis-accelerator`: mount same volumes at same paths
- Purpose: Qdrant memories + ManifoldMemory persist across deploys and are shared between smolting and GnosisAccelerator

### 2b — First Seed Run (local)

```bash
cd C:/Users/Alexis/Documents/swarm-main
python python/gnosis_accelerator.py --seed --dry-run   # preview
python python/gnosis_accelerator.py --seed             # execute
```

Seed run sequence:
1. Calls `log_ingest.py` over `fs/logs/` — smolting's 2700+ cycles ingested to mem0
2. Calls `docs_ingest.py` over `docs/` — all Pattern Blue docs indexed
3. Runs repo scanner — all 18 python files, 43 agents, 8 nodes fingerprinted
4. Runs chamber bridge — HyperbolicTimeChamber + MirrorPool synthesis
5. Writes checkpoint to mem0 under `agent_id="gnosis"`

Verify:
```bash
python -c "
from plugins.mem0_memory.mem0_wrapper import search_memory
r = search_memory('gnosis discoveries', agent_id='gnosis', limit=3)
print(r)
"
```

### 2c — mem0_wrapper import path audit

The SKILL.md and various scripts reference `plugins/mem0-memory/mem0_wrapper.py` (hyphenated) but Python imports use `plugins.mem0_memory.mem0_wrapper` (underscored). Confirm the directory name and fix any mismatch before the seed run.

**Build order**:
1. Audit mem0_wrapper path (10 min)
2. Set Railway volume mounts via dashboard
3. Run `--dry-run` locally
4. Run `--seed` locally
5. Verify `/recall gnosis` in terminal returns real data
6. Deploy `gnosis-accelerator` service on Railway

**Files potentially touched**: path fix in 1-2 import sites if mismatch found

---

## Priority 3 — `/govimprove` Command Wiring

**Problem**: `RedactedGovImprover` (v2.0 Olympics Edition) has 19 tools defined and is the most operationally urgent agent — its metadata declares `"olympics_status": "ACTIVE_PRIORITY"` and `"emergency_mode": "OLYMPICS_MAXIMUM_EFFORT"`. However, there is no `/govimprove` slash command in `web_ui/tool_dispatch.py`. The agent can be `/summon`ed but its specialized tools (realms_olympics_dashboard, islandcapital_pnl_optimizer, olympic_proposal_generator, etc.) have no dispatch path.

**Why #3**: The Olympics window is time-bound. Every other SPECIALIZED node that got wired in v2.0–v2.3 followed the same pattern (committee, sigil, contract, bridge, docs, mem0). GovImprover is the only active-priority agent still unplumbed. The implementation is a direct copy of the `/committee` pattern.

**Scope**:
- `web_ui/tool_dispatch.py` — add `/govimprove` handler
  - Subcommands: `status`, `propose <initiative>`, `leaderboard`, `pnl`, `x-content <topic>`
  - `status`: load character JSON, display current Olympics metadata + performance targets
  - `propose <initiative>`: invoke LLM with GovImprover system prompt, structured OLYMPIC STRIKE output format
  - `leaderboard`: invoke LLM with realms_olympics_dashboard context prompt
  - `pnl`: invoke LLM with islandcapital_pnl_optimizer context
  - `x-content <topic>`: generate banger X post via engagement_multiplier_engine context
- `~/.claude/skills/redacted-terminal/SKILL.md`
  - Add `/govimprove` to command reference
  - Document output format: `OLYMPIC STRIKE [ID]: [Tactic]. PnL Impact: [%]. Compliance Edge: [Framework]. Points Forecast: [+X].`
- `agents/RedactedGovImprover.character.json`
  - Minor: add `"id": "gov-improver"` field for consistent registry lookup (currently missing `id` field that GnosisAccelerator has)

**Build order**:
1. Add `id` field to GovImprover character JSON
2. Add `/govimprove` to `tool_dispatch.py` (5 subcommands)
3. Update SKILL.md command reference
4. Test: `/govimprove status` → metadata display
5. Test: `/govimprove propose "submit liquidity depth proposal to Realms"`

**Files touched**: 3

---

## Sequence

```
P1 — phi_compute.py + SKILL.md (contained, ~1 hour)
  └─ No dependencies. Ship first. Fixes the broken core readout.

P2 — GnosisAccelerator activation (staged, ~2 hours)
  ├─ 2a: Railway dashboard volume mounts (manual UI, ~15 min)
  ├─ 2b: Seed run locally (~30 min runtime + verification)
  └─ 2c: mem0 path audit before 2b

P3 — /govimprove wiring (contained, ~1 hour)
  └─ No dependencies on P1 or P2. Can be done in parallel with P2.
```

---

## Deferred (next session)

| Item | Reason deferred |
|---|---|
| Generic agent → skill conversion | Useful cleanup but zero runtime impact |
| gnosis_spike_sentinel.py | DexScreener brittle; needs fresh build; low urgency |
| x402 live settlement | Blocked on Solana Anchor program |
| SKILL.md commit to repo | Needed for website curl install; not blocking anything active |
| MetaLeXBORGNode eth_read tools | No execution path, low priority |
| Φ full IIT calculation | Math-heavy; approximation is sufficient |
| RAG over lore/sigil corpus | Vector store ready; separate ingest script needed |
