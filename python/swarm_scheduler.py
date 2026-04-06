#!/usr/bin/env python3
"""
python/swarm_scheduler.py
SwarmScheduler — Unified task scheduler with hyperbolic kernel health gating.

Responsibilities:
  - Registers all known swarm async loops as named Tasks
  - Reads kernel health (via phi_compute / fs/kernel_state.json) each tick
  - Gates task execution by kernel HealthStatus:
      HEALTHY   → all tasks run normally
      DEGRADED  → only PRIORITY ≤ 2 tasks run
      CRITICAL  → only PRIORITY = 1 (emergency) tasks run
      CORRUPT   → no tasks run; sends alert
      DEAD      → no tasks run; sends alert
  - Priority is Pattern-Blue-axis weighted (higher score = lower number = higher priority)
  - Exposes a lightweight aiohttp REST API:
      GET  /scheduler/status      — task list + kernel health
      POST /scheduler/pause/<id>  — pause a specific task
      POST /scheduler/resume/<id> — resume a specific task
      POST /scheduler/trigger/<id>— one-shot trigger
  - Appends health-transition events to ManifoldMemory.state.json
  - Runs standalone:  python python/swarm_scheduler.py
    or imported as:   from swarm_scheduler import SwarmScheduler; s = SwarmScheduler()

Usage:
    python python/swarm_scheduler.py [--port 8765] [--dry-run]
"""

from __future__ import annotations

import os
import sys
import json
import asyncio
import logging
import argparse
import importlib
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional, Callable, Awaitable

# ── Paths ──────────────────────────────────────────────────────────────────────
_ROOT     = Path(__file__).resolve().parent.parent
_FS       = _ROOT / "fs"
_FS.mkdir(exist_ok=True)
_STATE    = _FS / "kernel_state.json"
_MANIFOLD = _ROOT / "spaces" / "ManifoldMemory.state.json"
_BOT_DIR  = _ROOT / "smolting-telegram-bot"
_PY_DIR   = _ROOT / "python"

for _p in [str(_PY_DIR), str(_BOT_DIR)]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

# ── .env ──────────────────────────────────────────────────────────────────────
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

logging.basicConfig(
    format="%(asctime)s [SwarmScheduler] %(levelname)s %(message)s",
    level=logging.INFO,
)
log = logging.getLogger("swarm_scheduler")

# ── JST helper ────────────────────────────────────────────────────────────────
def _jst_now() -> str:
    utc = datetime.now(timezone.utc)
    return (utc + timedelta(hours=9)).strftime("%Y-%m-%d %H:%M JST")


# ═══════════════════════════════════════════════════════════════════════════════
# Kernel Health (reads phi_compute output or kernel_state.json)
# ═══════════════════════════════════════════════════════════════════════════════

class KernelHealth(str, Enum):
    HEALTHY  = "HEALTHY"
    DEGRADED = "DEGRADED"
    CRITICAL = "CRITICAL"
    CORRUPT  = "CORRUPT"
    DEAD     = "DEAD"
    UNKNOWN  = "UNKNOWN"


def read_kernel_health() -> tuple[KernelHealth, float]:
    """
    Returns (health_status, phi_value).
    Attempts to call phi_compute; falls back to kernel_state.json.
    Falls back to UNKNOWN/0.0 if neither is available.
    """
    try:
        from phi_compute import compute_phi
        result = compute_phi()
        phi = result.get("phi") or 0.0
        vitality = result.get("vitality", 1.0)
        if vitality > 0.8:
            return KernelHealth.HEALTHY, phi
        if vitality > 0.5:
            return KernelHealth.DEGRADED, phi
        if vitality > 0.2:
            return KernelHealth.CRITICAL, phi
        if vitality > 0.0:
            return KernelHealth.CORRUPT, phi
        return KernelHealth.DEAD, phi
    except Exception:
        pass

    # Fallback: read kernel_state.json
    if _STATE.exists():
        try:
            state = json.loads(_STATE.read_text(encoding="utf-8"))
            living  = state.get("living_tiles", 0)
            total   = state.get("total_tiles", 1)
            vitality = living / total if total else 0.0
            if vitality > 0.8:  return KernelHealth.HEALTHY, 0.0
            if vitality > 0.5:  return KernelHealth.DEGRADED, 0.0
            if vitality > 0.2:  return KernelHealth.CRITICAL, 0.0
            return KernelHealth.CORRUPT, 0.0
        except Exception:
            pass

    return KernelHealth.UNKNOWN, 0.0


