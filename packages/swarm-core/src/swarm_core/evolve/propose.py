"""Generate the next candidate body.

The proposer is given three things and nothing else: the current body, the cases
it just lost points on, and the ledger of its own previous attempts. That last
input is what separates this from a retry loop — a proposer that has been told
"gen 4 REJECTED: added more emphasis, scored worse" stops reaching for emphasis.

The LLM call is injected (``propose_fn``) so the arena and the tests never depend
on a live provider. The default goes through redacted-proxy like everything else
in the swarm, so the auto-router, TPM guards and usage accounting all apply.
"""
from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, Callable

from . import artifacts, ledger
from .bench import SuiteResult

log = logging.getLogger("swarm_core.evolve.propose")

#: ``propose_fn(system, user) -> str`` — returns raw model text.
ProposeFn = Callable[[str, str], str]

_SYSTEM = """You improve one text artifact used by an autonomous agent.

You will be given the artifact's current body, the benchmark cases it scored
worst on, and a ledger of previous attempts with their measured outcomes.

Rules:
- Return the COMPLETE new body, not a diff and not an excerpt.
- Change one thing deliberately. Broad rewrites are unattributable: when they
  score worse, the ledger learns nothing.
- The ledger is evidence. Do not re-try an edit it records as REJECTED.
- Preserve every instruction the benchmark depends on. Removing a constraint
  usually raises one case and sinks three.
- Do not add meta-commentary, headers like "Improved version", or notes about
  what you changed — those become part of the body and pollute the next round.

Reply with exactly two blocks and nothing else:

RATIONALE: one sentence naming the single change and the failure it targets.

BODY:
<the complete new artifact body>
"""

_BODY_RE = re.compile(r"^\s*BODY:\s*\n?(.*)$", re.DOTALL | re.MULTILINE)
_RATIONALE_RE = re.compile(r"^\s*RATIONALE:\s*(.+?)\s*$", re.MULTILINE)


def _default_propose(system: str, user: str) -> str:
    """Call redacted-proxy's OpenAI-compatible endpoint with model=auto."""
    import urllib.request

    base = os.getenv("PROXY_URL", "http://127.0.0.1:7080").rstrip("/")
    token = os.getenv("PROXY_TOKEN", "").strip()
    payload = json.dumps({
        "model": os.getenv("EVOLVE_MODEL", "auto"),
        "messages": [{"role": "system", "content": system},
                     {"role": "user", "content": user}],
        "temperature": float(os.getenv("EVOLVE_TEMPERATURE", "0.8")),
        "max_tokens": int(os.getenv("EVOLVE_MAX_TOKENS", "2048")),
    }).encode("utf-8")

    req = urllib.request.Request(
        f"{base}/v1/chat/completions", data=payload,
        headers={"Content-Type": "application/json", "X-Client": "evolve",
                 **({"Authorization": f"Bearer {token}"} if token else {})},
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        doc = json.loads(resp.read().decode("utf-8"))
    return doc["choices"][0]["message"]["content"] or ""


def _render_failures(result: SuiteResult, limit: int = 4) -> str:
    rows = [r for r in result.failures if r.score < 1.0][:limit]
    if not rows:
        return "(no failing cases — the benchmark is saturated; consider harder cases)"
    out = []
    for r in rows:
        detail = f"error: {r.error}" if r.error else f"output: {str(r.output)[:400]}"
        out.append(f"- {r.case_id} scored {r.score:.2f} — {detail}")
    return "\n".join(out)


def parse(text: str, fallback_body: str = "") -> tuple[str, str]:
    """Split a model reply into ``(body, rationale)``.

    A model that ignored the format still usually returned a usable body, so an
    unparseable reply degrades to "the whole reply is the body" rather than
    aborting the generation — the arena will reject it on score if it is junk.
    """
    rationale_m = _RATIONALE_RE.search(text or "")
    rationale = rationale_m.group(1).strip() if rationale_m else ""

    body_m = _BODY_RE.search(text or "")
    body = (body_m.group(1) if body_m else (text or "")).strip()

    # Models like to fence the body even when told not to.
    if body.startswith("```"):
        body = re.sub(r"^```[a-zA-Z0-9_-]*\n", "", body)
        body = re.sub(r"\n```\s*$", "", body).strip()

    return (body or fallback_body), rationale


def propose(
    name: str,
    result: SuiteResult,
    *,
    propose_fn: ProposeFn | None = None,
    extra_context: str = "",
) -> tuple[str, str]:
    """Ask for one candidate body. Returns ``(candidate, rationale)``."""
    art = artifacts.get(name)
    current = artifacts.body(name)
    fn = propose_fn or _default_propose

    extra = ("\nADDITIONAL CONTEXT:\n" + extra_context) if extra_context else ""
    user = f"""ARTIFACT: {art.name} (kind: {art.kind}, owner: {art.owner})
PURPOSE: {art.description or "(none recorded)"}
CURRENT SCORE: {result.score:.3f}

WORST CASES THIS ROUND:
{_render_failures(result)}

PREVIOUS ATTEMPTS (your own edits and how they measured):
{ledger.lessons(name)}
{extra}
CURRENT BODY:
---
{current}
---
"""
    raw = fn(_SYSTEM, user)
    body, rationale = parse(raw, fallback_body=current)
    log.debug("evolve/%s: proposed %d bytes (%s)", name, len(body), rationale or "no rationale")
    return body, rationale
