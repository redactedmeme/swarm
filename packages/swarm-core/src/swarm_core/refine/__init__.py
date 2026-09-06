"""swarm_core.refine — an iterate-until-better primitive and a cosmetic humanizer.

- ``loop.refine(produce, critique, *, max_rounds=3, stop_when)`` — generic
  iterate -> measure -> keep-if-better, with an explicit stop rule and a hard
  round cap so it can never become an unbounded token sink. It takes *callables*
  (``produce`` / ``critique``); any model calls belong inside those and must go
  through the redacted-proxy auto-router (``model="auto"``), never a provider.
- ``humanize.humanize(text, *, voice)`` — strip the well-known AI tells while
  asserting the facts are unchanged. **Returns the original on any failure** — a
  cosmetic pass must never drop or mangle a message.
- ``humanize.maybe_humanize(text, *, voice)`` — env-gated wrapper
  (``SWARM_HUMANIZE``, default off) that also runs ``leakscan`` on the rewrite.
"""
from __future__ import annotations

from .humanize import humanize, maybe_humanize
from .loop import RefineResult, refine

__all__ = ["refine", "RefineResult", "humanize", "maybe_humanize"]