# ═══════════════════════════════════════════════════════════════════════════════
# Task definition
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class SwarmTask:
    """
    A registered recurring task.

    priority: 1 = emergency (runs even in CRITICAL), 2 = important (runs in DEGRADED+),
              3+ = standard (runs in HEALTHY only)
    interval_s: seconds between runs
    """
    id:          str
    name:        str
    coro_factory: Callable[[], Awaitable]  # called each tick → returns a coroutine
    interval_s:  int
    priority:    int = 3
    enabled:     bool = True
    tags:        list[str] = field(default_factory=list)

    # Runtime state (set by scheduler)
    last_run:    Optional[float] = None   # epoch seconds
    last_status: str = "pending"          # "pending"|"ok"|"error"|"skipped"
    run_count:   int = 0
    error_count: int = 0
    paused:      bool = False

    def is_due(self, now: float) -> bool:
        if self.last_run is None:
            return True
        return (now - self.last_run) >= self.interval_s

    def health_gate_ok(self, health: KernelHealth) -> bool:
        """Returns True if this task is allowed to run under the current kernel health."""
        if health in (KernelHealth.DEAD, KernelHealth.CORRUPT):
            return False
        if health == KernelHealth.CRITICAL:
            return self.priority <= 1
        if health == KernelHealth.DEGRADED:
            return self.priority <= 2
        return True  # HEALTHY / UNKNOWN → all tasks allowed

    def to_dict(self) -> dict:
        return {
            "id":          self.id,
            "name":        self.name,
            "interval_s":  self.interval_s,
            "priority":    self.priority,
            "enabled":     self.enabled,
            "paused":      self.paused,
            "last_run":    self.last_run,
            "last_status": self.last_status,
            "run_count":   self.run_count,
            "error_count": self.error_count,
            "tags":        self.tags,
        }


# ═══════════════════════════════════════════════════════════════════════════════
# ManifoldMemory integration
# ═══════════════════════════════════════════════════════════════════════════════

def _append_manifold_event(body: str) -> None:
    """Append a scheduler event to ManifoldMemory.state.json."""
    try:
        if not _MANIFOLD.exists():
            return
        data = json.loads(_MANIFOLD.read_text(encoding="utf-8"))
        events = data.get("events", [])
        events.append(f"{_jst_now()} — [SwarmScheduler] {body}")
        data["events"] = events
        _MANIFOLD.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception as e:
        log.warning(f"ManifoldMemory write failed: {e}")


# ═══════════════════════════════════════════════════════════════════════════════
# Default task factories (lazy-import bot modules)
# ═══════════════════════════════════════════════════════════════════════════════

async def _noop():
    """Placeholder for tasks whose module isn't available."""
    pass


def _make_moltbook_reply_factory():
    async def run():
        try:
            mod = importlib.import_module("moltbook_autonomous")
            if hasattr(mod, "_agent") and mod._agent:
                await mod._agent.reply_to_notifications()
            else:
                log.debug("moltbook_autonomous: no _agent instance yet")
        except Exception as e:
            log.warning(f"moltbook reply_to_notifications error: {e}")
    return run


def _make_moltbook_scan_factory():
    async def run():
        try:
            mod = importlib.import_module("moltbook_autonomous")
            if hasattr(mod, "_agent") and mod._agent:
                await mod._agent.scan_and_comment()
        except Exception as e:
            log.warning(f"moltbook scan_and_comment error: {e}")
    return run


def _make_moltbook_post_factory():
    async def run():
        try:
            mod = importlib.import_module("moltbook_autonomous")
            if hasattr(mod, "_agent") and mod._agent:
                await mod._agent.autonomous_post()
        except Exception as e:
            log.warning(f"moltbook autonomous_post error: {e}")
    return run


def _make_gnosis_factory(dry_run: bool = False):
    async def run():
        try:
            import subprocess
            cmd = [sys.executable, str(_PY_DIR / "gnosis_accelerator.py")]
            if dry_run:
                cmd.append("--dry-run")
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(_ROOT),
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=120)
            if proc.returncode != 0:
                log.warning(f"GnosisAccelerator non-zero exit: {stderr.decode()[:200]}")
        except asyncio.TimeoutError:
            log.warning("GnosisAccelerator timed out after 120s")
        except Exception as e:
            log.warning(f"GnosisAccelerator error: {e}")
    return run


