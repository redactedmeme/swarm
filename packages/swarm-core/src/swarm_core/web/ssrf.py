"""SSRF host guard — one copy, lifted from the Hermes web plugin.

``is_blocked(url)`` returns True when a URL must not be fetched: non-http(s)
schemes, localhost / loopback, RFC1918 ranges (including the full 172.16/12
block), link-local, ``.internal`` names and cloud metadata endpoints.

This is a cheap string-level guard. It is deliberately conservative — callers
that need DNS-resolution-time checks should layer them on top, not replace this.
"""
from __future__ import annotations

import re
from urllib.parse import urlparse

_BLOCKED_HOST_SUBSTRINGS = (
    "localhost",
    "127.",
    "0.0.0.0",
    "10.",
    "192.168.",
    "169.254.",       # link-local / cloud metadata
    ".internal",
    "metadata.",
)

# 172.16.0.0/12 -> 172.16.x.x through 172.31.x.x
_BLOCKED_172_RE = re.compile(r"^172\.(1[6-9]|2\d|3[01])\.")


def is_blocked(url: str) -> bool:
    """Return True if the URL should be blocked for SSRF protection."""
    if not isinstance(url, str):
        return True
    lower = url.strip().lower()
    if not (lower.startswith("http://") or lower.startswith("https://")):
        return True

    host = urlparse(lower).hostname or ""
    if not host:
        return True

    for frag in _BLOCKED_HOST_SUBSTRINGS:
        # substrings anchored where it matters: exact-ish for the numeric/prefix
        # forms, contains for the name forms.
        if frag.startswith(".") or frag.endswith("."):
            if frag in host:
                return True
        elif host == frag.rstrip(".") or host.startswith(frag):
            return True

    if _BLOCKED_172_RE.match(host):
        return True

    return False


# Back-compat alias for the old private name in web_tools.py
_is_ssrf_blocked = is_blocked
