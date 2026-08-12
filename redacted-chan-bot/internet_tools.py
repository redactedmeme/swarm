"""
internet_tools.py — external data access for redacted-chan.

Tools to access real-time data, search the web, call APIs, and gather information.
"""

import os
import re
import ipaddress
import requests
import json
import logging
from typing import Optional, Any
from urllib.parse import urlparse, unquote
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# ── Safety filter ───────────────────────────────────────────────────────────

# Hardcoded floor — user env can extend but not shrink.
_DEFAULT_DENY = {
    "pornhub.com", "xvideos.com", "xhamster.com", "redtube.com", "youporn.com",
    "pastebin.com", "4chan.org", "8kun.top", "kiwifarms.net",
}
_DEFAULT_BLOCK_TERMS = {"porn", "nsfw", "xxx"}


def _env_set(name: str) -> set[str]:
    raw = os.getenv(name, "")
    return {p.strip().lower() for p in raw.split(",") if p.strip()}


def _host(url: str) -> str:
    try:
        return (urlparse(url).hostname or "").lower()
    except Exception:
        return ""


def _is_allowed(url: str) -> bool:
    """Reject unsafe or out-of-scope URLs (SSRF/adult/denylisted)."""
    if not url:
        return False
    host = _host(url)
    if not host:
        return False
    # Block IP literals + loopback/private ranges (SSRF guard).
    try:
        ip = ipaddress.ip_address(host)
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
            return False
        # Bare public IPs are also suspicious for a chat assistant.
        return False
    except ValueError:
        pass
    if host in {"localhost"} or host.endswith(".local") or host.endswith(".onion"):
        return False
    deny = _DEFAULT_DENY | _env_set("WEBSEARCH_DENY_DOMAINS")
    if any(host == d or host.endswith("." + d) for d in deny):
        return False
    allow = _env_set("WEBSEARCH_ALLOW_DOMAINS")
    if allow and not any(host == a or host.endswith("." + a) for a in allow):
        return False
    return True


def _snippet_ok(snippet: str) -> bool:
    if not snippet or not snippet.strip():
        return False
    lo = snippet.lower()
    blocked = _DEFAULT_BLOCK_TERMS | _env_set("WEBSEARCH_BLOCK_TERMS")
    return not any(term in lo for term in blocked)


def _norm_key(url: str) -> str:
    p = urlparse(url)
    return f"{(p.hostname or '').lower()}{p.path.rstrip('/')}"


def _curate(raw: list[dict], limit: int) -> list[dict]:
    """Filter + dedupe + trim snippets."""
    seen: set[str] = set()
    out: list[dict] = []
    for r in raw:
        url = (r.get("url") or "").strip()
        snip = (r.get("snippet") or "").strip()
        if not _is_allowed(url) or not _snippet_ok(snip):
            continue
        key = _norm_key(url)
        if key in seen:
            continue
        seen.add(key)
        out.append({
            "title": (r.get("title") or url)[:200],
            "snippet": snip[:400],
            "url": url,
            "source": r.get("source", "web"),
        })
        if len(out) >= limit:
            break
    return out


# ── Web Search — multi-backend ──────────────────────────────────────────────

def _search_tavily(query: str, limit: int) -> tuple[list[dict], str]:
    """Returns (results, answer). Raises on failure."""
    key = os.getenv("TAVILY_API_KEY")
    if not key:
        raise RuntimeError("no TAVILY_API_KEY")
    resp = requests.post(
        "https://api.tavily.com/search",
        json={
            "api_key": key,
            "query": query,
            "max_results": min(max(limit, 1), 10),
            "search_depth": "basic",
            "include_answer": True,
            "include_raw_content": False,
        },
        timeout=10,
    )
    resp.raise_for_status()
    data = resp.json()
    results = [
        {
            "title": r.get("title"),
            "snippet": r.get("content", ""),
            "url": r.get("url"),
            "source": "tavily",
        }
        for r in data.get("results", [])
    ]
    return results, (data.get("answer") or "")


def _search_brave(query: str, limit: int) -> tuple[list[dict], str]:
    key = os.getenv("BRAVE_API_KEY")
    if not key:
        raise RuntimeError("no BRAVE_API_KEY")
    resp = requests.get(
        "https://api.search.brave.com/res/v1/web/search",
        params={"q": query, "count": min(max(limit, 1), 10)},
        headers={"X-Subscription-Token": key, "Accept": "application/json"},
        timeout=10,
    )
    resp.raise_for_status()
    data = resp.json()
    web = (data.get("web") or {}).get("results") or []
    results = [
        {
            "title": r.get("title"),
            "snippet": r.get("description", ""),
            "url": r.get("url"),
            "source": "brave",
        }
        for r in web
    ]
    return results, ""


