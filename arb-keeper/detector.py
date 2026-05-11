"""
detector.py — arb opportunity detection and profit estimation.

Takes a PriceSnapshot and available balances, returns an ArbOpportunity
if the expected net profit clears the minimum threshold after Jito tip.
"""

import logging
from dataclasses import dataclass, field
import time
from typing import Optional

import config
from price_feed import PriceSnapshot

log = logging.getLogger(__name__)


@dataclass
class ArbOpportunity:
    # Leg 1: buy TOKEN with SOL
    buy_sol_lamports: int      # SOL to spend
    expected_tokens: int       # minimum tokens to receive (with slippage)
    buy_quote: dict            # full Jupiter quote for tx building

    # Leg 2: sell TOKEN for SOL
    sell_tokens: int           # tokens to sell (= expected_tokens)
    expected_sol_lamports: int # minimum SOL to receive (with slippage)
    sell_quote: dict

    # Economics
    gross_profit_lamports: int # sell_out - buy_in (before tip)
    jito_tip_lamports: int
    net_profit_sol: float      # after tip

    # Route info for logging
    buy_route_summary: str
    sell_route_summary: str
    snapshot_at: float = field(default_factory=time.monotonic)  # quote capture time

    def describe(self) -> str:
        return (
            f'Arb: spend {self.buy_sol_lamports/1e9:.5f} SOL → '
            f'{self.expected_tokens/1e6:.2f} tok → '
            f'{self.expected_sol_lamports/1e9:.5f} SOL | '
            f'net +{self.net_profit_sol*1000:.4f} mSOL'
        )


def _route_summary(quote: dict) -> str:
    """Extract a short human-readable route string from a Jupiter quote."""
    plans = quote.get('routePlan', [])
    labels = []
    for step in plans[:3]:
        swap = step.get('swapInfo', {})
        label = swap.get('label') or swap.get('ammKey', '')[:8]
        labels.append(label)
    return ' → '.join(labels) if labels else 'unknown'


def find_opportunity(
    snapshot: PriceSnapshot,
    sol_balance: float,
) -> Optional[ArbOpportunity]:
    """
    Determine if a profitable arb exists given the current price snapshot.

    Logic:
    - We buy TOKEN with X SOL, get Y tokens
    - We sell Y tokens for Z SOL
    - Profit = Z - X - jito_tip
    - Size trade to probe ratio, capped at MAX_TRADE_SOL and 50% of balance
    """
    # Calculate what fraction of probe shows profit
    probe_in  = snapshot.probe_sol_lamports
    probe_out = snapshot.sell_out_lamports  # SOL back after round-trip on probe

    # Gross profit on probe trade
    gross_probe = probe_out - probe_in
    if gross_probe <= 0:
        log.debug(f'No arb: round-trip loss {gross_probe/1e9:.6f} SOL (spread {snapshot.spread_pct:.4f}%)')
        return None

    # Scale trade size: keep same ratio as probe, capped at MAX_TRADE_SOL and 50% balance
    max_by_balance = sol_balance * 0.5
    trade_sol = min(config.MAX_TRADE_SOL, max_by_balance)
    trade_lamports = int(trade_sol * config.SOL_LAMPORTS)

    if trade_lamports < probe_in:
        # Smaller than probe — scale linearly
        scale = trade_lamports / probe_in
    else:
        # Larger than probe — use probe ratio (don't extrapolate; price impact grows)
        scale = 1.0
        trade_lamports = probe_in  # stay at probe size if we can't trust scaling

    # Estimate gross profit at trade size
    gross_est_lamports = int(gross_probe * scale)

    # Dynamic tip: 40% of gross, floored at config minimum.
    # More competitive on large spreads; cheaper on thin ones.
    dynamic_tip = max(config.JITO_TIP_LAMPORTS, int(gross_est_lamports * 0.40))
    net_profit_sol = (gross_est_lamports - dynamic_tip) / config.SOL_LAMPORTS

    if net_profit_sol < config.MIN_PROFIT_SOL:
        log.debug(
            f'Below threshold: est net {net_profit_sol*1000:.4f} mSOL '
            f'(gross {gross_est_lamports/1e9:.6f} - tip {config.JITO_TIP_LAMPORTS/1e9:.6f})'
        )
        return None

    # Use the probe quotes directly (trade at probe size for safety in Phase 1→2)
    expected_tokens = snapshot.probe_tokens
    expected_sol_back = snapshot.sell_out_lamports  # otherAmountThreshold already applies slippage

    opp = ArbOpportunity(
        buy_sol_lamports=probe_in,
        expected_tokens=expected_tokens,
        buy_quote=snapshot.buy_quote,
        sell_tokens=expected_tokens,
        expected_sol_lamports=expected_sol_back,
        sell_quote=snapshot.sell_quote,
        gross_profit_lamports=gross_probe,
        jito_tip_lamports=dynamic_tip,
        net_profit_sol=net_profit_sol,
        buy_route_summary=_route_summary(snapshot.buy_quote),
        sell_route_summary=_route_summary(snapshot.sell_quote),
        snapshot_at=snapshot.captured_at,
    )

    log.info(f'Opportunity found: {opp.describe()}')
    log.info(f'  Buy route:  {opp.buy_route_summary}')
    log.info(f'  Sell route: {opp.sell_route_summary}')
    return opp
