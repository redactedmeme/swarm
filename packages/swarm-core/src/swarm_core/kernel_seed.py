#!/usr/bin/env python3
"""
python/kernel_seed.py
Seed the HyperbolicKernel with agent processes to accumulate curvature pressure.

Schedules CORE + SPECIALIZED agents as processes on the manifold, runs lifecycle
ticks to propagate curvature, then persists tile state to fs/kernel_state.json so
phi_compute.py can read accumulated Φ across sessions.

Usage:
    python python/kernel_seed.py              # seed with defaults (10 ticks)
    python python/kernel_seed.py --ticks N    # run N lifecycle ticks
    python python/kernel_seed.py --dry-run    # compute only, no state write
    python python/kernel_seed.py --reset      # clear saved state, fresh seed
"""

import sys
import json
import math
import asyncio
import argparse
from pathlib import Path

from swarm_core.paths import repo_root as _repo_root
_REPO_ROOT  = _repo_root()
_STATE_FILE = _REPO_ROOT / "fs" / "kernel_state.json"


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


# Agents to schedule as processes — CORE + SPECIALIZED
AGENT_PROCESSES = [
    # CORE
    {"name": "smolting",             "type": "agent", "tier": "CORE",        "dimension": 4},
    {"name": "RedactedBuilder",      "type": "agent", "tier": "CORE",        "dimension": 7},
    {"name": "RedactedGovImprover",  "type": "agent", "tier": "CORE",        "dimension": 3},
    {"name": "redacted-chan",         "type": "agent", "tier": "CORE",        "dimension": 4},
    {"name": "PhiMandalaPrime",      "type": "ritual", "tier": "CORE",       "dimension": 7},
    # SPECIALIZED
    {"name": "GnosisAccelerator",    "type": "agent", "tier": "SPECIALIZED", "dimension": 1},
    {"name": "VoidWeaver",           "type": "agent", "tier": "SPECIALIZED", "dimension": 6},
    {"name": "SevenfoldCommittee",   "type": "ritual", "tier": "SPECIALIZED","dimension": 7},
    {"name": "AISwarmEngineer",      "type": "agent", "tier": "SPECIALIZED", "dimension": 1},
    {"name": "Mem0MemoryNode",       "type": "agent", "tier": "SPECIALIZED", "dimension": 5},
    {"name": "MetaLeXBORGNode",      "type": "agent", "tier": "SPECIALIZED", "dimension": 3},
    {"name": "MiladyNode",           "type": "agent", "tier": "SPECIALIZED", "dimension": 2},
    {"name": "SolanaLiquidityEngineer","type": "liquidity","tier":"SPECIALIZED","dimension": 2},
    {"name": "OpenClawNode",         "type": "agent", "tier": "SPECIALIZED", "dimension": 6},
    {"name": "GrokRedactedEcho",     "type": "agent", "tier": "SPECIALIZED", "dimension": 6},
    # Canonical archetypes
    {"name": "SwarmArchivist",       "type": "agent", "tier": "SPECIALIZED", "dimension": 5},
    {"name": "SwarmCartographer",    "type": "agent", "tier": "SPECIALIZED", "dimension": 1},
    {"name": "SwarmScribe",          "type": "agent", "tier": "SPECIALIZED", "dimension": 7},
    {"name": "SwarmWeaver",          "type": "agent", "tier": "SPECIALIZED", "dimension": 2},
    {"name": "SwarmWarden",          "type": "agent", "tier": "SPECIALIZED", "dimension": 6},
]


