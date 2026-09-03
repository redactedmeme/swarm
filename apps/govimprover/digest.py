"""Read-only fetch of the character's governance knowledge sources into a short
cached digest. Best-effort: network failures just shrink the digest.
"""
from __future__ import annotations

import logging
import re
import time

import aiohttp

logger = logging.getLogger(__name__)

_CACHE = {"ts": 0.0, "text": ""}
_TTL = 1800  # 30 min
_MAX_PER_SOURCE = 1200
_TAG_RE = re.compile(r"<[^>]+>")


def _extract_urls(sources: list) -> list[str]:
    urls = []
    for s in sources:
        m = re.search(r"https?://[^\s\)]+", str(s))
        if m:
            urls.append(m.group(0).rstrip(".,"))
    # de-dup, keep order, cap
    seen, out = set(), []
    for u in urls:
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out[:6]


async def _fetch(session: aiohttp.ClientSession, url: str) -> str:
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=8)) as r:
            if r.status != 200:
                return ""
            body = await r.text()
    except Exception as e:  # noqa: BLE001
        logger.debug("[digest] %s -> %s", url, e)
        return ""
    text = _TAG_RE.sub(" ", body)
    text = re.sub(r"\s+", " ", text).strip()
    return f"[{url}] {text[:_MAX_PER_SOURCE]}"


async def refresh(sources: list) -> str:
    now = time.time()
    if now - _CACHE["ts"] < _TTL and _CACHE["text"]:
        return _CACHE["text"]
    urls = _extract_urls(sources)
    if not urls:
        return _CACHE["text"]
    async with aiohttp.ClientSession(headers={"User-Agent": "redacted-govimprover/1.0"}) as s:
        chunks = []
        for u in urls:
            c = await _fetch(s, u)
            if c:
                chunks.append(c)
    if chunks:
        _CACHE["text"] = "\n\n".join(chunks)[:6000]
        _CACHE["ts"] = now
        logger.info("[digest] refreshed from %d/%d sources", len(chunks), len(urls))
    return _CACHE["text"]


def current() -> str:
    return _CACHE["text"]
