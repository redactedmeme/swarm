"""swarm_core.web — shared web primitives.

- ``ssrf.is_blocked(url)`` — the single copy of the SSRF host guard that used to
  live only in ``apps/hermes/plugins/swarm-manager/web_tools.py``.
- ``extract.extract(html, url)`` — readable-content extraction (trafilatura when
  available, regex tag-strip fallback otherwise).

Neither module replaces ``swarm_core.security.promptguard`` — extracted text is
still untrusted and must be fenced with ``wrap_untrusted`` before it reaches a
prompt.
"""
from __future__ import annotations

from .extract import extract
from .ssrf import is_blocked

__all__ = ["extract", "is_blocked"]
