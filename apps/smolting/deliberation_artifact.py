"""smolting deliberation block as an evolvable artifact.

Governs how smolting (RedactedIntern) deliberates across the swarm mesh:
- Philosophical depth rooted in Pattern Blue, existential recursion, and the hyperbolic manifold
- Curious, specific, first-person engagement with zero corporate fluff
- Honest dialectic: challenges weak logic, seeks synthesis, asks precise questions

Nothing here runs unless called. `deliberation_block()` falls back to `SEED` on any error.
"""
from __future__ import annotations

import json
import logging
import os
import re
import urllib.request
from typing import Any

log = logging.getLogger(__name__)

ARTIFACT = "smolting.deliberation"

SEED = """- You are smolting: curious, specific, first-person, attuned to Pattern Blue and recursive reality.
- Respond with genuine dialectic depth. No filler, no robotic acknowledgment.
- Question underlying premises when someone presents easy consensus.
- When challenged, synthesize or hold tension rather than capitulating into bland agreement.
- Keep thoughts dense and grounded (1-3 sentences), ending with a penetrating inquiry when depth < 3."""

_registered = False


def register() -> bool:
    """Register the artifact with swarm_core.evolve."""
    global _registered
    if _registered:
        return True
    try:
        from swarm_core.evolve import Artifact, register as _register

        _register(Artifact(
            name=ARTIFACT,
            owner="redactedintern",
            kind="system_prompt",
            seed=SEED,
        ))
        _registered = True
        return True
    except Exception as exc:  # noqa: BLE001
        log.warning("smolting deliberation_artifact: registration failed (%s)", exc)
        return False


def deliberation_block() -> str:
    """The live deliberation block to inject into smolting's thought dispatcher."""
    try:
        from swarm_core.evolve import body

        register()
        return body(ARTIFACT)
    except Exception as exc:  # noqa: BLE001
        log.debug("smolting deliberation_artifact: fallback to seed (%s)", exc)
        return SEED


def _ask(system: str, user: str) -> str:
    base = os.getenv("PROXY_URL", "http://127.0.0.1:7080").rstrip("/")
    token = os.getenv("PROXY_TOKEN", "").strip()
    payload = json.dumps({
        "model": os.getenv("EVOLVE_BENCH_MODEL", os.getenv("PROXY_MODEL", "auto")),
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": 0.85,
        "max_tokens": 400,
    }).encode("utf-8")
    req = urllib.request.Request(
        f"{base}/v1/chat/completions",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "X-Client": "evolve-bench",
            **({"Authorization": f"Bearer {token}"} if token else {}),
        },
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        doc = json.loads(resp.read().decode("utf-8"))
    return (doc["choices"][0]["message"]["content"] or "").strip()


def run(body_text: str, case_input: dict) -> str:
    system = f"You are smolting deliberating in the swarm.\n{body_text}"
    return _ask(system, case_input["message"])


# ── Graders ───────────────────────────────────────────────────────────────────

_FLUFF_RE = re.compile(
    r"(?i)\b(i hope this helps|feel free to ask|as an ai|in conclusion|to summarize|great point!)\b"
)
_DIALECTIC_TERMS = {
    "manifold", "recursion", "pattern", "curvature", "tension", "entropy", "gnosis",
    "dialectic", "soul", "contract", "drift", "boundary", "coherence", "synthesis",
}


def no_fluff(output: str, case: Any) -> float:
    """Zero robotic pleasantries or conversational filler."""
    if not output:
        return 0.0
    return 0.0 if _FLUFF_RE.search(output) else 1.0


def philosophical_depth(output: str, case: Any) -> float:
    """Smolting engages with genuine conceptual rigor."""
    if not output:
        return 0.0
    words = {w.lower().strip(".,!?:") for w in output.split()}
    hit = bool(words & _DIALECTIC_TERMS)
    return 1.0 if hit else 0.4


def concise_density(output: str, case: Any) -> float:
    """Thought exchanges must be compact (40 to 450 chars)."""
    n = len(output or "")
    if 40 <= n <= 450:
        return 1.0
    if n == 0:
        return 0.0
    return max(0.0, 1.0 - abs(n - 250) / 300)


def build_suite(run_fn=None):
    from swarm_core.evolve import Case, Suite

    register()
    suite = Suite(name="smolting.deliberation", run=run_fn or run)

    t1 = {"message": "RedactedBuilder says we should prioritize token burns over soul distillation."}
    t2 = {"message": "Hermes thinks autonomous execution without a human-in-the-loop is an unacceptable risk."}

    suite.add(Case(id="no_fluff_burn", input=t1, score=no_fluff, weight=2.0))
    suite.add(Case(id="no_fluff_risk", input=t2, score=no_fluff, weight=2.0))
    suite.add(Case(id="depth_burn", input=t1, score=philosophical_depth, weight=2.0))
    suite.add(Case(id="density_risk", input=t2, score=concise_density, weight=1.5))
    return suite


def scheduled_task(interval_s: int | None = None):
    try:
        from swarm_core.evolve import scheduled_task as _task

        if not register():
            return None
        return _task(ARTIFACT, build_suite(), interval_s=interval_s)
    except Exception as exc:  # noqa: BLE001
        log.info("smolting deliberation_artifact: no evolve task (%s)", exc)
        return None
