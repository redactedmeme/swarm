"""
price_feed.py — Jupiter v6 quote polling.

Probes the market with a small amount to discover the best executable
buy price (SOL→TOKEN) and sell price (TOKEN→SOL) across all Jupiter routes.
Jupiter aggregates all 30+ pools automatically.
"""

import asyncio
import logging
from dataclasses import dataclass
from typing import Optional

import httpx

import config

log = logging.getLogger(__name__)


@dataclass
class PriceSnapshot:
    # Buy side: how many tokens we get for probe_sol
    buy_out_tokens: int        # raw token units out
    buy_price_impact: float    # % price impact
    buy_quote: dict            # full Jupiter quote response (for tx building)

    # Sell side: how many lamports we get for selling probe_tokens
    sell_out_lamports: int     # raw lamports out
    sell_price_impact: float
    sell_quote: dict

    # Derived
    probe_sol_lamports: int    # what we put in on buy side
    probe_tokens: int          # what we put in on sell side

    @property
    def buy_price_sol_per_token(self) -> float:
        """Effective SOL cost per token unit (in whole SOL)."""
        if self.buy_out_tokens == 0:
            return float('inf')
        return (self.probe_sol_lamports / config.SOL_LAMPORTS) / (self.buy_out_tokens / 1e6)

    @property
    def sell_price_sol_per_token(self) -> float:
        """Effective SOL received per token unit (in whole SOL)."""
        if self.probe_tokens == 0:
            return 0.0
        return (self.sell_out_lamports / config.SOL_LAMPORTS) / (self.probe_tokens / 1e6)

    @property
    def spread_pct(self) -> float:
        """(sell - buy) / buy * 100 — positive means profitable arb exists."""
        b = self.buy_price_sol_per_token
        s = self.sell_price_sol_per_token
        if b == 0 or b == float('inf'):
            return 0.0
        return (s - b) / b * 100


async def _get_quote(
    client: httpx.AsyncClient,
    input_mint: str,
    output_mint: str,
    amount: int,
    slippage_bps: int = config.SLIPPAGE_BPS,
) -> Optional[dict]:
    """Single Jupiter quote request. Returns None on failure."""
    params = {
        'inputMint':    input_mint,
        'outputMint':   output_mint,
        'amount':       str(amount),
        'slippageBps':  str(slippage_bps),
        'onlyDirectRoutes': 'false',  # allow multi-hop for best price
    }
    try:
        resp = await client.get(config.JUPITER_QUOTE, params=params, timeout=8)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        log.warning(f'Jupiter quote failed ({input_mint[:8]}→{output_mint[:8]}): {e}')
        return None


async def get_price_snapshot(probe_sol: float = config.PROBE_SOL) -> Optional[PriceSnapshot]:
    """
    Fetch buy + sell quotes concurrently.
    probe_sol: SOL amount used on buy side to size the quote.
    Sell side uses the expected token output as its input (round-trip sizing).
    """
    probe_lamports = int(probe_sol * config.SOL_LAMPORTS)

    async with httpx.AsyncClient() as client:
        # First: get buy quote to know how many tokens we'd receive
        buy_quote = await _get_quote(
            client,
            input_mint=config.SOL_MINT,
            output_mint=config.TOKEN_MINT,
            amount=probe_lamports,
        )
        if not buy_quote:
            return None

        probe_tokens = int(buy_quote.get('outAmount', 0))
        if probe_tokens == 0:
            return None

        # Second: get sell quote using the expected token output as input
        sell_quote = await _get_quote(
            client,
            input_mint=config.TOKEN_MINT,
            output_mint=config.SOL_MINT,
            amount=probe_tokens,
        )
        if not sell_quote:
            return None

    buy_impact  = float(buy_quote.get('priceImpactPct', 0))
    sell_impact = float(sell_quote.get('priceImpactPct', 0))
    sell_out    = int(sell_quote.get('outAmount', 0))

    snap = PriceSnapshot(
        buy_out_tokens=probe_tokens,
        buy_price_impact=buy_impact,
        buy_quote=buy_quote,
        sell_out_lamports=sell_out,
        sell_price_impact=sell_impact,
        sell_quote=sell_quote,
        probe_sol_lamports=probe_lamports,
        probe_tokens=probe_tokens,
    )

    log.debug(
        f'Snapshot: buy={snap.buy_price_sol_per_token:.8f} SOL/tok '
        f'sell={snap.sell_price_sol_per_token:.8f} SOL/tok '
        f'spread={snap.spread_pct:.3f}%'
    )
    return snap