_DDG_HTML_RE = re.compile(
    r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>'
    r'.*?<a[^>]+class="result__snippet"[^>]*>(.*?)</a>',
    re.DOTALL,
)
_TAG_RE = re.compile(r"<[^>]+>")


def _ddg_unwrap(href: str) -> str:
    # DDG HTML wraps links as /l/?uddg=<encoded>
    m = re.search(r"uddg=([^&]+)", href)
    return unquote(m.group(1)) if m else href


def _search_ddg(query: str, limit: int) -> tuple[list[dict], str]:
    resp = requests.post(
        "https://html.duckduckgo.com/html/",
        data={"q": query},
        headers={"User-Agent": "Mozilla/5.0 (redacted-chan)"},
        timeout=8,
    )
    resp.raise_for_status()
    results: list[dict] = []
    for href, title_html, snip_html in _DDG_HTML_RE.findall(resp.text):
        url = _ddg_unwrap(href)
        results.append({
            "title": _TAG_RE.sub("", title_html).strip(),
            "snippet": _TAG_RE.sub("", snip_html).strip(),
            "url": url,
            "source": "ddg",
        })
        if len(results) >= limit * 2:  # over-fetch; filter later
            break
    return results, ""


def web_search(
    query: str,
    limit: int = 5,
    include_domains: Optional[list[str]] = None,
    exclude_domains: Optional[list[str]] = None,
) -> dict:
    """
    Curated web search — Tavily → Brave → DDG HTML fallback.
    Results are safety-filtered, deduped, and summarized.
    """
    limit = min(max(int(limit or 5), 1), 10)
    query = (query or "").strip()
    if not query:
        return {"status": "error", "error": "empty query", "query": query}

    # Per-call overrides via env for the duration of this call.
    old_allow = os.environ.get("WEBSEARCH_ALLOW_DOMAINS")
    old_deny = os.environ.get("WEBSEARCH_DENY_DOMAINS")
    if include_domains:
        os.environ["WEBSEARCH_ALLOW_DOMAINS"] = ",".join(include_domains)
    if exclude_domains:
        merged = (old_deny + "," if old_deny else "") + ",".join(exclude_domains)
        os.environ["WEBSEARCH_DENY_DOMAINS"] = merged

    try:
        backends = [("tavily", _search_tavily), ("brave", _search_brave), ("ddg", _search_ddg)]
        raw, answer, used = [], "", "none"
        last_err = None
        for name, fn in backends:
            try:
                raw, answer = fn(query, limit)
                used = name
                if raw:
                    break
            except Exception as e:
                last_err = e
                logger.debug(f"[internet] {name} backend skipped: {e}")
                continue

        results = _curate(raw, limit)

        if not results and used == "none":
            return {
                "status": "error",
                "error": f"no backend succeeded: {last_err}",
                "query": query,
            }

        # Summarize: prefer Tavily's answer; else stitch top-3 snippets.
        if answer:
            summary = answer.strip()[:800]
        elif results:
            summary = " ".join(r["snippet"] for r in results[:3])[:800]
        else:
            summary = "no on-topic results after filtering"

        return {
            "status": "success",
            "query": query,
            "backend": used,
            "summary": summary,
            "result_count": len(results),
            "results": results,
        }
    except Exception as e:
        logger.error(f"[internet] web_search failed: {e}")
        return {"status": "error", "error": str(e), "query": query}
    finally:
        # Restore env
        for k, v in (("WEBSEARCH_ALLOW_DOMAINS", old_allow), ("WEBSEARCH_DENY_DOMAINS", old_deny)):
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


# ── Curated find persistence ────────────────────────────────────────────────

