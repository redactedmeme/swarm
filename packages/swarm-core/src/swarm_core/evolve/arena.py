"""Champion vs challenger. The only code that may change what an agent reads.

Five gates stand between a generated candidate and the live artifact, in order:

1. the candidate is well-formed and not a no-op (``artifacts.write`` enforces);
2. the challenger beats the champion by ``EVOLVE_MIN_GAIN`` on the *mean* of
   ``rounds`` evaluations, not one lucky sample;
3. it introduced no new hard errors (a crash on a case the champion passed is
   disqualifying regardless of the aggregate);
4. the owning agent holds ``evolve.promote``;
5. ``EVOLVE_EXECUTE`` is true.

Fail any one and the generation is still written to the ledger — a rejection is
training data for the next proposer, not an event to discard.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any

from . import artifacts, ledger
from .bench import Suite, SuiteResult

log = logging.getLogger("swarm_core.evolve.arena")

#: How much better a challenger must be before it is worth the churn of a
#: promotion. Small positive by default — benchmark noise around zero would
#: otherwise let a coin-flip rewrite the prompt every tick.
MIN_GAIN = float(os.getenv("EVOLVE_MIN_GAIN", "0.02"))
ROUNDS = int(os.getenv("EVOLVE_ROUNDS", "2"))


def execute_enabled() -> bool:
    """Read at call time, never cached — the flag is meant to be flippable on a
    running box without a restart."""
    return os.getenv("EVOLVE_EXECUTE", "").strip().lower() in {"1", "true", "yes", "on"}


@dataclass
class Verdict:
    promoted: bool
    reason: str
    champion: SuiteResult
    challenger: SuiteResult
    record: dict[str, Any] | None = None

    @property
    def delta(self) -> float:
        return self.challenger.score - self.champion.score


def _new_errors(champion: SuiteResult, challenger: SuiteResult) -> list[str]:
    """Cases the champion handled without error that the challenger crashed on."""
    ok = {r.case_id for r in champion.results if r.error is None}
    return sorted(r.case_id for r in challenger.results
                  if r.error is not None and r.case_id in ok)


def compete(
    name: str,
    candidate: str,
    suite: Suite,
    *,
    rationale: str = "",
    diff_summary: str = "",
    rounds: int | None = None,
    min_gain: float | None = None,
    champion_result: SuiteResult | None = None,
) -> Verdict:
    """Evaluate ``candidate`` against the live body and promote it if it wins.

    ``champion_result`` reuses a measurement the caller already has. ``evolve_once``
    scores the live body to build the proposal prompt, and re-scoring it here would
    make every generation a third more expensive for no extra information.
    """
    art = artifacts.get(name)
    rounds = ROUNDS if rounds is None else rounds
    min_gain = MIN_GAIN if min_gain is None else min_gain

    champion = (champion_result if champion_result is not None
                else suite.evaluate_repeated(artifacts.body(name), rounds))
    challenger = suite.evaluate_repeated(candidate, rounds)

    gain = challenger.score - champion.score
    regressions = _new_errors(champion, challenger)

    if regressions:
        reason = f"new errors on {', '.join(regressions)} — disqualified regardless of score"
    elif gain < min_gain:
        reason = f"gain {gain:+.3f} below threshold {min_gain:.3f}"
    else:
        reason = f"gain {gain:+.3f} clears threshold {min_gain:.3f}"

    eligible = not regressions and gain >= min_gain
    promoted = False
    record = None

    if eligible:
        try:
            from swarm_core.security import authz

            authz.require(art.owner, "evolve.promote")
        except Exception as exc:  # noqa: BLE001 — Denied or a missing authz module
            reason = f"{reason}, but promotion denied: {exc}"
            eligible = False

    if eligible and not execute_enabled():
        reason = f"{reason}, held — EVOLVE_EXECUTE is off (proposal recorded, not applied)"
    elif eligible:
        try:
            record = artifacts.write(name, candidate, origin="evolve")
            promoted = True
        except artifacts.ArtifactError as exc:
            reason = f"{reason}, but the write was refused: {exc}"

    gen = ledger.record(ledger.Generation(
        artifact=name,
        generation=artifacts.generation(name),
        champion_score=champion.score,
        challenger_score=challenger.score,
        promoted=promoted,
        verdict=reason,
        rationale=rationale,
        diff_summary=diff_summary,
        suite=suite.name,
        rounds=max(1, rounds),
        failures=[r.case_id for r in challenger.failures[:5] if r.score < 1.0],
    ))
    log.info("evolve/%s: %s (gen %d, %s)", name, reason, gen.generation,
             "promoted" if promoted else "held")

    return Verdict(promoted=promoted, reason=reason, champion=champion,
                   challenger=challenger, record=record)
