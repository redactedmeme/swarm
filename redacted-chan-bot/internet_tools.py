"""
internet_tools.py — external data access for redacted-chan.

Tools to access real-time data, search the web, call APIs, and gather information.
"""

import requests
import json
import logging
from typing import Optional, Any
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# ── Web Search ──────────────────────────────────────────────────────────────

def web_search(query: str, limit: int = 5) -> dict:
    """
    Search the web using DuckDuckGo API (no key required).

    Args:
        query: Search query
        limit: Number of results (max 10)

    Returns:
        dict with 'results' list containing search results
    """
    try:
        # DuckDuckGo instant answer + web search
        url = "https://api.duckduckgo.com/"
        params = {
            "q": query,
            "format": "json",
            "no_redirect": 1,
            "skip_disambig": 1,
        }

        resp = requests.get(url, params=params, timeout=5)
        resp.raise_for_status()
        data = resp.json()

        # Extract results
        results = []

        # Add instant answer if available
        if data.get("AbstractText"):
            results.append({
                "title": data.get("Heading", "Instant Answer"),
                "snippet": data.get("AbstractText"),
                "url": data.get("AbstractURL", ""),
                "source": "instant_answer"
            })

        # Add web results
        for result in data.get("Results", [])[:limit]:
            results.append({
                "title": result.get("Title"),
                "snippet": result.get("Text"),
                "url": result.get("FirstURL"),
                "source": "web_search"
            })

        # Add related topics if needed
        for topic in data.get("RelatedTopics", [])[:2]:
            if topic.get("Text"):
                results.append({
                    "title": topic.get("FirstURL", "Related"),
                    "snippet": topic.get("Text"),
                    "url": topic.get("FirstURL", ""),
                    "source": "related_topic"
                })

        return {
            "status": "success",
            "query": query,
            "result_count": len(results),
            "results": results[:limit]
        }
    except Exception as e:
        logger.error(f"[internet] web_search failed: {e}")
        return {
            "status": "error",
            "error": str(e),
            "query": query
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
