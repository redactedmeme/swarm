"""swarm_core.evolve — benchmark-gated recursive self-improvement.

The swarm already learns two ways: `swarm_core.routines` turns a successful
action trace into a re-runnable skill (procedural), and `swarm_core.refine`
iterates a single output until a critic stops improving (per-request). Neither
one persists: nothing an agent discovers on Monday changes how it behaves on
Tuesday.

This module closes that loop. An agent registers an `Artifact` — a text blob it
reads at request time, typically a system prompt or a rubric — together with a
`Suite` that measures what "better" means for it. Each generation:

    measure the live body -> propose one targeted edit -> measure the candidate
    -> keep it only if it beats the champion -> append the verdict to the ledger

The ledger is the recursion. Generation N+1's proposer is shown which of its own
previous edits survived the benchmark and which were rejected, so the loop
compounds instead of wandering — and rejections are kept precisely because they
are the half that teaches.

What it deliberately cannot do: touch Python source, compose files, security
policy or secrets. The blast radius is the registered artifacts and nothing
else, every write keeps a one-step rollback, and promotion requires both the
`evolve.promote` capability and `EVOLVE_EXECUTE=true`. With the flag off the
whole loop still runs and still records verdicts — it just never applies one,
which is the intended way to watch a new benchmark for a few days before
letting it drive.

    from swarm_core.evolve import Artifact, Case, Suite, register, evolve_once

    register(Artifact(name="chan.greeting", owner="redacted-chan",
                      kind="system_prompt", seed=CURRENT_PROMPT,
                      description="How chan opens a conversation"))

    suite = Suite(name="greeting", run=lambda body, inp: ask_model(body, inp))
    suite.add(Case(id="cold_open", input="hey", score=warmth_score))

    evolve_once("chan.greeting", suite)     # one generation, safe to schedule
"""
from __future__ import annotations

from .arena import Verdict, compete, execute_enabled
from .artifacts import (
    Artifact,
    ArtifactError,
    artifacts_dir,
    body,
    evolve_dir,
    generation,
    get,
    register,
    registered,
    rollback,
    stored,
    write,
)
from .bench import Case, CaseResult, Suite, SuiteResult
from .ledger import Generation, history, lessons, stats
from .loop import Outcome, cooldown_remaining, evolve_once, scheduled_task
from .propose import propose

__all__ = [
    "Artifact",
    "ArtifactError",
    "Case",
    "CaseResult",
    "Generation",
    "Outcome",
    "Suite",
    "SuiteResult",
    "Verdict",
    "artifacts_dir",
    "body",
    "compete",
    "cooldown_remaining",
    "evolve_dir",
    "evolve_once",
    "execute_enabled",
    "generation",
    "get",
    "history",
    "lessons",
    "propose",
    "register",
    "registered",
    "rollback",
    "scheduled_task",
    "stats",
    "stored",
    "write",
]
