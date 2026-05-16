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

# ── SSRF guard ────────────────────────────────────────────────────────────────

_BLOCKED_HOST_PATTERNS = [
    "localhost",
    "127.",
    "10.",
    "192.168.",
    "0.0.0.0",
    ".railway.internal",
    "metadata.",
]

# 172.16.0.0/12 → 172.16.x.x through 172.31.x.x
_BLOCKED_172_RE = re.compile(r"172\.(1[6-9]|2\d|3[01])\.")


def _is_ssrf_blocked(url: str) -> bool:
    """Return True if the URL should be blocked for SSRF protection."""
    lower = url.lower()

    # Scheme check
    if not (lower.startswith("http://") or lower.startswith("https://")):
        return True

    # Strip scheme
    host_part = lower.split("://", 1)[1].split("/")[0]

    for pattern in _BLOCKED_HOST_PATTERNS:
        if pattern in host_part:
            return True

    if _BLOCKED_172_RE.search(host_part):
        return True

    return False


# ── Handlers ──────────────────────────────────────────────────────────────────

def _handle_web_fetch(args: dict) -> str:
    url = args.get("url", "").strip()
    if not url:
        return json.dumps({"status": "error", "error": "No URL provided"})

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
        html = resp.text
        text = re.sub(r"<[^>]+>", " ", html)
        text = re.sub(r"\s+", " ", text).strip()
        return json.dumps({
            "status": "ok",
            "url": url,
            "text": text[:3000],
            "length": len(text),
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
