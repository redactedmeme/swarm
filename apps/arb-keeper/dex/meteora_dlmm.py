"""
meteora_dlmm.py — Meteora DLMM price discovery.

Fetches mid-price from the Meteora DLMM pool via DexScreener. Used only for
cross-pool price comparison — execution is routed through Jupiter which handles
the DLMM swap instructions.
"""

import logging
import time
import requests
from dataclasses import dataclass, field
from typing import Optional

import config

log = logging.getLogger(__name__)

SOL_MINT = 'So11111111111111111111111111111111111111112'


@dataclass
class MeteoraSnapshot:
    mid_price_sol_per_token: float
    volume_1h_usd: float
    volume_5m_usd: float
    pool_address: str
    captured_at: float = field(default_factory=time.monotonic)

    def age_seconds(self) -> float:
        return time.monotonic() - self.captured_at


_cache: Optional[MeteoraSnapshot] = None
_last_fetch: float = 0.0


def get_meteora_snapshot(pool_address: str = config.METEORA_POOL_ID) -> Optional[MeteoraSnapshot]:
    """
    Return Meteora DLMM mid-price via DexScreener.
    Caches for VOLUME_UPDATE_INTERVAL seconds to avoid hammering the API.
    """
    global _cache, _last_fetch

    now = time.monotonic()
    if _cache and (now - _last_fetch) < config.VOLUME_UPDATE_INTERVAL:
        return _cache

    try:
        url = f"https://api.dexscreener.com/latest/dex/pairs/solana/{pool_address}"
        resp = requests.get(url, timeout=5)
        resp.raise_for_status()
        data = resp.json()

        if not data.get('pairs'):
            log.warning(f'[Meteora] No pair data for {pool_address[:8]}…')
            return _cache  # return stale rather than None

        pair = data['pairs'][0]
        price_native = float(pair.get('priceNative') or 0)

        # DexScreener shows price of baseToken in quoteToken units.
        # If TOKEN is base: priceNative = SOL per TOKEN (what we want).
        # If SOL is base:   priceNative = TOKEN per SOL (need to invert).
        base_addr = pair.get('baseToken', {}).get('address', '')
        if base_addr.lower() == SOL_MINT.lower():
            # SOL is base → priceNative = TOKEN per SOL → invert
            price_sol_per_token = 1.0 / price_native if price_native > 0 else 0.0
        else:
            price_sol_per_token = price_native

        volume = pair.get('volume', {})
        snap = MeteoraSnapshot(
            mid_price_sol_per_token=price_sol_per_token,
            volume_1h_usd=float(volume.get('h1') or 0),
            volume_5m_usd=float(volume.get('m5') or 0),
            pool_address=pool_address,
        )
        _cache = snap
        _last_fetch = now

        log.debug(
            f'[Meteora] price={price_sol_per_token:.8f} SOL/tok  '
            f'1h_vol=${snap.volume_1h_usd:.0f}  '
            f'pool={pool_address[:8]}…'
        )
        return snap

    except Exception as e:
        log.warning(f'[Meteora] DexScreener fetch failed: {e}')
        return _cache  # return stale cache rather than None
