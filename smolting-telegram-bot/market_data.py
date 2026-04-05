# smolting-telegram-bot/market_data.py
"""
Real-time market data aggregator for /alpha command.
Sources (all free or key-based):
  - DexScreener   : price, volume, liquidity, buys/sells (no key needed)
  - Birdeye       : token overview, OHLCV, holder count (BIRDEYE_API_KEY)
  - CoinGecko     : SOL price + 24h change (no key needed)
  - Jupiter       : fallback price quote (no key needed)
"""
import os
import asyncio
import logging
import aiohttp
from typing import Optional

logger = logging.getLogger(__name__)

# $REDACTED token addresses (v1 and v2)
REDACTED_V2 = os.getenv("REDACTED_TOKEN", "9mtKd1o8Ht7F1daumKgs5D8EdVyopWBfYQwNmMojpump")
REDACTED_V1 = "9a21gb7fWGm9dD2UFdZAzgFn5K1NwfmYkjyLbpAcKgnM"
SOL_MINT    = "So11111111111111111111111111111111111111112"

BIRDEYE_KEY  = os.getenv("BIRDEYE_API_KEY", "")
XAI_KEY      = os.getenv("XAI_API_KEY", "")
BIRDEYE_BASE = "https://public-api.birdeye.so"
DEX_BASE     = "https://api.dexscreener.com"
GECKO_BASE   = "https://api.coingecko.com/api/v3"
XAI_BASE     = "https://api.x.ai/v1"

# Simple in-process cache for Birdeye (avoids 429 on repeated calls)
_birdeye_cache: dict = {}
_birdeye_cache_ts: dict = {}
BIRDEYE_CACHE_TTL = 300  # 5 minutes


# ---------------------------------------------------------------------------
# DexScreener
# ---------------------------------------------------------------------------
async def fetch_dexscreener(token_address: str) -> Optional[dict]:
    """Fetch token pair data from DexScreener. Returns the most-liquid pair."""
    url = f"{DEX_BASE}/tokens/v1/solana/{token_address}"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=8)) as resp:
                if resp.status != 200:
                    logger.warning(f"DexScreener {resp.status} for {token_address}")
                    return None
                data = await resp.json()
                # data is a list of pairs; pick highest liquidity
                pairs = data if isinstance(data, list) else data.get("pairs", [])
                if not pairs:
                    return None
                best = max(pairs, key=lambda p: float(p.get("liquidity", {}).get("usd", 0) or 0))
                return best
    except Exception as e:
        logger.error(f"DexScreener error: {e}")
        return None


def _fmt_dex(pair: dict) -> dict:
    """Normalize a DexScreener pair into a flat summary dict."""
    if not pair:
        return {}
    price_usd = pair.get("priceUsd") or "?"
    price_native = pair.get("priceNative") or "?"
    vol = pair.get("volume", {})
    txns = pair.get("txns", {}).get("h24", {})
    liq = pair.get("liquidity", {})
    chg = pair.get("priceChange", {})
    return {
        "price_usd":     price_usd,
        "price_sol":     price_native,
        "vol_24h":       vol.get("h24", "?"),
        "vol_1h":        vol.get("h1", "?"),
        "buys_24h":      txns.get("buys", "?"),
        "sells_24h":     txns.get("sells", "?"),
        "liquidity_usd": liq.get("usd", "?"),
        "fdv":           pair.get("fdv", "?"),
        "mcap":          pair.get("marketCap", "?"),
        "change_5m":     chg.get("m5", "?"),
        "change_1h":     chg.get("h1", "?"),
        "change_24h":    chg.get("h24", "?"),
        "dex":           pair.get("dexId", "?"),
        "pair_url":      pair.get("url", ""),
    }


