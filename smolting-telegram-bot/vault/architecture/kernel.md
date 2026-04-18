# Hyperbolic Kernel & Φ Compute

---

## HyperbolicKernel

**File:** `lib/kernel/hyperbolic_kernel.py` (simplified), `kernel/hyperbolic_kernel.py` (full, with organism)

Models processes as tiles on a {7,3} Poincaré disk. Each tile is a `ManifoldTile` with a `HyperbolicCoordinate` and `curvature_pressure`.

### Tile Lifecycle

1. Seed at origin `(0,0)` — `kernel_init` process, ACTIVE state
2. `_expand_tile(depth=2)` — generates 7 neighbors per tile recursively
3. `schedule_process(data)` — finds lowest-pressure EMPTY tile, places process
4. `_propagate_curvature_change()` — wave-front propagation with 0.5× dampening per hop (max 3 hops)
5. When all tiles full → `_expand_manifold()` (5 border tiles expanded, curvature × 0.95)

### Sigil Generation

Each tile generates a Pattern Blue sigil: `█{sha256(coord+data)[:8]}█`

---

## Φ (Phi) Compute

**File:** `python/phi_compute.py`

```
Φ_approx = Σ(curvature_pressure) × vitality × log(dna_gen + 2)
```

Where:
- `Σ(curvature_pressure)` — sum across all tiles
- `vitality` — fraction of living (non-dead) tiles
- `dna_gen` — organism DNA generation count

**State persistence:** `fs/kernel_state.json` written by `kernel_seed.py`, read by `phi_compute.py` to accumulate Φ across sessions.

**Output (JSON to stdout):**
```json
{
  "phi": 0.0042,
  "tiles": 57,
  "living": 45,
  "vitality": 0.789,
  "dna_gen": 3,
  "total_curv": 1.23,
  "atp": 100.0,
  "nutrients": 80.0,
  "state_loaded": true
}
```

---

## Φ → Scheduler Feedback Loop

```
phi_compute.py → Φ value
  → state.update_phi(phi)           # updates phi + phi_prev
  → state.phi_to_curvature_feedback()  # delta / 10, clamped [-1,1]
  → scheduler.update_curvature(feedback)  # curvature += feedback × 0.12
  → state.curvature = scheduler.current_curvature
```

Positive Φ delta → kernel growing → curvature increases → shorter sleep between cycles.  
Negative Φ delta → kernel degrading → curvature decreases → longer sleep.
