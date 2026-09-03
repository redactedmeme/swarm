# redacteddegen-service/pool_monitor.py
"""
Real-time LP pool monitor for RedactedDegen.
Sources:
  - Raydium   : AMM pairs + CLMM pools (no key needed)
  - Orca      : Whirlpool CLMM pools   (no key needed)
  - Meteora   : DLMM pairs             (no key needed)

Fetches concurrently, normalizes to PoolData, computes IL, ranks by APR.
30-second cache per pool source (matches character spec).
"""
import os
import math
import time
import asyncio
import logging
import aiohttp
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

# ── Config ─────────────────────────────────────────────────────────────────
MIN_LIQUIDITY_USD   = float(os.getenv("POOL_MIN_LIQUIDITY", "100000"))
MAX_POOLS_PER_SOURCE = int(os.getenv("POOL_MAX_RESULTS", "10"))
POOL_CACHE_TTL      = 30   # seconds

RAYDIUM_BASE = "https://api.raydium.io"
ORCA_BASE    = "https://api.mainnet.orca.so"
METEORA_BASE = "https://dlmm-api.meteora.ag"

_cache: dict = {}
_cache_ts: dict = {}


# ── Data model ─────────────────────────────────────────────────────────────
@dataclass
class PoolData:
    source:        str           # "raydium" | "orca" | "meteora"
    name:          str           # e.g. "SOL-USDC"
    address:       str
    liquidity_usd: float
    volume_24h:    float
    fee_apr:       float         # fee-only APR %
    total_apr:     float         # fees + rewards APR %
    token_a:       str
    token_b:       str
    current_price: Optional[float] = None
    bin_step:      Optional[int]   = None   # Meteora DLMM only


@dataclass
class ILResult:
    entry_price:   float
    current_price: float
    price_ratio:   float
    il_pct:        float    # e.g. -2.5 means -2.5% IL

    @property
    def description(self) -> str:
        return f"IL {self.il_pct:+.2f}% (price moved {self.price_ratio:.3f}x from entry)"


# ── IL calculator ──────────────────────────────────────────────────────────
def compute_il(entry_price: float, current_price: float) -> ILResult:
    """
    Standard constant-product IL formula.
    IL = 2√k / (1+k) − 1   where k = current_price / entry_price
    Returns a negative percentage for loss.
    """
    if entry_price <= 0 or current_price <= 0:
        raise ValueError("Prices must be positive")
    k = current_price / entry_price
    il = (2 * math.sqrt(k) / (1 + k)) - 1
    return ILResult(
        entry_price=entry_price,
        current_price=current_price,
        price_ratio=k,
        il_pct=round(il * 100, 4),
    )


# ── Cache helper ───────────────────────────────────────────────────────────
def _cached(key: str):
    now = time.monotonic()
    if key in _cache and now - _cache_ts.get(key, 0) < POOL_CACHE_TTL:
        return _cache[key]
    return None


def _store(key: str, value):
    _cache[key] = value
    _cache_ts[key] = time.monotonic()
    return value


# ── Raydium ────────────────────────────────────────────────────────────────
async def fetch_raydium_pools() -> list[PoolData]:
    """
    Fetch top AMM pairs from Raydium V2.
    Filters by MIN_LIQUIDITY_USD, sorts by 24h APR descending.
    """
    cached = _cached("raydium")
    if cached is not None:
        return cached

    url = f"{RAYDIUM_BASE}/v2/main/pairs"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status != 200:
                    logger.warning(f"Raydium pairs {resp.status}")
                    return []
                raw = await resp.json()
    except Exception as e:
        logger.error(f"Raydium fetch error: {type(e).__name__}: {e}")
        return []

    pools: list[PoolData] = []
    for p in raw if isinstance(raw, list) else []:
        liq = float(p.get("liquidity") or 0)
        if liq < MIN_LIQUIDITY_USD:
            continue
        pools.append(PoolData(
            source        = "raydium",
            name          = p.get("name", "?"),
            address       = p.get("ammId", ""),
            liquidity_usd = liq,
            volume_24h    = float(p.get("volume24h") or 0),
            fee_apr       = float(p.get("apr24h") or 0),
            total_apr     = float(p.get("apr24h") or 0),  # Raydium V2 returns combined
            token_a       = (p.get("coin") or {}).get("symbol", "?"),
            token_b       = (p.get("pc")   or {}).get("symbol", "?"),
            current_price = float(p.get("price") or 0) or None,
        ))

    pools.sort(key=lambda x: x.total_apr, reverse=True)
    result = pools[:MAX_POOLS_PER_SOURCE]
    return _store("raydium", result)


