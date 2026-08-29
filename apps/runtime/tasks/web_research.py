"""Web research — DuckDuckGo search + fetch + Groq synthesis."""

import re
import logging
import asyncio

import aiohttp
import llm_client as llm
from url_guard import validate_url

logger = logging.getLogger(__name__)

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE  = re.compile(r"\s{2,}")


def _strip_html(raw: str) -> str:
    text = _TAG_RE.sub(" ", raw)
    return _WS_RE.sub(" ", text).strip()


async def _fetch_body(url: str, session: aiohttp.ClientSession) -> str:
    try:
        validate_url(url)
    except ValueError:
        return ""
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=8), allow_redirects=False) as r:
            if r.status != 200:
                return ""
            ct = r.headers.get("Content-Type", "")
            if "text" not in ct:
                return ""
            raw = await r.text(errors="ignore")
            return _strip_html(raw)[:2500]
    except Exception as e:
        logger.debug(f"[web_research] fetch {url}: {e}")
        return ""


async def run(task: str, context: dict) -> tuple[str, str, list[str]]:
    try:
        from duckduckgo_search import DDGS
        hits = DDGS().text(task, max_results=5)
    except Exception as e:
        logger.warning(f"[web_research] DDG failed: {e}")
        # Fallback to pure reasoning if DDG unavailable
        result, model = await llm.call(
            "You are a research assistant. Answer thoroughly, note uncertainty, use bullet points.",
            f"Research task: {task}",
            max_tokens=500, prefer_strong=True,
        )
        return result, model, ["reasoning:fallback"]

    if not hits:
        result, model = await llm.call(
            "You are a research assistant. Answer thoroughly, note uncertainty, use bullet points.",
            f"Research task: {task}",
            max_tokens=500, prefer_strong=True,
        )
        return result, model, ["reasoning:no_results"]

    # Fetch top 3 pages concurrently
    async with aiohttp.ClientSession(headers={"User-Agent": "Mozilla/5.0"}) as session:
        bodies = await asyncio.gather(*[_fetch_body(h["href"], session) for h in hits[:3]])

    # Build source context
    snippets = []
    sources = ["web:ddg"]
    for i, (hit, body) in enumerate(zip(hits[:3], bodies), 1):
        text = body if body else hit.get("body", "")
        if text:
            snippets.append(f"[{i}] {hit['title']}\nURL: {hit['href']}\n{text[:800]}")
            sources.append(hit["href"])

    if not snippets:
        # Fall back to DDG body snippets only
        for i, h in enumerate(hits[:3], 1):
            if h.get("body"):
                snippets.append(f"[{i}] {h['title']}\n{h['body']}")

    context_block = "\n\n".join(snippets)
    system = (
        "You are a research analyst. Synthesize the sources below into a clear 250–300 word briefing. "
        "Cite sources inline as [1], [2], [3]. Flag any contradictions or uncertainty. "
        "End with 2 suggested follow-up queries."
    )
    user = f"Task: {task}\n\nSources:\n{context_block}"

    result, model = await llm.call(system, user, max_tokens=500, prefer_strong=True)
    return result, model, sources