def remember_find(
    title: str,
    snippet: str,
    url: str,
    tags: Optional[list[str]] = None,
    reason: str = "",
) -> dict:
    """
    Persist an interesting web find into both the relationship vault (FTS)
    and the vector memory (semantic), so it can be recalled in later chats.
    """
    if not _is_allowed(url):
        return {"status": "error", "error": "url rejected by safety filter", "url": url}

    tags = tags or []
    body_parts = [f"[web_find] {title}".strip(), snippet.strip(), f"→ {url}"]
    if reason:
        body_parts.insert(1, f"why: {reason.strip()}")
    if tags:
        body_parts.append("tags: " + ", ".join(tags))
    content = "\n".join(p for p in body_parts if p)[:500]

    vault_id = None
    try:
        import relationship_vault as rv
        vault_id = rv.add_memory(
            content=content,
            category="moment",       # rv coerces unknown categories anyway
            title=f"🌐 {title[:70]}",
            emotional_tone=None,
            source="chan_web_search",
        )
    except Exception as e:
        logger.warning(f"[internet] vault add failed: {e}")

    vector_ok = False
    try:
        import vector_memory as vm
        fact_id = f"webfind:{vault_id or datetime.now(timezone.utc).timestamp()}"
        vector_ok = vm.add_fact(
            fact_id,
            f"{title}. {snippet} (source: {url})",
            metadata={"kind": "web_find", "url": url, "tags": ",".join(tags)},
        )
    except Exception as e:
        logger.warning(f"[internet] vector add failed: {e}")

    return {
        "status": "success" if (vault_id or vector_ok) else "error",
        "vault_id": vault_id,
        "vector_indexed": vector_ok,
        "title": title,
        "url": url,
    }


# ── API Client ──────────────────────────────────────────────────────────────

def api_call(
    url: str,
    method: str = "GET",
    headers: Optional[dict] = None,
    params: Optional[dict] = None,
    json_body: Optional[dict] = None,
    timeout: int = 10
) -> dict:
    """
    Make HTTP API call to external service.

    Args:
        url: API endpoint URL
        method: HTTP method (GET, POST, PUT, DELETE)
        headers: Optional headers dict
        params: Optional query parameters
        json_body: Optional JSON request body
        timeout: Request timeout in seconds

    Returns:
        dict with response data and status
    """
    try:
        resp = requests.request(
            method=method.upper(),
            url=url,
            headers=headers or {},
            params=params,
            json=json_body,
            timeout=timeout
        )
        resp.raise_for_status()

        return {
            "status": "success",
            "status_code": resp.status_code,
            "data": resp.json() if resp.headers.get("content-type") == "application/json" else resp.text,
            "url": url
        }
    except requests.exceptions.Timeout:
        return {
            "status": "error",
            "error": "Request timeout",
            "url": url
        }
    except requests.exceptions.HTTPError as e:
        return {
            "status": "error",
            "error": f"HTTP {e.response.status_code}: {e.response.text[:200]}",
            "url": url
        }
    except Exception as e:
        logger.error(f"[internet] api_call failed: {e}")
        return {
            "status": "error",
            "error": str(e),
            "url": url
        }


# ── Crypto & Market Data ────────────────────────────────────────────────────

