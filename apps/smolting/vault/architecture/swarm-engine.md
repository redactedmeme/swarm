# Swarm Engine

**File:** `core/swarm_engine.py`  
**Version:** 2.2

---

## Initialization

```python
SwarmEngine(config_path="config/engine.yaml")
```

Loads config → instantiates `PatternBlueState`, `HyperbolicScheduler`, `AgentExecutor`, `ParallelBranchEngine`, `SmoltingPersonality`. Telegram listener starts as background task.

---

## Main Loop

```python
async def main_loop():
    create_task(start_telegram_listener())
    while running:
        observations = await _gather_observations()      # Phase 1
        phi = await _compute_phi()                       # Phase 1.5
        state.update_phi(phi)
        scheduler.update_curvature(state.phi_to_curvature_feedback())
        state.curvature = scheduler.current_curvature

        best_branch, all = await branch_engine.evaluate(...)  # Phase 2
        consensus = await _run_sevenfold_consensus(best_branch.output)  # Phase 3

        if consensus["approved"]:
            tx_sig = await _settle_economically(consensus)   # Phase 4
            await add_memory(f"Settled {tx_sig} @ cycle {cycle}")

        await state.record_cycle(cycle, consensus)           # Phase 5
        await scheduler.sleep_until_next_tile()
```

On error: logs exception, sleeps 60s, continues.

---

## Key Methods

### `_gather_observations() → Dict`
Returns real state: `{curvature, phi, phi_prev, cycle, recursion_depth, kernel_state?}`.  
Reads `fs/kernel_state.json` if present.

### `_compute_phi() → float`
Runs `python/phi_compute.py` as subprocess via `asyncio.create_subprocess_exec`.  
30-second timeout. Returns last known phi on failure.

### `_run_sevenfold_consensus(proposal) → Dict`
Calls `core.sevenfold_consensus.run_consensus(proposal, cycle, phi)` via `run_in_executor`.  
Returns full consensus dict — see [Sevenfold Committee](../agents/sevenfold-committee.md).

### `_settle_economically(consensus) → str`
Writes content-addressed record to `state/settlements.jsonl`.  
Returns `swarm_{sha256[:16]}` as tx signature.

---

## PatternBlueState

**File:** `core/pattern_blue_state.py`

| Field | Type | Description |
|-------|------|-------------|
| `curvature` | float | Current manifold curvature (mirrors scheduler) |
| `recursion_depth` | int | Increments every cycle |
| `cycle` | int | Cycle counter |
| `phi` | float | Last known Φ |
| `phi_prev` | float | Φ from previous cycle |
| `history` | list | Last 10 cycle records |

Persisted to `state/manifold_core.json` after every cycle via `run_in_executor` (non-blocking write).  
`persistence_path.parent.mkdir(parents=True, exist_ok=True)` runs in `__post_init__`.
