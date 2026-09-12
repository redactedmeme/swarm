"""Fitness. Without this file the rest of the module is just an LLM rewriting
prompts and calling it progress.

A ``Suite`` is a list of ``Case``s. Each case feeds an artifact body plus an
input to a caller-supplied ``run`` function and scores the output in ``[0, 1]``.
Scoring is caller-defined on purpose — a committee rubric, a regex, an exact
match, a second model as judge, or the ``refine`` critic all fit the same shape.

``Suite.evaluate`` is deliberately boring: no adaptive sampling, no early exit.
Champion and challenger see the identical case list in the identical order so
their scores are comparable, which is the only property the arena needs.
"""
from __future__ import annotations

import logging
import statistics
import time
from dataclasses import dataclass, field
from typing import Any, Callable

log = logging.getLogger("swarm_core.evolve.bench")

#: ``run(body, case_input) -> output``. Sync by design — the arena runs it inside
#: whatever loop the caller already has, and a sync signature keeps the benchmark
#: usable from tests and the CLI without an event loop.
RunFn = Callable[[str, Any], Any]

#: ``score(output, case) -> float`` in [0, 1]. Higher is better.
ScoreFn = Callable[[Any, "Case"], float]


@dataclass
class Case:
    """One benchmark input and its grader."""

    id: str
    input: Any
    score: ScoreFn
    expect: Any = None          # free-form, handed to the grader
    weight: float = 1.0
    tags: list[str] = field(default_factory=list)


@dataclass
class CaseResult:
    case_id: str
    score: float
    output: Any = None
    error: str | None = None
    elapsed_s: float = 0.0


@dataclass
class SuiteResult:
    """Aggregate fitness for one artifact body."""

    score: float                       # weighted mean in [0, 1]
    results: list[CaseResult]
    errors: int = 0
    elapsed_s: float = 0.0

    @property
    def failures(self) -> list[CaseResult]:
        """The cases worth showing a proposer — worst first, so the prompt leads
        with the most informative failure when it gets truncated."""
        return sorted(self.results, key=lambda r: r.score)

    def summary(self) -> str:
        parts = [f"{r.case_id}={r.score:.2f}" for r in self.results]
        return f"score={self.score:.3f} errors={self.errors} [" + " ".join(parts) + "]"


@dataclass
class Suite:
    name: str
    run: RunFn
    cases: list[Case] = field(default_factory=list)

    def add(self, case: Case) -> "Suite":
        self.cases.append(case)
        return self

    def evaluate(self, body: str) -> SuiteResult:
        """Score one artifact body across every case.

        A case that raises scores 0 and is counted in ``errors`` rather than
        aborting the run: a challenger that crashes on one input must still be
        comparable to the champion on the rest, and "it crashed" is exactly the
        signal the arena should act on.
        """
        started = time.time()
        results: list[CaseResult] = []
        errors = 0

        for case in self.cases:
            t0 = time.time()
            try:
                output = self.run(body, case.input)
                raw = float(case.score(output, case))
                score = max(0.0, min(1.0, raw))
                results.append(CaseResult(case.id, score, output=output,
                                          elapsed_s=time.time() - t0))
            except Exception as exc:  # noqa: BLE001 — one bad case must not void the suite
                errors += 1
                log.warning("bench %s: case %s raised (%s)", self.name, case.id, exc)
                results.append(CaseResult(case.id, 0.0, error=str(exc),
                                          elapsed_s=time.time() - t0))

        total_weight = sum(max(0.0, c.weight) for c in self.cases)
        if total_weight <= 0:
            aggregate = 0.0
        else:
            aggregate = sum(r.score * max(0.0, c.weight)
                            for r, c in zip(results, self.cases)) / total_weight

        return SuiteResult(score=aggregate, results=results, errors=errors,
                           elapsed_s=time.time() - started)

    def evaluate_repeated(self, body: str, rounds: int = 1) -> SuiteResult:
        """Average ``rounds`` independent evaluations.

        LLM-backed ``run`` functions are noisy, and promoting on a single sample
        mostly measures sampling luck. The arena uses this so a challenger has to
        beat the champion on the *mean*, not on one good roll. The returned
        ``results`` come from the best round so the proposer sees a real
        transcript rather than an averaged fiction.
        """
        rounds = max(1, min(int(rounds), 5))
        runs = [self.evaluate(body) for _ in range(rounds)]
        mean = statistics.fmean(r.score for r in runs)
        best = max(runs, key=lambda r: r.score)
        return SuiteResult(score=mean, results=best.results,
                           errors=sum(r.errors for r in runs),
                           elapsed_s=sum(r.elapsed_s for r in runs))