# ── Orca ───────────────────────────────────────────────────────────────────
async def fetch_orca_pools() -> list[PoolData]:
    """
    Fetch top Whirlpool (CLMM) pools from Orca.
    Returns pools sorted by 24h total APR descending.
    """
    cached = _cached("orca")
    if cached is not None:
        return cached

    url = f"{ORCA_BASE}/v1/whirlpool/list"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status != 200:
                    logger.warning(f"Orca whirlpool {resp.status}")
                    return []
                body = await resp.json()
    except Exception as e:
        logger.error(f"Orca fetch error: {type(e).__name__}: {e}")
        return []

    whirlpools = body.get("whirlpools", []) if isinstance(body, dict) else body
    pools: list[PoolData] = []

    for p in whirlpools:
        tvl = float(p.get("tvl") or 0)
        if tvl < MIN_LIQUIDITY_USD:
            continue

        vol_day  = (p.get("volume") or {}).get("day", 0) or 0
        fee_apr  = (p.get("feeApr") or {}).get("day", 0) or 0
        rwd_apr  = (p.get("rewardApr") or {}).get("day", 0) or 0
        tot_apr  = (p.get("totalApr") or {}).get("day", 0) or (float(fee_apr) + float(rwd_apr))

        ta = p.get("tokenA") or {}
        tb = p.get("tokenB") or {}
        pools.append(PoolData(
            source        = "orca",
            name          = f"{ta.get('symbol','?')}-{tb.get('symbol','?')}",
            address       = p.get("address", ""),
            liquidity_usd = tvl,
            volume_24h    = float(vol_day),
            fee_apr       = float(fee_apr),
            total_apr     = float(tot_apr),
            token_a       = ta.get("symbol", "?"),
            token_b       = tb.get("symbol", "?"),
            current_price = float(p.get("price") or 0) or None,
        ))

    pools.sort(key=lambda x: x.total_apr, reverse=True)
    result = pools[:MAX_POOLS_PER_SOURCE]
    return _store("orca", result)


# ── Meteora ────────────────────────────────────────────────────────────────
async def fetch_meteora_pools() -> list[PoolData]:
    """
    Fetch top DLMM pairs from Meteora.
    Filters hidden pools and those below MIN_LIQUIDITY_USD.
    """
    cached = _cached("meteora")
    if cached is not None:
        return cached

    url = f"{METEORA_BASE}/pair/all"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=12)) as resp:
                if resp.status != 200:
                    logger.warning(f"Meteora pairs {resp.status}")
                    return []
                raw = await resp.json()
    except Exception as e:
        logger.error(f"Meteora fetch error: {type(e).__name__}: {e}")
        return []

    pairs = raw if isinstance(raw, list) else raw.get("data", [])
    pools: list[PoolData] = []

    for p in pairs:
        if p.get("hide"):
            continue
        liq = float(p.get("liquidity") or 0)
        if liq < MIN_LIQUIDITY_USD:
            continue

        name    = p.get("name", "?")
        parts   = name.split("-") if "-" in name else [name, "?"]
        fee_apr = float(p.get("apr") or 0)
        tot_apr = fee_apr + float(p.get("farm_apr") or 0)

        pools.append(PoolData(
            source        = "meteora",
            name          = name,
            address       = p.get("address", ""),
            liquidity_usd = liq,
            volume_24h    = float(p.get("trade_volume_24h") or 0),
            fee_apr       = fee_apr,
            total_apr     = tot_apr,
            token_a       = parts[0],
            token_b       = parts[1] if len(parts) > 1 else "?",
            current_price = float(p.get("current_price") or 0) or None,
            bin_step      = int(p.get("bin_step") or 0) or None,
        ))

    pools.sort(key=lambda x: x.total_apr, reverse=True)
    result = pools[:MAX_POOLS_PER_SOURCE]
    return _store("meteora", result)


