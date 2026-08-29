#!/usr/bin/env python3
"""
python/phi_compute.py
Standalone Φ (phi) approximation script for the REDACTED AI Swarm.

Instantiates HyperbolicKernel, reads live organism state, and computes:
    Φ_approx = Σ(curvature_pressure) × vitality × log(dna_gen + 2)

If fs/kernel_state.json exists (written by kernel_seed.py), loads persisted
tile curvature pressures and dna_gen into the kernel before computing.
This allows Φ to accumulate across sessions.

Outputs JSON to stdout. Used by the redacted-terminal SKILL.md /status handler.

Exit codes:
    0 — success (phi value in output)
    1 — kernel unavailable (phi: null in output)

Usage:
    python python/phi_compute.py
"""

import sys
import json
import math
from pathlib import Path

from swarm_core.paths import repo_root as _repo_root
_REPO_ROOT  = _repo_root()
_STATE_FILE = _REPO_ROOT / "fs" / "kernel_state.json"



def _load_kernel_state() -> dict:
    """Load persisted tile curvature state from kernel_seed.py output."""
    if _STATE_FILE.exists():
        try:
            return json.loads(_STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def _inject_state(tiles: dict, saved: dict) -> int:
    """Inject saved curvature pressures into live kernel tiles. Returns count injected."""
    tile_state = saved.get("tiles", {})
    injected = 0
    for key, pressure in tile_state.items():
        try:
            x, y = map(float, key.split(","))
            tile = tiles.get((x, y))
            if tile is not None:
                tile.curvature_pressure = pressure
                injected += 1
        except (ValueError, KeyError):
            pass
    return injected


def compute_phi() -> dict:
    from hyperbolic_kernel import HyperbolicKernel
    kernel = HyperbolicKernel()
    org    = kernel.organism
    tiles  = kernel.tiles

    # Load persisted state if available
    saved = _load_kernel_state()
    if saved:
        _inject_state(tiles, saved)
        saved_gen = saved.get("dna_gen", 0)
        if saved_gen > org.dna.generation:
            org.dna.generation = saved_gen

    total_tiles  = len(tiles)
    living_tiles = sum(
        1 for t in tiles.values()
        if hasattr(t, 'health') and str(t.health.value) != 'dead'
    )
    total_curv = sum(getattr(t, 'curvature_pressure', 0.0) for t in tiles.values())
    vitality   = (living_tiles / total_tiles) if total_tiles else 0.0
    dna_gen    = org.dna.generation

    phi = total_curv * vitality * math.log(dna_gen + 2)

    circ      = org.circulatory
    atp       = getattr(circ, 'atp_reserves',      getattr(circ, 'atp_reserve',      0.0))
    nutrients = getattr(circ, 'nutrient_reserves', getattr(circ, 'nutrients_reserve', 0.0))

    return {
        "phi":        round(phi, 4),
        "tiles":      total_tiles,
        "living":     living_tiles,
        "vitality":   round(vitality, 4),
        "dna_gen":    dna_gen,
        "total_curv": round(total_curv, 4),
        "atp":        round(atp, 1),
        "nutrients":  round(nutrients, 1),
        "state_loaded": bool(saved),
    }


def main():
    try:
        result = compute_phi()
        print(json.dumps(result))
        sys.exit(0)
    except Exception as e:
        print(json.dumps({"phi": None, "error": str(e)}))
        sys.exit(1)


if __name__ == "__main__":
    main()
