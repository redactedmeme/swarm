"""Deep research — multi-step: search → vet → fetch → synthesize with citations."""

import re
import time
import logging
import asyncio
from urllib.parse import urlparse

import aiohttp
import llm_client as llm

logger = logging.getLogger(__name__)

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE  = re.compile(r"\s{2,}")

# Trusted domain tiers for credibility scoring
_TIER1 = {"arxiv.org", "pubmed.ncbi.nlm.nih.gov", "scholar.google.com", "nature.com",
           "science.org", "ieee.org", "acm.org", "ncbi.nlm.nih.gov"}
_TIER2 = {"wikipedia.org", "britannica.com", "mit.edu", "stanford.edu", "oxford.ac.uk",
           "cam.ac.uk", "nasa.gov", "nih.gov", "who.int", "un.org"}


def _strip_html(raw: str) -> str:
    text = _TAG_RE.sub(" ", raw)
    return _WS_RE.sub(" ", text).strip()


def _credibility_score(url: str) -> float:
    try:
        domain = urlparse(url).netloc.lstrip("www.")
        if any(t in domain for t in _TIER1):
            return 1.0
        if any(t in domain for t in _TIER2):
            return 0.75
        # Penalise known low-quality patterns
        if any(x in url for x in ("reddit.com", "quora.com", "yahoo.com/answers")):
            return 0.2
        return 0.5
    except Exception:
        return 0.4


async def _fetch_body(url: str, session: aiohttp.ClientSession) -> str:
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=10), allow_redirects=True) as r:
            if r.status != 200:
                return ""
            ct = r.headers.get("Content-Type", "")
            if "text" not in ct:
                return ""
            raw = await r.text(errors="ignore")
            return _strip_html(raw)[:3000]
    except Exception as e:
        logger.debug(f"[deep_research] fetch {url}: {e}")
        return ""


async def run(task: str, context: dict) -> tuple[str, str, list[str]]:
    try:
        from duckduckgo_search import DDGS
        hits = DDGS().text(task, max_results=8)
    except Exception as e:
        logger.warning(f"[deep_research] DDG failed: {e}")
        result, model = await llm.call(
            "You are a research analyst. Answer thoroughly with citations where possible, note uncertainty.",
            f"Deep research task: {task}",
            max_tokens=600, prefer_strong=True,
        )
        return result, model, ["reasoning:fallback"]

    if not hits:
        result, model = await llm.call(
            "You are a research analyst. Answer thoroughly, note uncertainty, flag gaps.",
            f"Deep research task: {task}",
            max_tokens=600, prefer_strong=True,
        )
        return result, model, ["reasoning:no_results"]

    # Vet and rank by credibility
    scored = sorted(
        [{"hit": h, "score": _credibility_score(h["href"])} for h in hits],
        key=lambda x: x["score"], reverse=True,
    )
    top4 = scored[:4]

    # Fetch bodies concurrently
    async with aiohttp.ClientSession(headers={"User-Agent": "Mozilla/5.0"}) as session:
        bodies = await asyncio.gather(*[_fetch_body(s["hit"]["href"], session) for s in top4])

    snippets = []
    sources = ["web:ddg:deep"]
    for i, (entry, body) in enumerate(zip(top4, bodies), 1):
        hit = entry["hit"]
        text = body if body else hit.get("body", "")
        cred = entry["score"]
        cred_label = "★★★" if cred >= 0.9 else "★★" if cred >= 0.6 else "★"
        if text:
            snippets.append(
                f"[{i}] {hit['title']} {cred_label}\n"
                f"URL: {hit['href']}\n"
                f"{text[:1200]}"
            )
            sources.append(hit["href"])

    # Also include body snippets from lower-ranked results as supporting context
    remaining_bodies = [h["hit"].get("body", "") for h in scored[4:]]
    supporting = " | ".join(b[:200] for b in remaining_bodies if b)

    context_block = "\n\n".join(snippets)
    system = (
        "You are a rigorous research analyst. Synthesize the sources below into a 350–450 word briefing. "
        "Rules: (1) Cite inline as [1] [2] [3] [4]. "
        "(2) Lead with the most credible finding. "
        "(3) Note any disagreement between sources. "
        "(4) Flag your confidence level: HIGH / MEDIUM / LOW at the end. "
        "(5) List 3 suggested follow-up queries. "
        "Be precise. Do not pad."
    )
    user_parts = [f"Research task: {task}", f"\nSources:\n{context_block}"]
    if supporting:
        user_parts.append(f"\nAdditional context: {supporting[:600]}")

    result, model = await llm.call(system, "\n".join(user_parts), max_tokens=600, prefer_strong=True)
    return result, model, sources
