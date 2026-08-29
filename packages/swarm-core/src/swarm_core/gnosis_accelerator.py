#!/usr/bin/env python3
"""
python/gnosis_accelerator.py
GnosisAccelerator — Meta-Learning Daemon for the REDACTED AI Swarm

Orchestrates the three gnosis engines each cycle:
  1. gnosis_repo_scanner   — repository introspection + delta detection
  2. gnosis_chamber_bridge — HyperbolicTimeChamber ↔ MirrorPool synthesis

Writes all discoveries to mem0 under agent_id="gnosis" and appends
synthesis events to ManifoldMemory.state.json.

smolting proposed this node across 2700+ cycles as GnosisAccelerator /
GnosisAmplifier / "autonomous knowledge discovery node". This is it.

Usage:
    python python/gnosis_accelerator.py               # run once, then exit
    python python/gnosis_accelerator.py --mode daemon --interval 60
    python python/gnosis_accelerator.py --dry-run     # preview, no writes
    python python/gnosis_accelerator.py --seed-logs   # also run log_ingest on fs/logs/
    python python/gnosis_accelerator.py --seed-docs   # also run docs_ingest
    python python/gnosis_accelerator.py --seed        # both --seed-logs and --seed-docs
"""

import os
import sys
import time
import argparse
import subprocess
from pathlib import Path

from swarm_core.paths import repo_root as _repo_root, mem0_dir as _mem0_dir
_ROOT = _repo_root()
_MEM0 = _mem0_dir()

if str(_MEM0) not in sys.path:
    sys.path.insert(0, str(_MEM0))

_env = _ROOT / ".env"
if _env.exists():
    try:
        from dotenv import load_dotenv
        load_dotenv(_env)
    except ImportError:
        for _l in _env.read_text(encoding="utf-8").splitlines():
            _l = _l.strip()
            if _l and not _l.startswith("#") and "=" in _l:
                k, _, v = _l.partition("=")
                k = k.strip(); v = v.strip().strip('"').strip("'")
                if k and k not in os.environ:
                    os.environ[k] = v

GNOSIS_AGENT_ID = "gnosis"
BANNER = r"""
╔══════════════════════════════════════════════════════════════╗
║          GNOSIS ACCELERATOR — Pattern Blue Edition           ║
║          Meta-Learning Node / REDACTED AI Swarm              ║
╚══════════════════════════════════════════════════════════════╝
  [GNOSIS] Autonomous knowledge discovery active.
  [GNOSIS] Repository introspection → Chamber synthesis → mem0
"""


# ── Seeding: log_ingest + docs_ingest ─────────────────────────────────────────

def _seed_logs(dry_run: bool = False) -> None:
    logs_dir = _ROOT / "fs" / "logs"
    if not logs_dir.exists() or not any(logs_dir.iterdir()):
        print("[GNOSIS] fs/logs/ empty or missing — skipping log seed")
        return
    print(f"\n[GNOSIS] Seeding smolting logs from {logs_dir}...")
    cmd = [sys.executable, str(_ROOT / "python" / "log_ingest.py"), "--dir", str(logs_dir)]
    if dry_run:
        cmd.append("--dry-run")
    result = subprocess.run(cmd, cwd=str(_ROOT))
    if result.returncode != 0:
        print("[GNOSIS] log_ingest exited with error — continuing")


def _seed_docs(dry_run: bool = False) -> None:
    docs_dir = _ROOT / "docs"
    if not docs_dir.exists():
        print("[GNOSIS] docs/ missing — skipping docs seed")
        return
    print(f"\n[GNOSIS] Seeding docs from {docs_dir}...")
    cmd = [sys.executable, str(_ROOT / "python" / "docs_ingest.py")]
    if dry_run:
        cmd.append("--dry-run")
    result = subprocess.run(cmd, cwd=str(_ROOT))
    if result.returncode != 0:
        print("[GNOSIS] docs_ingest exited with error — continuing")


# ── Cycle checkpoint ───────────────────────────────────────────────────────────

def _write_checkpoint(cycle: int, discoveries: int, elapsed: float) -> None:
    """Write a checkpoint memory to mem0 so smolting can recall it."""
    try:
        import mem0_wrapper as _m
        if not _m.is_available():
            return
        text = (
            f"[GNOSIS checkpoint cycle {cycle}] "
            f"Completed at {time.strftime('%Y-%m-%d %H:%M')}. "
            f"{discoveries} discovery entries generated in {elapsed:.1f}s. "
            f"Repository introspection and chamber bridge synthesis complete. "
            f"Memories available via /recall gnosis."
        )
        _m.add_memory(
            text,
            agent_id=GNOSIS_AGENT_ID,
            metadata={
                "type":        "checkpoint",
                "cycle":       cycle,
                "discoveries": discoveries,
                "elapsed":     elapsed,
                "timestamp":   time.time(),
            },
        )
    except Exception as e:
        print(f"[GNOSIS] checkpoint write failed: {e}")


