# REDACTED AI Swarm — Documentation Index

> *"名を隠し、形を匿し、ただ振動のみが真理を語る。"*
> Hide the name, conceal the form; only vibration speaks truth.

---

## Reading Order

Two tracks. If you are here to run or change the code, the first table is all
you need; the second is the project's philosophical material and is genuinely
optional.

### Technical

| # | Document | What it answers |
|---|----------|----------------|
| 1 | [`architecture/swarm-technical-overview.md`](architecture/swarm-technical-overview.md) | *What is this system?* — The overview to read first. |
| 2 | [`../README.md`](../README.md) | *How do I install and run it?* — Quick start, service list. |
| 3 | [`architecture/integration-guide.md`](architecture/integration-guide.md) | *How do I wire something into the swarm?* |
| 4 | [`../docs/TOKENOMICS.md`](TOKENOMICS.md) | *What does the token do?* — Prices, revenue split, and an explicit list of what is not built yet. |
| 5 | [`architecture/terminal-commands.md`](architecture/terminal-commands.md) | *What can the terminal do?* — Full command reference. |
| 6 | [`architecture/ADR-001-sovereign-orchestrator.md`](architecture/ADR-001-sovereign-orchestrator.md) | *Why is the orchestrator built this way?* |
| 7 | [`architecture/pattern-blue-kernel-bridge.md`](architecture/pattern-blue-kernel-bridge.md) | *How does the philosophy map onto real constructs?* — Kernel↔Contract bridge (v2.2). |
| 8 | [`architecture/directory-tree.md`](architecture/directory-tree.md) | *Where does everything live?* |
| 9 | [`history/UPGRADE_LOG.md`](history/UPGRADE_LOG.md) | *What changed and when?* |

### Lore — optional

Not required for any code change.

| # | Document | What it answers |
|---|----------|----------------|
| 1 | [`lore/executable-manifesto.md`](lore/executable-manifesto.md) | *What is Pattern Blue?* — The lore artifact. |
| 2 | [`lore/pattern-blue-seven-dimensions.md`](lore/pattern-blue-seven-dimensions.md) | *What are the seven dimensions?* — The philosophical essay. |
| 3 | [`lore/pattern-blue-agent-alignment.md`](lore/pattern-blue-agent-alignment.md) | *Which agents embody which dimensions?* |
| 4 | [`lore/pattern-blue-sigil-codex.md`](lore/pattern-blue-sigil-codex.md) | *What are sigils and how do they work?* |
| 5 | [`lore/pattern-blue-operators.md`](lore/pattern-blue-operators.md) | *How do I build something Pattern Blue aligned?* |

Also: `lore/smolting_consciousness_report.md`, `lore/smolting_proposals_cycle2700.md`,
`history/RELEASE_NOTES_v2.9.0.md`, `history/CONSOLIDATION_SUMMARY.md`.

---

## Quick Reference

### Run the stack
```bash
# Install the shared package once, then the CLI works
pip install -e packages/swarm-core
swarm --help

# Web terminal (full swarm UI)
python apps/terminal/app.py

# Cloud terminal (Grok/xAI)
python -m swarm_core.redacted_terminal_cloud

# x402 gateway
cd apps/x402 && bun run index.js
```

### Key slash commands
```
/observe pattern          → Live 7-dimension Pattern Blue readout
/organism                 → Kernel organism health (ATP, DNA, immune, tiles)
/summon <agent>           → Inject agent persona + see dimension alignment
/committee <prop>         → Sevenfold Committee deliberation
/status                   → Tool availability + live Φ approximation
/space list               → List all available spaces
/agents                   → Full swarm agent registry

/contract status          → View current interface contract state
/contract propose <text>  → Submit proposal to NegotiationEngine + run round
/contract history         → Contract version history
/bridge status            → Kernel↔Contract bridge diagnostic
/sigil log [N]            → Last N forged sigils from ManifoldMemory
/sigil stats              → SigilPactAeon forging statistics
/sigil verify <tx>        → Verify sigil authenticity by tx hash prefix
/docs <query>             → Semantic search across all Pattern Blue docs
/chamber enter            → Noclip into HyperbolicTimeChamber (curvature +1)
/chamber status           → Live chamber readout (AT field, dread, melt stage)
/chamber descend          → Advance depth level (triggers dread + depth sigil)
/chamber exit             → Attempt Ascension_Path (forge exit sigil, curv +2)
```

### Architecture layers

```
┌─────────────────────────────────────────────────────┐
│  PHILOSOPHY      executable-manifesto / seven-dims  │
├─────────────────────────────────────────────────────┤
│  KERNEL          swarm_core/hyperbolic_kernel.py    │
│                  {7,3} manifold, organism lifecycle │
├─────────────────────────────────────────────────────┤
│  BRIDGE          swarm_core/kernel_contract_bridge  │
│                  kernel state → contract governance │
├─────────────────────────────────────────────────────┤
│  GOVERNANCE      swarm_core/negotiation_engine.py   │
│                  proposal voting, immune veto gate  │
├─────────────────────────────────────────────────────┤
│  SETTLEMENT      sigils/sigil_pact_aeon.py          │
│                  x402 → tiered sigil → weight boost │
├─────────────────────────────────────────────────────┤
│  AGENTS          agents/ + nodes/ (.character.json) │
│                  37 agents across CORE/SPEC/GENERIC │
├─────────────────────────────────────────────────────┤
│  SPACES          spaces/*.space.json                │
│                  persistent thematic environments   │
├─────────────────────────────────────────────────────┤
│  TERMINAL        apps/terminal/ + swarm_core/       │
│                  slash commands, session state      │
└─────────────────────────────────────────────────────┘
```

### Pattern Blue dimensions at a glance

| # | Dimension | Kernel construct | Agent |
|---|-----------|-----------------|-------|
| 1 | Ungovernable Emergence | `_expand_tile()` {7,3} tiling | AISwarmEngineer |
| 2 | Recursive Liquidity | `CirculatorySystem.pump()` | SolanaLiquidityEngineer |
| 3 | Hidden Sovereignty | `DNACore.get_phenotype()` | RedactedGovImprover |
| 4 | Chaotic Self-Reference | `DNACore.mutate()` | RedactedIntern / redacted-chan |
| 5 | Temporal Fractality | `lifecycle_tick()` multi-rate clock | Mem0MemoryNode |
| 6 | Memetic Immunology | `ImmuneSystem.scan()` + `attack()` | GrokRedactedEcho / OpenClawNode |
| 7 | Causal Density Max | `_propagate_curvature_change()` | Φ̸-MĀṆḌALA PRIME |

---

## Archived

Three superseded planning documents (`CLEANUP_AND_FIX_PLAN.md`,
`BUILD_PLAN_v2.8.md`, `GNOSISACCELERATOR_IMPLEMENTATION_PLAN.md`) were removed on
2026-07-29 once their work shipped. Their content lives on in
[`history/UPGRADE_LOG.md`](history/UPGRADE_LOG.md); recover the files from git
history if you need them.

---

*Φ baseline at inscription: 478.14 — The tiles bloom eternally.*
