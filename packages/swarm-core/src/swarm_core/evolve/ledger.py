"""The generation ledger — the part that makes the loop *recursive*.

Every attempt (kept or rejected) is appended here with what changed, what it
scored, and why the arena ruled the way it did. Generation N+1's proposer reads
this back as ``lessons()``, so the loop is not "an LLM rewrites a prompt N times"
but "an LLM rewrites a prompt knowing which of its own previous edits survived
contact with the benchmark".

Rejections are the valuable half and are never pruned preferentially — a ledger
of only successes teaches nothing about what not to try.
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterator

from .artifacts import evolve_dir

log = logging.getLogger("swarm_core.evolve.ledger")


def ledger_path() -> Path:
    return evolve_dir() / "generations.jsonl"


@dataclass
class Generation:
    """One champion-vs-challenger verdict."""

    artifact: str
    generation: int
    ts: float = field(default_factory=time.time)
    champion_score: float = 0.0
    challenger_score: float = 0.0
    promoted: bool = False
    verdict: str = ""               # human-readable reason from the arena
    rationale: str = ""             # what the proposer said it was trying to fix
    diff_summary: str = ""          # short description of the edit
    suite: str = ""
    rounds: int = 1
    failures: list[str] = field(default_factory=list)

    @property
    def delta(self) -> float:
        return self.challenger_score - self.champion_score


def record(gen: Generation) -> Generation:
    """Append one generation. Best-effort mirrored onto the tamper-evident audit
    chain — a self-modifying system that can quietly edit its own history of
    self-modifications is exactly the thing to avoid."""
    p = ledger_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(asdict(gen), ensure_ascii=False) + "\n")

    try:
        from swarm_core.security import audit

        audit.record(
            "evolve.generation",
            actor=gen.artifact,
            decision="allow" if gen.promoted else "deny",
            detail={
                "artifact": gen.artifact,
                "generation": gen.generation,
                "champion": round(gen.champion_score, 4),
                "challenger": round(gen.challenger_score, 4),
                "promoted": gen.promoted,
                "verdict": gen.verdict,
            },
        )
    except Exception as exc:  # noqa: BLE001 — audit must never break the loop
        log.debug("evolve ledger: audit mirror failed (%s)", exc)
    return gen


def read_all(artifact: str | None = None) -> Iterator[Generation]:
    p = ledger_path()
    if not p.exists():
        return iter(())

    def _gen() -> Iterator[Generation]:
        for line in p.read_text("utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if artifact and row.get("artifact") != artifact:
                continue
            known = {f for f in Generation.__dataclass_fields__}
            yield Generation(**{k: v for k, v in row.items() if k in known})

    return _gen()


def history(artifact: str, limit: int = 20) -> list[Generation]:
    rows = list(read_all(artifact))
    return rows[-limit:]


def lessons(artifact: str, limit: int = 8) -> str:
    """Render recent generations as proposer context.

    Kept deliberately terse: this goes into every proposal prompt, and the swarm's
    live TPM ceiling means a verbose lesson block crowds out the actual failures.
    """
    rows = history(artifact, limit)
    if not rows:
        return "(no previous generations — this is the first attempt)"
    lines = []
    for g in rows:
        mark = "KEPT" if g.promoted else "REJECTED"
        lines.append(
            f"- gen {g.generation} {mark} ({g.champion_score:.2f} -> {g.challenger_score:.2f}): "
            f"{g.diff_summary or g.rationale or g.verdict}"
        )
    return "\n".join(lines)


def stats(artifact: str) -> dict[str, Any]:
    rows = list(read_all(artifact))
    kept = [g for g in rows if g.promoted]
    return {
        "attempts": len(rows),
        "promoted": len(kept),
        "last_score": rows[-1].challenger_score if rows else 0.0,
        "best_score": max((g.challenger_score for g in rows), default=0.0),
        "current_generation": kept[-1].generation if kept else 0,
    }