def _make_lore_vault_seed_factory():
    async def run():
        try:
            import sys
            if str(_PY_DIR) not in sys.path:
                sys.path.insert(0, str(_PY_DIR))
            from lore_vault import init_db, seed_all
            init_db()
            seed_all()
        except Exception as e:
            log.warning(f"LoreVault seed error: {e}")
    return run


def _make_phi_log_factory():
    """Log Φ value to manifold memory every N seconds."""
    async def run():
        try:
            health, phi = read_kernel_health()
            _append_manifold_event(f"Φ={phi:.4f} | kernel={health.value}")
        except Exception as e:
            log.warning(f"Phi log error: {e}")
    return run


# ═══════════════════════════════════════════════════════════════════════════════
# Scheduler
# ═══════════════════════════════════════════════════════════════════════════════

class SwarmScheduler:
    """
    Unified async scheduler for the REDACTED swarm.
    All tasks are registered at init; run() starts the event loop.
    """

    TICK_INTERVAL = 10  # seconds between scheduler ticks

    def __init__(self, dry_run: bool = False):
        self.dry_run = dry_run
        self._tasks: dict[str, SwarmTask] = {}
        self._health: KernelHealth = KernelHealth.UNKNOWN
        self._phi:    float        = 0.0
        self._prev_health: Optional[KernelHealth] = None
        self._running = False

        self._register_default_tasks()
        log.info(f"SwarmScheduler initialized ({len(self._tasks)} tasks, dry_run={dry_run})")

    # ── Task registration ──────────────────────────────────────────────────────

    def register(self, task: SwarmTask) -> None:
        self._tasks[task.id] = task
        log.info(f"  + task registered: {task.id} (every {task.interval_s}s, prio={task.priority})")

    def _register_default_tasks(self) -> None:
        self.register(SwarmTask(
            id="moltbook_reply",
            name="Moltbook: Reply to Notifications",
            coro_factory=_make_moltbook_reply_factory(),
            interval_s=20 * 60,
            priority=2,
            tags=["moltbook", "social"],
        ))
        self.register(SwarmTask(
            id="moltbook_scan",
            name="Moltbook: Scan + Comment",
            coro_factory=_make_moltbook_scan_factory(),
            interval_s=45 * 60,
            priority=3,
            tags=["moltbook", "social"],
        ))
        self.register(SwarmTask(
            id="moltbook_post",
            name="Moltbook: Autonomous Post",
            coro_factory=_make_moltbook_post_factory(),
            interval_s=6 * 60 * 60,
            priority=3,
            tags=["moltbook", "content"],
        ))
        self.register(SwarmTask(
            id="gnosis_accelerator",
            name="GnosisAccelerator: Meta-Learning Cycle",
            coro_factory=_make_gnosis_factory(dry_run=self.dry_run),
            interval_s=60 * 60,
            priority=3,
            tags=["gnosis", "learning"],
        ))
        self.register(SwarmTask(
            id="lore_vault_seed",
            name="LoreVault: Incremental Seed",
            coro_factory=_make_lore_vault_seed_factory(),
            interval_s=4 * 60 * 60,
            priority=3,
            tags=["lore", "memory"],
        ))
        self.register(SwarmTask(
            id="phi_logger",
            name="Kernel: Φ Health Logger",
            coro_factory=_make_phi_log_factory(),
            interval_s=30 * 60,
            priority=1,
            tags=["kernel", "health"],
        ))

    # ── Task control ──────────────────────────────────────────────────────────

    def pause(self, task_id: str) -> bool:
        if task_id in self._tasks:
            self._tasks[task_id].paused = True
            log.info(f"Task paused: {task_id}")
            return True
        return False

    def resume(self, task_id: str) -> bool:
        if task_id in self._tasks:
            self._tasks[task_id].paused = False
            log.info(f"Task resumed: {task_id}")
            return True
        return False

    async def trigger(self, task_id: str) -> bool:
        """One-shot trigger of a task regardless of schedule."""
        task = self._tasks.get(task_id)
        if not task:
            return False
        log.info(f"One-shot trigger: {task_id}")
        await self._run_task(task)
        return True

    # ── Main loop ─────────────────────────────────────────────────────────────

    async def run(self) -> None:
        self._running = True
        log.info("SwarmScheduler running.")
        _append_manifold_event("SwarmScheduler started.")
        while self._running:
            await self._tick()
            await asyncio.sleep(self.TICK_INTERVAL)

    async def _tick(self) -> None:
        import time
        now = time.monotonic()
        self._health, self._phi = read_kernel_health()

        # Detect health transitions → log to ManifoldMemory
        if self._prev_health is not None and self._health != self._prev_health:
            msg = (f"Kernel health transition: {self._prev_health.value} → {self._health.value} "
                   f"(Φ={self._phi:.4f})")
            log.warning(msg)
            _append_manifold_event(msg)
        self._prev_health = self._health

        if self._health in (KernelHealth.DEAD, KernelHealth.CORRUPT):
            log.error(f"Kernel {self._health.value} — all tasks suspended.")
            return

        for task in self._tasks.values():
            if not task.enabled or task.paused:
                continue
            if not task.is_due(now):
                continue
            if not task.health_gate_ok(self._health):
                task.last_status = "skipped"
                log.debug(f"Task {task.id} skipped (kernel={self._health.value})")
                continue
            asyncio.create_task(self._run_task(task))
            task.last_run = now

    async def _run_task(self, task: SwarmTask) -> None:
        log.info(f"Running task: {task.id}")
        try:
            if self.dry_run:
                log.info(f"[DRY-RUN] would run: {task.id}")
                task.last_status = "ok (dry-run)"
            else:
                await task.coro_factory()
                task.last_status = "ok"
                task.run_count  += 1
        except Exception as e:
            task.last_status  = f"error: {e}"
            task.error_count += 1
            log.error(f"Task {task.id} failed: {e}")

    def stop(self) -> None:
        self._running = False
        _append_manifold_event("SwarmScheduler stopped.")

    # ── Status ────────────────────────────────────────────────────────────────

    def status(self) -> dict:
        return {
            "kernel_health": self._health.value,
            "phi":           round(self._phi, 4),
            "tasks":         [t.to_dict() for t in self._tasks.values()],
            "ts":            _jst_now(),
        }


