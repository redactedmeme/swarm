"""The registry of things the swarm is allowed to rewrite about itself.

Recursive self-improvement is only as safe as its blast radius. Nothing here can
touch Python source, compose files, policy YAML or secrets: an artifact is a
**text blob with a fitness function**, stored under ``data_dir()/evolve/artifacts/``
and read by the running agent at request time. If an agent wants to be improved,
it registers the artifact it reads from and a benchmark that says what "better"
means — there is no other entry point.

Every write keeps the previous body, so ``rollback()`` is always one call away
and a bad generation costs one scheduler tick.
"""
from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from swarm_core.paths import data_dir

#: A generated artifact body larger than this is rejected outright — a proposer
#: that has started pasting its own reasoning into the prompt is not improving it.
MAX_BODY_BYTES = int(os.getenv("EVOLVE_MAX_BODY_BYTES", "16384"))

_SLUG = re.compile(r"[^a-z0-9_.-]+")


class ArtifactError(RuntimeError):
    """Raised for an unregistered name, an oversized body, or a bad rollback."""


def evolve_dir() -> Path:
    d = data_dir() / "evolve"
    d.mkdir(parents=True, exist_ok=True)
    return d


def artifacts_dir() -> Path:
    d = evolve_dir() / "artifacts"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _slug(name: str) -> str:
    s = _SLUG.sub("_", (name or "").strip().lower()).strip("_")
    if not s:
        raise ArtifactError("artifact name is empty")
    return s


@dataclass
class Artifact:
    """One mutable, benchmarked text blob owned by one agent.

    ``kind`` is advisory metadata for the proposer ("system_prompt", "routine_params",
    "committee_rubric", …) — it shapes the instructions the proposer is given but
    grants no extra reach. ``owner`` is the agent name checked against the
    ``evolve.promote`` grant before anything is written.
    """

    name: str
    owner: str
    kind: str = "system_prompt"
    description: str = ""
    seed: str = ""
    notes: list[str] = field(default_factory=list)

    @property
    def slug(self) -> str:
        return _slug(self.name)

    def path(self) -> Path:
        return artifacts_dir() / f"{self.slug}.json"


_REGISTRY: dict[str, Artifact] = {}


def register(artifact: Artifact) -> Artifact:
    """Make an artifact eligible for evolution. Idempotent; re-registering
    updates the metadata but never the stored body."""
    _REGISTRY[artifact.slug] = artifact
    p = artifact.path()
    if not p.exists():
        _write_record(artifact.slug, {
            "name": artifact.name,
            "owner": artifact.owner,
            "kind": artifact.kind,
            "body": artifact.seed,
            "generation": 0,
            "previous": None,
            "updated": time.time(),
            "origin": "seed",
        })
    return artifact


def registered() -> dict[str, Artifact]:
    return dict(_REGISTRY)


def get(name: str) -> Artifact:
    """Resolve a registered artifact, falling back to one stored on disk.

    A record written by a previous process *is* a registration — without this
    fallback the CLI could never inspect or roll back an artifact that only the
    agent's own process registers.
    """
    slug = _slug(name)
    a = _REGISTRY.get(slug)
    if a is not None:
        return a
    try:
        rec = _read_record(slug)
    except (ArtifactError, json.JSONDecodeError):
        raise ArtifactError(
            f"artifact {name!r} is not registered — register() it with a benchmark first"
        ) from None
    return Artifact(name=rec.get("name", name), owner=rec.get("owner", ""),
                    kind=rec.get("kind", "system_prompt"), seed=rec.get("body", ""))


def stored() -> list[dict[str, Any]]:
    """Every artifact record on disk, registered in this process or not."""
    out = []
    for p in sorted(artifacts_dir().glob("*.json")):
        try:
            rec = json.loads(p.read_text("utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        rec.pop("previous", None)          # bodies are large; the summary is the point
        out.append(rec)
    return out


def _write_record(slug: str, record: dict[str, Any]) -> None:
    p = artifacts_dir() / f"{slug}.json"
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(record, indent=2, ensure_ascii=False), "utf-8")
    tmp.replace(p)


def _read_record(slug: str) -> dict[str, Any]:
    p = artifacts_dir() / f"{slug}.json"
    if not p.exists():
        raise ArtifactError(f"artifact {slug!r} has no stored record")
    return json.loads(p.read_text("utf-8"))


def body(name: str) -> str:
    """The live body an agent should read at request time. Falls back to the
    registered seed if the store was wiped, so a missing volume degrades to the
    hand-written default rather than to an empty prompt."""
    art = get(name)
    try:
        return _read_record(art.slug).get("body", art.seed) or art.seed
    except ArtifactError:
        return art.seed


def generation(name: str) -> int:
    try:
        return int(_read_record(get(name).slug).get("generation", 0))
    except ArtifactError:
        return 0


def write(name: str, new_body: str, *, origin: str = "evolve") -> dict[str, Any]:
    """Replace the body, keeping exactly one previous version for rollback.

    Callers must have already passed the authz + arena gates — this is the
    mechanical write, not the decision.
    """
    art = get(name)
    new_body = (new_body or "").strip()
    if not new_body:
        raise ArtifactError(f"{art.name}: refusing to write an empty body")
    if len(new_body.encode("utf-8")) > MAX_BODY_BYTES:
        raise ArtifactError(
            f"{art.name}: body is {len(new_body.encode('utf-8'))} bytes, cap is {MAX_BODY_BYTES}"
        )
    cur = _read_record(art.slug)
    if new_body == cur.get("body", ""):
        raise ArtifactError(f"{art.name}: candidate is identical to the current body")

    record = {
        "name": art.name,
        "owner": art.owner,
        "kind": art.kind,
        "body": new_body,
        "generation": int(cur.get("generation", 0)) + 1,
        "previous": cur.get("body", ""),
        "previous_generation": int(cur.get("generation", 0)),
        "updated": time.time(),
        "origin": origin,
    }
    _write_record(art.slug, record)
    return record


def rollback(name: str) -> dict[str, Any]:
    """Restore the single retained previous body. Rolling back twice in a row is
    an error rather than a no-op, so a panicking operator gets told the truth."""
    art = get(name)
    cur = _read_record(art.slug)
    prev = cur.get("previous")
    if not prev:
        raise ArtifactError(f"{art.name}: nothing to roll back to")
    record = {
        "name": art.name,
        "owner": art.owner,
        "kind": art.kind,
        "body": prev,
        "generation": int(cur.get("generation", 0)) + 1,
        "previous": None,
        "previous_generation": int(cur.get("generation", 0)),
        "updated": time.time(),
        "origin": f"rollback_of_gen_{cur.get('generation', 0)}",
    }
    _write_record(art.slug, record)
    return record