# ---------------------------------------------------------------------------
# Birdeye
# ---------------------------------------------------------------------------
async def fetch_birdeye_overview(token_address: str) -> Optional[dict]:
    """Fetch token overview from Birdeye with 5-minute cache to avoid 429s."""
    import time
    if not BIRDEYE_KEY:
        return None

    cache_key = f"overview:{token_address}"
    now = time.monotonic()
    if cache_key in _birdeye_cache and now - _birdeye_cache_ts.get(cache_key, 0) < BIRDEYE_CACHE_TTL:
        return _birdeye_cache[cache_key]

    url = f"{BIRDEYE_BASE}/defi/token_overview"
    headers = {
        "X-API-KEY": BIRDEYE_KEY,
        "x-chain": "solana",
        "accept": "application/json",
    }
    params = {"address": token_address}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, params=params,
                                   timeout=aiohttp.ClientTimeout(total=8)) as resp:
                if resp.status == 429:
                    logger.warning("Birdeye overview 429 — returning cached data if available")
                    return _birdeye_cache.get(cache_key)
                if resp.status != 200:
                    logger.warning(f"Birdeye overview {resp.status}")
                    return None
                body = await resp.json()
                data = body.get("data") or body
                _birdeye_cache[cache_key] = data
                _birdeye_cache_ts[cache_key] = now
                return data
    except Exception as e:
        logger.error(f"Birdeye overview error: {e}")
        return _birdeye_cache.get(cache_key)


async def fetch_birdeye_ohlcv(token_address: str, interval: str = "1D") -> Optional[list]:
    """Fetch recent OHLCV bars from Birdeye."""
    if not BIRDEYE_KEY:
        return None
    import time
    now = int(time.time())
    time_from = now - 7 * 86400  # last 7 days
    url = f"{BIRDEYE_BASE}/defi/ohlcv"
    headers = {
        "X-API-KEY": BIRDEYE_KEY,
        "x-chain": "solana",
        "accept": "application/json",
    }
    params = {
        "address": token_address,
        "type": interval,
        "time_from": time_from,
        "time_to": now,
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, params=params,
                                   timeout=aiohttp.ClientTimeout(total=8)) as resp:
                if resp.status != 200:
                    logger.warning(f"Birdeye OHLCV {resp.status}")
                    return None
                body = await resp.json()
                items = (body.get("data") or {}).get("items") or []
                return items[-3:] if items else None  # last 3 days
    except Exception as e:
        logger.error(f"Birdeye OHLCV error: {e}")
        return None


async def fetch_birdeye_trending() -> Optional[list]:
    """Fetch trending Solana tokens from Birdeye."""
    if not BIRDEYE_KEY:
        return None
    url = f"{BIRDEYE_BASE}/defi/trending_tokens/solana"
    headers = {
        "X-API-KEY": BIRDEYE_KEY,
        "x-chain": "solana",
        "accept": "application/json",
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers,
                                   timeout=aiohttp.ClientTimeout(total=8)) as resp:
                if resp.status != 200:
                    return None
                body = await resp.json()
                items = (body.get("data") or {}).get("items") or body.get("data") or []
                return items[:5]
    except Exception as e:
        logger.error(f"Birdeye trending error: {e}")
        return None


# ---------------------------------------------------------------------------
# CoinGecko — macro context (no key needed on free tier)
# ---------------------------------------------------------------------------
async def fetch_coingecko_sol() -> Optional[dict]:
    """Fetch SOL price + 24h change from CoinGecko."""
    url = f"{GECKO_BASE}/simple/price"
    params = {
        "ids": "solana",
        "vs_currencies": "usd",
        "include_24hr_change": "true",
        "include_market_cap": "true",
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params,
                                   timeout=aiohttp.ClientTimeout(total=8)) as resp:
                if resp.status != 200:
                    return None
                body = await resp.json()
                sol = body.get("solana", {})
                return {
                    "sol_price":      sol.get("usd", "?"),
                    "sol_change_24h": round(sol.get("usd_24h_change", 0), 2),
                    "sol_mcap":       sol.get("usd_market_cap", "?"),
                }
    except Exception as e:
        logger.error(f"CoinGecko error: {e}")
        return None