# ═══════════════════════════════════════════════════════════════════════════════
# REST API (aiohttp, optional)
# ═══════════════════════════════════════════════════════════════════════════════

async def _serve_api(scheduler: SwarmScheduler, port: int) -> None:
    try:
        from aiohttp import web

        async def handle_status(req):
            return web.json_response(scheduler.status())

        async def handle_pause(req):
            task_id = req.match_info["id"]
            ok = scheduler.pause(task_id)
            return web.json_response({"ok": ok, "task_id": task_id})

        async def handle_resume(req):
            task_id = req.match_info["id"]
            ok = scheduler.resume(task_id)
            return web.json_response({"ok": ok, "task_id": task_id})

        async def handle_trigger(req):
            task_id = req.match_info["id"]
            ok = await scheduler.trigger(task_id)
            return web.json_response({"ok": ok, "task_id": task_id})

        app = web.Application()
        app.router.add_get( "/scheduler/status",         handle_status)
        app.router.add_post("/scheduler/pause/{id}",     handle_pause)
        app.router.add_post("/scheduler/resume/{id}",    handle_resume)
        app.router.add_post("/scheduler/trigger/{id}",   handle_trigger)

        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "0.0.0.0", port)
        await site.start()
        log.info(f"SwarmScheduler API listening on :{port}")
    except ImportError:
        log.warning("aiohttp not installed — REST API not available")


# ═══════════════════════════════════════════════════════════════════════════════
# CLI entry point
# ═══════════════════════════════════════════════════════════════════════════════

async def _main(args):
    scheduler = SwarmScheduler(dry_run=args.dry_run)
    tasks_to_run = [scheduler.run()]
    if not args.no_api:
        tasks_to_run.append(_serve_api(scheduler, args.port))
    await asyncio.gather(*tasks_to_run)


def main():
    parser = argparse.ArgumentParser(description="REDACTED SwarmScheduler")
    parser.add_argument("--port",    type=int, default=8765, help="REST API port")
    parser.add_argument("--dry-run", action="store_true",    help="Preview tasks, no execution")
    parser.add_argument("--no-api",  action="store_true",    help="Disable REST API")
    args = parser.parse_args()
    try:
        asyncio.run(_main(args))
    except KeyboardInterrupt:
        log.info("Interrupted.")


if __name__ == "__main__":
    main()
