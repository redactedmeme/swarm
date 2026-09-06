"""swarm_core.routines — turn a recorded workspace action trace into a re-runnable routine.

Grok Bot learns a path once and re-runs it. The distil + improve machinery
already exists (`apps/chan/learning_loop.py`, `skills_manager`); the scheduler
already runs periodic work (`swarm_core.swarm_scheduler`, `AgentRuntime.add_periodic`).
This module is the thin missing piece:

- ``distill_skill_doc(name, description, steps)`` — render a skill markdown doc
  (``## Description / ## When to Use / ## Steps / ## Example``) from a trace.
- ``promote(trace, name=, interval_s=, ...)`` — write that doc under
  ``data_dir()/skills/`` and a routine spec under ``data_dir()/routines/``.
- ``load_routines()`` — read the specs back as ``swarm_scheduler.SwarmTask``s so a
  running scheduler picks them up (called from ``SwarmScheduler.__init__``).
- ``run_routine(spec)`` — replay a trace's steps against the ``apps/workspace``
  unix socket.

A "trace" is the list returned by ``apps/workspace`` ``GET /trace/<id>``:
``[{"action": "workspace.shell", "detail": {...}, "ts": ...}, ...]``.
"""
from __future__ import annotations

from .promote import (
    distill_skill_doc,
    load_routines,
    promote,
    routines_dir,
    run_routine,
    slugify,
)

__all__ = [
    "distill_skill_doc",
    "load_routines",
    "promote",
    "routines_dir",
    "run_routine",
    "slugify",
]