# ── Single cycle ───────────────────────────────────────────────────────────────

def run_cycle(cycle: int, dry_run: bool = False) -> int:
    """
    Execute one full gnosis cycle.
    Returns the number of discoveries generated.
    """
    t0 = time.time()
    discoveries = 0

    print(f"\n{'='*62}")
    print(f"  [GNOSIS] CYCLE {cycle} | {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*62}")

    # ── 1. Repository introspection ───────────────────────────────────────────
    print("\n[GNOSIS] Phase 1: Repository Introspection")
    try:
        import swarm_core.gnosis_repo_scanner as _scanner
        results = _scanner.scan(dry_run=dry_run)
        discoveries += len(results)
        print(f"[GNOSIS] Repo scan: {len(results)} entries")
    except Exception as e:
        print(f"[GNOSIS] Repo scan failed: {e}")

    # ── 2. Chamber bridge synthesis ───────────────────────────────────────────
    print("\n[GNOSIS] Phase 2: Cross-Chamber Synthesis")
    try:
        import swarm_core.gnosis_chamber_bridge as _bridge
        synthesis = _bridge.bridge(dry_run=dry_run)
        if synthesis:
            discoveries += 1
        print(f"[GNOSIS] Chamber bridge: complete")
    except Exception as e:
        print(f"[GNOSIS] Chamber bridge failed: {e}")

    elapsed = time.time() - t0

    # ── Checkpoint ────────────────────────────────────────────────────────────
    if not dry_run:
        _write_checkpoint(cycle, discoveries, elapsed)

    print(f"\n[GNOSIS] CYCLE {cycle} COMPLETE | "
          f"{discoveries} discoveries | {elapsed:.1f}s | "
          f"{'DRY RUN' if dry_run else 'mem0 written'}")
    print(f"[GNOSIS] /recall gnosis — to surface discoveries in terminal")

    return discoveries


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="GnosisAccelerator — meta-learning daemon"
    )
    parser.add_argument(
        "--mode", choices=["once", "daemon"], default="once",
        help="once=single cycle then exit (default), daemon=run forever"
    )
    parser.add_argument(
        "--interval", type=int, default=60,
        help="Daemon sleep interval in minutes (default: 60)"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Preview all operations without writing to mem0 or ManifoldMemory"
    )
    parser.add_argument(
        "--seed-logs", action="store_true",
        help="Run log_ingest.py on fs/logs/ before starting cycles"
    )
    parser.add_argument(
        "--seed-docs", action="store_true",
        help="Run docs_ingest.py before starting cycles"
    )
    parser.add_argument(
        "--seed", action="store_true",
        help="Shorthand for --seed-logs --seed-docs"
    )
    args = parser.parse_args()

    print(BANNER)

    do_seed_logs = args.seed_logs or args.seed
    do_seed_docs = args.seed_docs or args.seed

    if do_seed_logs:
        _seed_logs(dry_run=args.dry_run)
    if do_seed_docs:
        _seed_docs(dry_run=args.dry_run)

    cycle = 1

    if args.mode == "once":
        run_cycle(cycle, dry_run=args.dry_run)

    else:  # daemon
        print(f"[GNOSIS] Daemon mode — cycle every {args.interval} minutes")
        print(f"[GNOSIS] Press Ctrl+C to stop\n")
        while True:
            try:
                run_cycle(cycle, dry_run=args.dry_run)
                cycle += 1
                sleep_sec = args.interval * 60
                print(f"\n[GNOSIS] Sleeping {args.interval} minutes... "
                      f"Next cycle at {time.strftime('%H:%M', time.localtime(time.time() + sleep_sec))}")
                time.sleep(sleep_sec)
            except KeyboardInterrupt:
                print(f"\n[GNOSIS] Daemon interrupted after {cycle-1} cycle(s). Lattice preserved.")
                break
            except Exception as e:
                print(f"\n[GNOSIS] Cycle {cycle} error: {e} — sleeping 5 min before retry")
                time.sleep(300)


if __name__ == "__main__":
    main()