# ── Aggregate ──────────────────────────────────────────────────────────────
async def get_pool_context(
    min_liquidity: Optional[float] = None,
    token_filter: Optional[str] = None,
) -> dict:
    """
    Fetch all three sources concurrently.
    Returns:
      {
        "raydium":  [PoolData, ...],
        "orca":     [PoolData, ...],
        "meteora":  [PoolData, ...],
        "top_by_apr": [PoolData, ...],   # cross-source top 5
        "errors":   []
      }
    Optional filters applied post-fetch:
      min_liquidity  — override global MIN_LIQUIDITY_USD for this call
      token_filter   — case-insensitive symbol substring match (e.g. "SOL")
    """
    raydium, orca, meteora = await asyncio.gather(
        fetch_raydium_pools(),
        fetch_orca_pools(),
        fetch_meteora_pools(),
        return_exceptions=True,
    )

    def safe(v) -> list[PoolData]:
        return [] if isinstance(v, Exception) else (v or [])

    ray = safe(raydium)
    orc = safe(orca)
    met = safe(meteora)

    all_pools = ray + orc + met

    if min_liquidity is not None:
        all_pools = [p for p in all_pools if p.liquidity_usd >= min_liquidity]

    if token_filter:
        q = token_filter.upper()
        all_pools = [p for p in all_pools if q in p.token_a.upper() or q in p.token_b.upper()]

    top = sorted(all_pools, key=lambda x: x.total_apr, reverse=True)[:5]

    return {
        "raydium":    ray,
        "orca":       orc,
        "meteora":    met,
        "top_by_apr": top,
    }


# ── Formatters ─────────────────────────────────────────────────────────────
def _fmt_usd(v: float) -> str:
    if v >= 1_000_000:
        return f"${v/1_000_000:.2f}M"
    if v >= 1_000:
        return f"${v/1_000:.1f}K"
    return f"${v:.2f}"


def _fmt_pool(p: PoolData) -> str:
    price_str = f" | price={p.current_price:.4f}" if p.current_price else ""
    step_str  = f" | bin={p.bin_step}" if p.bin_step else ""
    return (
        f"  [{p.source.upper():8}] {p.name:<16}"
        f"  liq={_fmt_usd(p.liquidity_usd)}"
        f"  vol24h={_fmt_usd(p.volume_24h)}"
        f"  APR={p.total_apr:.1f}% (fee={p.fee_apr:.1f}%)"
        f"{price_str}{step_str}"
    )


def format_pool_context(ctx: dict) -> str:
    """Format pool context dict as compact, LLM-readable string."""
    lines = ["=== POOL MONITOR — RAYDIUM / ORCA / METEORA ==="]

    top = ctx.get("top_by_apr", [])
    if top:
        lines.append("\nTop pools by APR (cross-source):")
        for p in top:
            lines.append(_fmt_pool(p))

    for source in ("raydium", "orca", "meteora"):
        pools = ctx.get(source, [])
        if not pools:
            lines.append(f"\n{source.capitalize()}: no data")
            continue
        lines.append(f"\n{source.capitalize()} ({len(pools)} pools, liquidity ≥ {_fmt_usd(MIN_LIQUIDITY_USD)}):")
        for p in pools:
            lines.append(_fmt_pool(p))

    return "\n".join(lines)


def format_il_alert(pool: PoolData, entry_price: float) -> str:
    """
    Format an IL alert string for a given pool + entry price.
    Returns empty string if current_price is unknown.
    """
    if not pool.current_price or not entry_price:
        return ""
    result = compute_il(entry_price, pool.current_price)
    threshold = -5.0
    flag = " ⚠️ AUTO-EXIT THRESHOLD" if result.il_pct <= -25.0 else (
           " ⚠️  IL WARNING" if result.il_pct <= threshold else ""
    )
    return (
        f"[IL] {pool.name} ({pool.source}): {result.description}"
        f"  |  APR={pool.total_apr:.1f}%  liq={_fmt_usd(pool.liquidity_usd)}{flag}"
    )
