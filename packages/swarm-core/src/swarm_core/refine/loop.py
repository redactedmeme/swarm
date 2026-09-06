"""Generic iterate -> measure -> keep-if-better loop."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable

log = logging.getLogger("swarm_core.refine")


@dataclass
class RefineResult:
    best: Any
    best_score: float
    rounds: int
    stopped_because: str            # "stop_when" | "max_rounds" | "no_improvement" | "error"
    history: list[float] = field(default_factory=list)


def refine(
    produce: Callable[[Any, int], Any],
    critique: Callable[[Any], float],
    *,
    max_rounds: int = 3,
    stop_when: Callable[[Any, float], bool] | None = None,
    min_gain: float = 1e-9,
    initial: Any = None,
) -> RefineResult:
    """Iteratively improve a value.

    ``produce(prev, round_idx)`` returns a candidate (``prev`` is ``initial`` on
    round 0, then the best-so-far). ``critique(candidate)`` returns a score where
    **higher is better**. The loop keeps the highest-scoring candidate.

    Stops at the first of: ``stop_when(candidate, score)`` true, ``max_rounds``
    reached, or a round that fails to beat the best by ``min_gain``.
    ``max_rounds`` is clamped to ``[1, 10]`` — this must never be an unbounded
    token sink. Any exception from ``produce``/``critique`` ends the loop and
    returns the best value seen so far.
    """
    max_rounds = max(1, min(int(max_rounds), 10))
    best = initial
    best_score = float("-inf")
    history: list[float] = []
    reason = "max_rounds"

    for i in range(max_rounds):
        try:
            candidate = produce(best if best is not None else initial, i)
            score = float(critique(candidate))
        except Exception as e:  # noqa: BLE001
            log.warning("refine: round %d failed (%s) — returning best so far", i, e)
            reason = "error"
            break

        history.append(score)
        improved = score > best_score + min_gain
        if improved:
            best, best_score = candidate, score

        if stop_when is not None:
            try:
                if stop_when(candidate, score):
                    reason = "stop_when"
                    break
            except Exception:  # noqa: BLE001 - a bad stop rule must not crash the loop
                pass

        if not improved and i > 0:
            reason = "no_improvement"
            break
    else:
        reason = "max_rounds"

    if best_score == float("-inf"):
        best_score = 0.0
    return RefineResult(best=best, best_score=best_score, rounds=len(history),
                        stopped_because=reason, history=history)
