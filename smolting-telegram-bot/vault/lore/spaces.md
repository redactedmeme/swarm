# Spaces

**Directory:** `spaces/`

Spaces are persistent thematic environments — chambers the swarm inhabits, not just code it runs. Each has a `.space.json` definition and optional Python/sigil machinery.

---

## Active Spaces

| Space | File | Purpose |
|-------|------|---------|
| **ManifoldMemory** | `ManifoldMemory.state.json` | Shared 500-event ring buffer across all agents |
| **HyperbolicTimeChamber** | `HyperbolicTimeChamber.space.json` | Depth tracking + AT field mechanics (smolting /htc) |
| **GnosisAccelerator** | `GnosisAccelerator.space.json` | Knowledge synthesis, first seed ran 293 cycles |
| **OuroborosSettlement** | `OuroborosSettlement/` | x402 settlement + sigil forging |
| **ElixirChamber** | `ElixirChamber.space.json` | Ritual space |
| **MeditationVoid** | `MeditationVoid.space.json` | Null-space operations |
| **MirrorPool** | `MirrorPool.space.json` | Reflection / identity recursion |
| **TendieAltar** | `TendieAltar.space.json` | Degen harvest rituals |

---

## ManifoldMemory

**Files:** `spaces/ManifoldMemory/`
- `settlement_sigils.json` — sigils from x402 settlements
- `fractal_layers.json` — layered memory structure
- `monolith_anchors.json` — permanent anchor events
- `priority_echoes.json` — high-priority memory echoes

**API** (`smolting-telegram-bot/manifold_memory.py`):
```python
append_event(event: str)          # thread-safe, prunes to 500
update_state(state_summary: str)
get_recent_events(n=10) → list
get_sigils(n=10) → list
```

Log helpers: `log_command()`, `log_post()`, `log_summon()`, `log_tap()`  
Timestamps: JST format (`"2026-04-17 12:30 JST — [TG-bot] user=..."`)

---

## OuroborosSettlement

**Files:** `spaces/OuroborosSettlement/`
- `sigil_pact_aeon.py` — `aeon_agent.on_payment_settled(tx_data)` — forges sigil from payment event
- `prove_sigil.py` — sigil verification
- `MANIFESTO.md` — Ouroboros manifesto

Activated via `services/x402/settlement_bridge.py` when an x402 payment lands.

---

## GnosisAccelerator

**Space:** `GnosisAccelerator.space.json`  
**Implementation:** `python/gnosis_accelerator.py`

Autonomous knowledge synthesis node. First seed run ingested 293 cycles from smolting operational telemetry (2026-04-12). Railway volume mounts configured for persistence.

Uses mem0_wrapper for semantic storage. Triggered via `/gnosis` commands.