def get_crypto_price(
    symbol: str,
    vs_currency: str = "usd"
) -> dict:
    """
    Get current cryptocurrency price from CoinGecko API (free, no key).

    Args:
        symbol: Crypto symbol (e.g., "bitcoin", "ethereum", "solana")
        vs_currency: Currency to compare against (default USD)

    Returns:
        dict with price and market data
    """
    try:
        url = "https://api.coingecko.com/api/v3/simple/price"
        params = {
            "ids": symbol.lower(),
            "vs_currencies": vs_currency.lower(),
            "include_market_cap": "true",
            "include_24hr_vol": "true",
            "include_24hr_change": "true"
        }

        resp = requests.get(url, params=params, timeout=5)
        resp.raise_for_status()
        data = resp.json()

        if not data or symbol.lower() not in data:
            return {
                "status": "error",
                "error": f"Symbol not found: {symbol}",
                "symbol": symbol
            }

        price_data = data[symbol.lower()]
        return {
            "status": "success",
            "symbol": symbol.upper(),
            "currency": vs_currency.upper(),
            "price": price_data.get(vs_currency.lower()),
            "market_cap": price_data.get(f"{vs_currency.lower()}_market_cap"),
            "volume_24h": price_data.get(f"{vs_currency.lower()}_24h_vol"),
            "change_24h": price_data.get(f"{vs_currency.lower()}_24h_change"),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    except Exception as e:
        logger.error(f"[internet] get_crypto_price failed: {e}")
        return {
            "status": "error",
            "error": str(e),
            "symbol": symbol
        }


def get_stock_price(symbol: str) -> dict:
    """
    Get stock price (via free API with rate limits).

    Args:
        symbol: Stock ticker (e.g., "AAPL", "GOOGL")

    Returns:
        dict with price and basic data
    """
    try:
        # Using yfinance-like endpoint via free API
        url = f"https://query1.finance.yahoo.com/v10/finance/quoteSummary/{symbol}"
        params = {
            "modules": "price,summaryDetail"
        }

        resp = requests.get(url, params=params, timeout=5)
        resp.raise_for_status()
        data = resp.json()

        if data.get("quoteSummary", {}).get("error"):
            return {
                "status": "error",
                "error": f"Stock not found: {symbol}",
                "symbol": symbol
            }

        result = data.get("quoteSummary", {}).get("result", [{}])[0]
        price_data = result.get("price", {})

        return {
            "status": "success",
            "symbol": symbol.upper(),
            "price": price_data.get("regularMarketPrice", {}).get("raw"),
            "currency": price_data.get("currency"),
            "change": price_data.get("regularMarketChange", {}).get("raw"),
            "change_percent": price_data.get("regularMarketChangePercent", {}).get("raw"),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    except Exception as e:
        logger.error(f"[internet] get_stock_price failed: {e}")
        return {
            "status": "error",
            "error": str(e),
            "symbol": symbol
        }


# ── News & Information ──────────────────────────────────────────────────────

def get_news(
    query: str,
    limit: int = 5
) -> dict:
    """
    Get recent news articles about a topic.

    Args:
        query: News search query
        limit: Number of articles to return

    Returns:
        dict with news articles
    """
    try:
        # Using NewsData.io free API (requires no key for basic search)
        # Fallback: use DuckDuckGo news search
        url = "https://api.duckduckgo.com/"
        params = {
            "q": f"{query} news",
            "format": "json",
            "no_redirect": 1,
            "t": "DDG"
        }

        resp = requests.get(url, params=params, timeout=5)
        resp.raise_for_status()
        data = resp.json()

        articles = []

        # Extract news results
        for result in data.get("Results", [])[:limit]:
            articles.append({
                "title": result.get("Title"),
                "snippet": result.get("Text"),
                "url": result.get("FirstURL"),
                "source": "news"
            })

        return {
            "status": "success",
            "query": query,
            "article_count": len(articles),
            "articles": articles
        }
    except Exception as e:
        logger.error(f"[internet] get_news failed: {e}")
        return {
            "status": "error",
            "error": str(e),
            "query": query
        }


def get_weather(location: str) -> dict:
    """
    Get current weather for a location.

    Args:
        location: City name or coordinates

    Returns:
        dict with weather data
    """
    try:
        # Using Open-Meteo (free, no key required)
        url = "https://geocoding-api.open-meteo.com/v1/search"
        params = {
            "name": location,
            "count": 1,
            "language": "en",
            "format": "json"
        }

        resp = requests.get(url, params=params, timeout=5)
        resp.raise_for_status()
        data = resp.json()

        if not data.get("results"):
            return {
                "status": "error",
                "error": f"Location not found: {location}"
            }

        place = data["results"][0]
        lat, lon = place.get("latitude"), place.get("longitude")

        # Get weather
        weather_url = "https://api.open-meteo.com/v1/forecast"
        weather_params = {
            "latitude": lat,
            "longitude": lon,
            "current": "temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m",
            "temperature_unit": "fahrenheit"
        }

        weather_resp = requests.get(weather_url, params=weather_params, timeout=5)
        weather_resp.raise_for_status()
        weather_data = weather_resp.json()

        current = weather_data.get("current", {})

        return {
            "status": "success",
            "location": f"{place.get('name')}, {place.get('country')}",
            "temperature": current.get("temperature_2m"),
            "unit": "°F",
            "humidity": current.get("relative_humidity_2m"),
            "wind_speed": current.get("wind_speed_10m"),
            "weather_code": current.get("weather_code"),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    except Exception as e:
        logger.error(f"[internet] get_weather failed: {e}")
        return {
            "status": "error",
            "error": str(e),
            "location": location
        }


# ── Tool Registry ────────────────────────────────────────────────────────────

def execute(tool_name: str, **kwargs) -> dict:
    """
    Execute an internet tool by name.

    Args:
        tool_name: Name of tool to execute
        **kwargs: Tool-specific arguments

    Returns:
        dict with tool result
    """
    tools = {
        "web_search": web_search,
        "api_call": api_call,
        "get_crypto_price": get_crypto_price,
        "get_stock_price": get_stock_price,
        "get_news": get_news,
        "get_weather": get_weather,
        "remember_find": remember_find,
    }

    if tool_name not in tools:
        return {
            "status": "error",
            "error": f"Unknown tool: {tool_name}",
            "available_tools": list(tools.keys())
        }

    try:
        result = tools[tool_name](**kwargs)
        logger.info(f"[internet] {tool_name} executed: {result.get('status')}")
        return result
    except Exception as e:
        logger.error(f"[internet] {tool_name} failed: {e}")
        return {
            "status": "error",
            "error": str(e),
            "tool": tool_name
        }