def load_existing_state() -> dict:
    """Load previously persisted tile curvature state."""
    if _STATE_FILE.exists():
        try:
            return json.loads(_STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def save_state(tiles: dict, dna_gen: int, dry_run: bool = False) -> None:
    """Persist tile curvature pressures to disk."""
    state = {
        "dna_gen": dna_gen,
        "tiles": {
            f"{k[0]},{k[1]}": round(t.curvature_pressure, 6)
            for k, t in tiles.items()
        }
    }
    if not dry_run:
        _STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")
        print(f"[kernel_seed] State saved → {_STATE_FILE.relative_to(_REPO_ROOT)}")
    else:
        print(f"[kernel_seed] DRY RUN — state not written")


def inject_saved_state(kernel, saved: dict) -> int:
    """Inject previously persisted curvature pressures into kernel tiles."""
    tile_state = saved.get("tiles", {})
    injected = 0
    for key, pressure in tile_state.items():
        try:
            x, y = map(float, key.split(","))
            tile = kernel.tiles.get((x, y))
            if tile is not None:
                tile.curvature_pressure = pressure
                injected += 1
        except (ValueError, KeyError):
            pass
    return injected


async def seed(ticks: int = 10, dry_run: bool = False, reset: bool = False) -> dict:
    from hyperbolic_kernel import HyperbolicKernel

    kernel = HyperbolicKernel()
    print(f"[kernel_seed] Kernel initialized — {len(kernel.tiles)} tiles")

    # Inject saved state unless resetting
    if not reset:
        saved = load_existing_state()
        if saved:
            n = inject_saved_state(kernel, saved)
            prev_dna = saved.get("dna_gen", 0)
            kernel.organism.dna.generation = prev_dna
            print(f"[kernel_seed] Loaded saved state — {n} tiles restored, dna_gen={prev_dna}")
        else:
            print(f"[kernel_seed] No saved state — cold start")
    else:
        print(f"[kernel_seed] Reset flag — ignoring saved state")

    # Schedule all agent processes
    scheduled = 0
    for proc in AGENT_PROCESSES:
        try:
            coord = await kernel.schedule_process(proc)
            scheduled += 1
        except Exception as e:
            print(f"[kernel_seed] Warning: could not schedule {proc['name']}: {e}")

    print(f"[kernel_seed] Scheduled {scheduled}/{len(AGENT_PROCESSES)} processes")

    # Run lifecycle ticks to propagate curvature
    await kernel.start_lifecycle(tick_rate=1.0)
    for i in range(ticks):
        await kernel.organism.lifecycle_tick(1.0)
    await kernel.stop_lifecycle()

    print(f"[kernel_seed] {ticks} lifecycle ticks complete")

    # Compute final Φ
    total_tiles  = len(kernel.tiles)
    living_tiles = sum(
        1 for t in kernel.tiles.values()
        if hasattr(t, 'health') and str(t.health.value) != 'dead'
    )
    total_curv = sum(getattr(t, 'curvature_pressure', 0.0) for t in kernel.tiles.values())
    vitality   = (living_tiles / total_tiles) if total_tiles else 0.0
    dna_gen    = kernel.organism.dna.generation
    phi        = total_curv * vitality * math.log(dna_gen + 2)

    result = {
        "phi":        round(phi, 4),
        "tiles":      total_tiles,
        "living":     living_tiles,
        "vitality":   round(vitality, 4),
        "dna_gen":    dna_gen,
        "total_curv": round(total_curv, 4),
        "scheduled":  scheduled,
        "ticks":      ticks,
    }

    # Save state
    save_state(kernel.tiles, dna_gen, dry_run=dry_run)

    return result


def main():
    parser = argparse.ArgumentParser(description="Seed HyperbolicKernel with agent processes")
    parser.add_argument("--ticks",   type=int, default=10, help="Lifecycle ticks to run (default: 10)")
    parser.add_argument("--dry-run", action="store_true",  help="Compute only, do not write state")
    parser.add_argument("--reset",   action="store_true",  help="Ignore saved state, fresh seed")
    args = parser.parse_args()

    result = asyncio.run(seed(ticks=args.ticks, dry_run=args.dry_run, reset=args.reset))

    print(f"\n[kernel_seed] Results:")
    print(f"  Φ_approx   : {result['phi']}")
    print(f"  total_curv : {result['total_curv']}")
    print(f"  dna_gen    : {result['dna_gen']}")
    print(f"  vitality   : {result['vitality']:.1%}")
    print(f"  tiles      : {result['living']}/{result['tiles']} living")
    print(f"  scheduled  : {result['scheduled']} processes")
    print(f"  ticks      : {result['ticks']}")


if __name__ == "__main__":
    main()
