"""One generation of self-improvement, and the scheduler task that repeats it.

``evolve_once`` is measure -> propose -> compete -> record. Everything else in
this module is about making that safe to run unattended:

- one candidate per tick, never a burst — a tick that regresses costs one tick;
- a cooldown so a scheduled artifact cannot be rewritten faster than the
  operator can read the ledger;
- a saturation check, because a benchmark a body already aces has nothing left
  to teach and every further generation is drift dressed as progress.
"""
from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from typing import Any

from . import arena, artifacts, ledger
from .propose import propose as _propose
from .bench import Suite

log = logging.getLogger("swarm_core.evolve")

#: A body scoring at or above this has nothing the suite can still measure.
SATURATED = float(os.getenv("EVOLVE_SATURATED_AT", "0.99"))
#: Minimum seconds between generations for one artifact.
COOLDOWN_S = int(os.getenv("EVOLVE_COOLDOWN_S", "3600"))


@dataclass
class Outcome:
    artifact: str
    ran: bool
    promoted: bool
    reason: str
    score: float = 0.0
    delta: float = 0.0
    rationale: str = ""


def _last_attempt_ts(name: str) -> float:
    rows = ledger.history(name, limit=1)
    return rows[-1].ts if rows else 0.0


def cooldown_remaining(name: str, cooldown_s: int | None = None) -> float:
    cd = COOLDOWN_S if cooldown_s is None else cooldown_s
    if cd <= 0:
        return 0.0
    return max(0.0, cd - (time.time() - _last_attempt_ts(name)))


def evolve_once(
    name: str,
    suite: Suite,
    *,
    propose_fn: Any = None,
    cooldown_s: int | None = None,
    extra_context: str = "",
    rounds: int | None = None,
) -> Outcome:
    """Run exactly one generation for one artifact.

    Never raises: a proposer outage, a dead provider or a malformed reply must
    leave the champion in place and the scheduler running.
    """
    try:
        artifacts.get(name)
    except artifacts.ArtifactError as exc:
        return Outcome(name, ran=False, promoted=False, reason=str(exc))

    wait = cooldown_remaining(name, cooldown_s)
    if wait > 0:
        return Outcome(name, ran=False, promoted=False,
                       reason=f"cooldown — {int(wait)}s to the next generation")

    try:
        baseline = suite.evaluate_repeated(artifacts.body(name),
                                           arena.ROUNDS if rounds is None else rounds)
    except Exception as exc:  # noqa: BLE001
        log.warning("evolve/%s: baseline evaluation failed (%s)", name, exc)
        return Outcome(name, ran=False, promoted=False, reason=f"baseline failed: {exc}")

    if baseline.score >= SATURATED:
        return Outcome(name, ran=False, promoted=False, score=baseline.score,
                       reason=f"benchmark saturated at {baseline.score:.3f} — add harder cases")

    try:
        candidate, rationale = _propose(
            name, baseline, propose_fn=propose_fn, extra_context=extra_context)
    except Exception as exc:  # noqa: BLE001
        log.warning("evolve/%s: proposer failed (%s)", name, exc)
        return Outcome(name, ran=False, promoted=False, reason=f"proposer failed: {exc}",
                       score=baseline.score)

    if candidate.strip() == artifacts.body(name).strip():
        return Outcome(name, ran=False, promoted=False, score=baseline.score,
                       rationale=rationale, reason="proposer returned the current body unchanged")

    verdict = arena.compete(name, candidate, suite, rationale=rationale,
                            diff_summary=rationale, rounds=rounds,
                            champion_result=baseline)
    return Outcome(
        artifact=name,
        ran=True,
        promoted=verdict.promoted,
        reason=verdict.reason,
        score=verdict.challenger.score,
        delta=verdict.delta,
        rationale=rationale,
    )


def scheduled_task(
    name: str,
    suite: Suite,
    *,
    interval_s: int | None = None,
    propose_fn: Any = None,
    priority: int = 4,
):
    """Wrap ``evolve_once`` as a :class:`swarm_scheduler.SwarmTask`.

    Priority defaults to 4 (standard), so self-improvement is the first thing the
    scheduler sheds when the kernel drops out of HEALTHY. An agent that is
    struggling should be serving traffic, not rewriting its own prompt.
    """
    from swarm_core.swarm_scheduler import SwarmTask

    interval = interval_s if interval_s is not None else max(COOLDOWN_S, 600)

    async def _run():
        outcome = evolve_once(name, suite, propose_fn=propose_fn)
        log.info("evolve/%s: %s", name, outcome.reason)
        return outcome

    return SwarmTask(
        id=f"evolve_{artifacts.get(name).slug}",
        name=f"evolve:{name}",
        coro_factory=_run,
        interval_s=interval,
        priority=priority,
        tags=["evolve", "self-improvement"],
    )