async def fetch_coingecko_global() -> Optional[dict]:
    """Fetch global crypto market dominance + total cap."""
    url = f"{GECKO_BASE}/global"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=8)) as resp:
                if resp.status != 200:
                    return None
                body = await resp.json()
                d = body.get("data", {})
                chg = d.get("market_cap_change_percentage_24h_usd", "?")
                total = d.get("total_market_cap", {}).get("usd", "?")
                btc_dom = d.get("market_cap_percentage", {}).get("btc", "?")
                return {
                    "total_mcap_usd": total,
                    "mcap_change_24h": round(chg, 2) if isinstance(chg, float) else chg,
                    "btc_dominance":   round(btc_dom, 1) if isinstance(btc_dom, float) else btc_dom,
                }
    except Exception as e:
        logger.error(f"CoinGecko global error: {e}")
        return None


# ---------------------------------------------------------------------------
# Jupiter price (backup / cross-check)
# ---------------------------------------------------------------------------
async def fetch_x_intelligence(query: str = None) -> Optional[str]:
    """
    Use xAI Grok Responses API with x_search tool to fetch live CT/X sentiment.
    Requires XAI_API_KEY with credits. Returns a summary string or None.
    Model: grok-3-mini (cheapest with x_search support).
    """
    if not XAI_KEY:
        return None

    prompt = query or (
        "Search X for recent posts about: $REDACTED meme token, Solana meme coins alpha, "
        "pattern blue, wassie crypto, and Solana DeFi in the last 24 hours. "
        "Summarize: sentiment, notable posts, any alpha signals or whale activity. "
        "Keep it under 150 words."
    )
    payload = {
        "model": "grok-3-mini",
        "stream": False,
        "input": [{"role": "user", "content": prompt}],
        "tools": [{"type": "x_search"}],
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{XAI_BASE}/responses",
                headers={
                    "Authorization": f"Bearer {XAI_KEY}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                if resp.status == 403:
                    logger.warning("xAI x_search: no credits — add billing at console.x.ai")
                    return None
                if resp.status != 200:
                    logger.warning(f"xAI x_search {resp.status}: {await resp.text()}")
                    return None
                body = await resp.json()
                # Extract text from output array
                for item in body.get("output", []):
                    if item.get("type") == "message":
                        for c in item.get("content", []):
                            if c.get("type") == "output_text":
                                return c.get("text", "").strip()
                return None
    except Exception as e:
        logger.error(f"xAI x_search error: {e}")
        return None


async def fetch_jupiter_price(token_address: str) -> Optional[float]:
    """Fetch token price in USD from Jupiter Price API v2."""
    url = f"https://api.jup.ag/price/v2"
    params = {"ids": token_address}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params,
                                   timeout=aiohttp.ClientTimeout(total=6)) as resp:
                if resp.status != 200:
                    return None
                body = await resp.json()
                price_str = (body.get("data") or {}).get(token_address, {}).get("price")
                return float(price_str) if price_str else None
    except Exception as e:
        logger.error(f"Jupiter price error: {e}")
        return None


# ---------------------------------------------------------------------------
# Aggregate — single call used by /alpha
# ---------------------------------------------------------------------------
async def get_alpha_context() -> dict:
    """
    Fetch all market data concurrently and return a structured context dict
    ready to be formatted into the LLM prompt.
    """
    (dex_raw, birdeye_ov, birdeye_ohlcv, birdeye_trend,
     sol_data, global_data, jup_price, x_intel) = await asyncio.gather(
        fetch_dexscreener(REDACTED_V2),
        fetch_birdeye_overview(REDACTED_V2),
        fetch_birdeye_ohlcv(REDACTED_V2),
        fetch_birdeye_trending(),
        fetch_coingecko_sol(),
        fetch_coingecko_global(),
        fetch_jupiter_price(REDACTED_V2),
        fetch_x_intelligence(),
        return_exceptions=True,
    )

    # Normalize exceptions to None
    def safe(v):
        return None if isinstance(v, Exception) else v

    dex     = _fmt_dex(safe(dex_raw)) if safe(dex_raw) else {}
    bird    = safe(birdeye_ov) or {}
    ohlcv   = safe(birdeye_ohlcv) or []
    trend   = safe(birdeye_trend) or []
    sol     = safe(sol_data) or {}
    glbl    = safe(global_data) or {}
    jup     = safe(jup_price)
    x_ct    = safe(x_intel)

    return {
        "token_address": REDACTED_V2,
        "dexscreener":   dex,
        "birdeye":       bird,
        "ohlcv_7d":      ohlcv,
        "trending_sol":  trend,
        "sol":           sol,
        "global":        glbl,
        "jupiter_price": jup,
        "x_intelligence": x_ct,
    }


def format_alpha_context(ctx: dict) -> str:
    """Convert the context dict into a compact, LLM-readable string."""
    lines = ["=== LIVE MARKET DATA ==="]

    dex = ctx.get("dexscreener", {})
    if dex:
        lines.append(f"\n$REDACTED (DexScreener):")
        lines.append(f"  Price: ${dex.get('price_usd')} | SOL: {dex.get('price_sol')}")
        lines.append(f"  24h change: {dex.get('change_24h')}% | 1h: {dex.get('change_1h')}% | 5m: {dex.get('change_5m')}%")
        lines.append(f"  Volume 24h: ${dex.get('vol_24h')} | 1h: ${dex.get('vol_1h')}")
        lines.append(f"  Liquidity: ${dex.get('liquidity_usd')} | FDV: ${dex.get('fdv')} | MCap: ${dex.get('mcap')}")
        lines.append(f"  Buys/Sells 24h: {dex.get('buys_24h')}/{dex.get('sells_24h')} | DEX: {dex.get('dex')}")

    bird = ctx.get("birdeye", {})
    if bird:
        lines.append(f"\n$REDACTED (Birdeye):")
        holder_keys = ["holder", "holders", "holderCount", "uniqueWallets"]
        holders = next((bird.get(k) for k in holder_keys if bird.get(k)), "?")
        lines.append(f"  Holders: {holders}")
        v24 = bird.get("v24hUSD") or bird.get("volume24h") or bird.get("volumeUSD24h")
        if v24:
            lines.append(f"  Volume 24h (Birdeye): ${v24}")
        v24_chg = bird.get("v24hChangePercent") or bird.get("volumeChange24h")
        if v24_chg is not None:
            lines.append(f"  Volume change 24h: {round(float(v24_chg), 2)}%")
        price_chg = bird.get("priceChange24h") or bird.get("price24hChangePercent")
        if price_chg is not None:
            lines.append(f"  Price change 24h: {round(float(price_chg), 2)}%")
        trade24 = bird.get("trade24h") or bird.get("trades24h")
        if trade24:
            lines.append(f"  Trades 24h: {trade24}")

    ohlcv = ctx.get("ohlcv_7d", [])
    if ohlcv:
        lines.append(f"\n$REDACTED OHLCV (last {len(ohlcv)} days, Birdeye):")
        for bar in ohlcv:
            import datetime
            ts = bar.get("unixTime") or bar.get("time") or 0
            date_str = datetime.datetime.utcfromtimestamp(ts).strftime("%m/%d") if ts else "?"
            lines.append(
                f"  {date_str}: O={bar.get('o','?')} H={bar.get('h','?')} "
                f"L={bar.get('l','?')} C={bar.get('c','?')} V={bar.get('v','?')}"
            )

    jup = ctx.get("jupiter_price")
    if jup:
        lines.append(f"\n$REDACTED Jupiter price: ${jup}")

    sol = ctx.get("sol", {})
    if sol:
        lines.append(f"\nSOL: ${sol.get('sol_price')} ({sol.get('sol_change_24h')}% 24h)")

    glbl = ctx.get("global", {})
    if glbl:
        lines.append(f"Global market 24h change: {glbl.get('mcap_change_24h')}% | BTC dom: {glbl.get('btc_dominance')}%")

    trend = ctx.get("trending_sol", [])
    if trend:
        lines.append(f"\nTrending on Solana (Birdeye):")
        for t in trend[:5]:
            sym  = t.get("symbol") or t.get("name") or "?"
            chg  = t.get("price24hChangePercent") or t.get("priceChange24h") or "?"
            vol  = t.get("v24hUSD") or t.get("volume24h") or "?"
            lines.append(f"  {sym}: {chg}% 24h | vol ${vol}")

    x_ct = ctx.get("x_intelligence")
    if x_ct:
        lines.append(f"\n=== CT / X INTELLIGENCE (Grok live search) ===")
        lines.append(x_ct)

    return "\n".join(lines)
