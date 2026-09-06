# hermes-bot/plugins/swarm-manager/web_tools.py
"""
Web tools for Hermes — web_fetch and web_search.
SSRF-protected. No API key required for search (DuckDuckGo Instant Answers).
"""
from __future__ import annotations

import json
import logging
import re

import requests

logger = logging.getLogger("swarm-manager.web")

# ── SSRF guard + readable extraction — one shared copy in swarm_core.web ──────

try:
    from swarm_core.web import is_blocked as _is_ssrf_blocked  # noqa: F401
    from swarm_core.web import extract as _extract
except Exception:  # pragma: no cover - fallback keeps hermes bootable offline
    _BLOCKED_HOST_PATTERNS = [
        "localhost", "127.", "10.", "192.168.", "0.0.0.0", ".internal", "metadata.",
    ]
    _BLOCKED_172_RE = re.compile(r"172\.(1[6-9]|2\d|3[01])\.")

    def _is_ssrf_blocked(url: str) -> bool:
        lower = (url or "").lower()
        if not (lower.startswith("http://") or lower.startswith("https://")):
            return True
        host_part = lower.split("://", 1)[1].split("/")[0]
        if any(p in host_part for p in _BLOCKED_HOST_PATTERNS):
            return True
        return bool(_BLOCKED_172_RE.search(host_part))

    def _extract(html: str, url: str = "") -> dict:
        text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html or "")).strip()
        return {"title": "", "markdown": text, "text": text, "word_count": len(text.split())}


# Default fetch truncation. Raised from 3000 now that extraction removes chrome,
# but a parameter, not a constant — the Groq TPM ceiling makes full-context
# calls unreachable on some routes, so callers must be able to ask for less.
_DEFAULT_MAX_CHARS = 8000


# ── Handlers ──────────────────────────────────────────────────────────────────

def _handle_web_fetch(args: dict) -> str:
    url = args.get("url", "").strip()
    if not url:
        return json.dumps({"status": "error", "error": "No URL provided"})

    try:
        max_chars = int(args.get("max_chars") or _DEFAULT_MAX_CHARS)
    except (TypeError, ValueError):
        max_chars = _DEFAULT_MAX_CHARS
    max_chars = max(200, min(max_chars, 40000))

    if _is_ssrf_blocked(url):
        return json.dumps({"status": "error", "error": f"URL blocked by SSRF guard: {url}"})

    try:
        resp = requests.get(
            url,
            timeout=15,
            headers={"User-Agent": "HermesBot/1.0"},
            allow_redirects=True,
        )
        resp.raise_for_status()
        doc = _extract(resp.text, url)
        body = doc.get("markdown") or doc.get("text") or ""
        return json.dumps({
            "status": "ok",
            "url": url,
            "title": doc.get("title", ""),
            "text": body[:max_chars],
            "word_count": doc.get("word_count", 0),
            "length": len(body),
            "truncated": len(body) > max_chars,
        })
    except Exception as e:
        logger.warning("[web_fetch] Error fetching %s: %s", url, e)
        return json.dumps({"status": "error", "error": str(e)})


def _handle_web_search(args: dict) -> str:
    query = args.get("query", "").strip()
    if not query:
        return json.dumps({"status": "error", "error": "No query provided"})

    try:
        resp = requests.get(
            "https://api.duckduckgo.com/",
            params={
                "q": query,
                "format": "json",
                "no_html": "1",
                "skip_disambig": "1",
            },
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()

        abstract = data.get("AbstractText", "")
        abstract_url = data.get("AbstractURL", "")

        related = []
        for item in data.get("RelatedTopics", [])[:3]:
            text = item.get("Text", "")
            if text:
                related.append(text)

        results = []
        for item in data.get("Results", [])[:3]:
            results.append({
                "title": item.get("Text", ""),
                "url": item.get("FirstURL", ""),
                "text": item.get("Text", ""),
            })

        # Fallback: scrape HTML results if DDG instant answers returned nothing
        if not abstract and not related and not results:
            try:
                fallback_url = f"https://html.duckduckgo.com/html/?q={requests.utils.quote(query)}"
                fb_resp = requests.get(
                    fallback_url,
                    timeout=10,
                    headers={"User-Agent": "HermesBot/1.0"},
                )
                fb_html = fb_resp.text
                # Extract result snippets
                snippets = re.findall(
                    r'class="result__snippet"[^>]*>(.*?)</a>',
                    fb_html,
                    re.DOTALL,
                )
                titles = re.findall(
                    r'class="result__a"[^>]*>(.*?)</a>',
                    fb_html,
                    re.DOTALL,
                )
                for i in range(min(5, len(snippets))):
                    title = re.sub(r"<[^>]+>", " ", titles[i]).strip() if i < len(titles) else ""
                    snippet = re.sub(r"<[^>]+>", " ", snippets[i]).strip()
                    results.append({"title": title, "snippet": snippet})
            except Exception as fe:
                logger.debug("[web_search] Fallback scrape failed: %s", fe)

        return json.dumps({
            "status": "ok",
            "abstract": abstract,
            "abstract_url": abstract_url,
            "related": related,
            "results": results,
        })
    except Exception as e:
        logger.warning("[web_search] Error searching %r: %s", query, e)
        return json.dumps({"status": "error", "error": str(e)})


# ── Registration ──────────────────────────────────────────────────────────────

def register(ctx):
    ctx.register_tool(
        name="web_fetch",
        toolset="swarm",
        schema={
            "name": "web_fetch",
            "description": "Fetch the text content of a web page",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "The full URL to fetch (http/https only)",
                    },
                    "max_chars": {
                        "type": "integer",
                        "description": "Max characters of readable text to return (default 8000)",
                    },
                },
                "required": ["url"],
            },
        },
        handler=_handle_web_fetch,
    )

    ctx.register_tool(
        name="web_search",
        toolset="swarm",
        schema={
            "name": "web_search",
            "description": "Search the web using DuckDuckGo Instant Answers",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The search query",
                    },
                },
                "required": ["query"],
            },
        },
        handler=_handle_web_search,
    )

    logger.info("[swarm-manager] Web tools registered (2 tools)")
