"""
virtual_position.py — Off-chain CLMM/DLMM concentrated liquidity emulator.

Mimics Raydium CLMM / Meteora DLMM behavior in pure Python — no on-chain LP.
The bot maintains a VirtualPosition in memory and rebalances when price exits
the virtual range instead of on every ratio drift.

Range width is the #1 performance lever:
  ±0.5–1%   (1000–2000 bps): high efficiency, high rebalance frequency — use on
             tight, high-volume pools with low volatility.
  ±2–5%     (4000–10000 bps): sweet spot for most memecoins. Recommended start.
  ±10%+     (20000+ bps): near full-range CPMM behavior, fewer trades.

Keep REBALANCE_TOLERANCE < half the range width to avoid thrashing.

Math references:
  Uniswap v3 / Raydium CLMM: https://atiselsts.github.io/pdfs/uniswap-v3-liquidity-math.pdf
  Meteora DLMM bins: https://docs.meteora.ag/overview/products/dlmm/dlmm-formulas
    bin_price(id) = (1 + bin_step/10000)^id  (geometric progression)
"""

import math
import time
import logging
from dataclasses import dataclass, field
from typing import Optional

log = logging.getLogger(__name__)


@dataclass
class VirtualPosition:
    lower_price: float       # SOL per whole token — lower bound of virtual range
    upper_price: float       # SOL per whole token — upper bound
    center_price: float      # price when range was last set (for re-centering logic)
    liquidity: float         # virtual L (Uniswap v3 style, in token·sqrt-SOL units)
    strategy: str            # 'spot' | 'curve' | 'bidask'
    mode: str                # 'virtual_clmm' | 'virtual_dlmm'
    bin_step_bps: int        # DLMM only: bin step in basis points
    created_at: float = field(default_factory=time.monotonic)
    rebalance_count: int = 0

    # ── Derived helpers ───────────────────────────────────────────────────────

    @property
    def in_range(self) -> bool:
        return self.lower_price < self.center_price < self.upper_price

    @property
    def range_width_bps(self) -> float:
        """Total range width in basis points relative to center price."""
        if self.center_price <= 0:
            return 0.0
        return (self.upper_price - self.lower_price) / self.center_price * 10_000

    def range_status(self, current_price: float) -> str:
        if current_price < self.lower_price:
            pct = (self.lower_price - current_price) / self.lower_price * 100
            return f'BELOW range by {pct:.2f}%'
        if current_price > self.upper_price:
            pct = (current_price - self.upper_price) / self.upper_price * 100
            return f'ABOVE range by {pct:.2f}%'
        # in range — show position within
        pos = (current_price - self.lower_price) / (self.upper_price - self.lower_price) * 100
        return f'in-range @ {pos:.0f}% of width'


# ── Factory ───────────────────────────────────────────────────────────────────

def create_virtual_position(
    center_price: float,
    range_bps: int,
    strategy: str = 'spot',
    mode: str = 'virtual_clmm',
    bin_step_bps: int = 25,
    capital_sol: float = 1.0,
) -> VirtualPosition:
    """
    Create a symmetric virtual position centered on current price.

    capital_sol is used to size the virtual liquidity L so that virtual
    slippage estimates are realistic relative to the bot's portfolio.
    """
    half = range_bps / 2 / 10_000          # fractional half-width
    lower = center_price * (1 - half)
    upper = center_price * (1 + half)

    # Uniswap v3 liquidity L from capital:
    #   L = capital_sol / (sqrt(P_upper) - sqrt(P)) + capital_sol / (P - P_lower)
    # Simplified: use just the sqrt formulation (assumes 50/50 split at center).
    sqrt_p = math.sqrt(center_price)
    sqrt_u = math.sqrt(upper)
    sqrt_l = math.sqrt(lower)
    # L such that the SOL side = capital_sol * 0.5
    # delta_x = L * (sqrt_u - sqrt_p) / (sqrt_u * sqrt_p)
    denom = (sqrt_u - sqrt_p) / (sqrt_u * sqrt_p)
    liquidity = (capital_sol * 0.5 / denom) if denom > 0 else capital_sol * 1e6

    log.info(
        f'VirtualPosition created: center={center_price:.8f} '
        f'range=[{lower:.8f}, {upper:.8f}] ±{range_bps/2:.0f}bps '
        f'strategy={strategy} mode={mode} L={liquidity:.2f}'
    )
    return VirtualPosition(
        lower_price=lower,
        upper_price=upper,
        center_price=center_price,
        liquidity=liquidity,
        strategy=strategy,
        mode=mode,
        bin_step_bps=bin_step_bps,
    )


def recenter_position(pos: VirtualPosition, new_center: float, range_bps: int, capital_sol: float = 1.0) -> VirtualPosition:
    """Re-center the virtual position after a rebalance trade."""
    new_pos = create_virtual_position(
        center_price=new_center,
        range_bps=range_bps,
        strategy=pos.strategy,
        mode=pos.mode,
        bin_step_bps=pos.bin_step_bps,
        capital_sol=capital_sol,
    )
    new_pos.rebalance_count = pos.rebalance_count + 1
    return new_pos


# ── CLMM quote math ───────────────────────────────────────────────────────────

def simulate_clmm_quote(
    current_price: float,
    pos: VirtualPosition,
    amount_sol: float,
    is_buy: bool,
) -> dict:
    """
    Estimate output for a swap inside the virtual CLMM range.

    Uses Uniswap v3 sqrt-price math. When price is outside the range the
    position has zero active liquidity — returns a zero-edge quote.

    Returns dict with keys: amount_out_sol, effective_price, price_impact_pct,
    in_range, slippage_vs_mid_pct.
    """
    if current_price <= 0 or pos.liquidity <= 0:
        return _zero_quote(current_price, is_buy)

    in_range = pos.lower_price <= current_price <= pos.upper_price

    sqrt_p = math.sqrt(current_price)
    sqrt_l = math.sqrt(pos.lower_price)
    sqrt_u = math.sqrt(pos.upper_price)
    L = pos.liquidity

    if not in_range:
        # No active liquidity — fall back to mid-price (full slippage of the
        # underlying CPMM will apply; we just pass through the mid price here).
        return {
            'amount_out_sol': amount_sol,
            'effective_price': current_price,
            'price_impact_pct': 0.0,
            'in_range': False,
            'slippage_vs_mid_pct': 0.0,
            'note': 'out-of-range — no virtual edge',
        }

    # ── Strategy weight ──────────────────────────────────────────────────────
    # Adjusts effective L based on where in the range we are.
    # spot: flat (L is constant)
    # curve: bell curve — peaks at center, drops toward edges
    # bidask: inverse bell — more liquidity at edges (ping-pong style)
    pos_in_range = (current_price - pos.lower_price) / (pos.upper_price - pos.lower_price)
    weight = _strategy_weight(pos.strategy, pos_in_range)
    L_eff = L * weight

    if L_eff <= 0:
        return _zero_quote(current_price, is_buy)

    # Uniswap v3 swap math (single tick / single-range simplification):
    # For a buy (SOL → token): sqrt_p_new = sqrt_p + delta_sol / L
    # For a sell (token → SOL): sqrt_p_new = sqrt_p - delta_token / L  (approx)
    #
    # delta_x (SOL) = L * (sqrt_p_new - sqrt_p) / (sqrt_p_new * sqrt_p)
    # delta_y (tok) = L * (sqrt_p_new - sqrt_p)
    # Ref: Uniswap v3 whitepaper §6.1

    if is_buy:
        # SOL in → token out
        # amount_sol = L * (sqrt_p_new - sqrt_p) / (sqrt_p_new * sqrt_p)
        # Solve for sqrt_p_new: sqrt_p_new = sqrt_p * L / (L - amount_sol * sqrt_p)
        denom_v = L_eff - amount_sol * sqrt_p
        if denom_v <= 0:
            # Trade size exceeds available liquidity in range — clip to upper bound
            sqrt_p_new = sqrt_u
        else:
            sqrt_p_new = sqrt_p * L_eff / denom_v
        sqrt_p_new = min(sqrt_p_new, sqrt_u)   # cap at range boundary

        token_out_units = L_eff * (sqrt_p_new - sqrt_p)  # in sqrt-units
        # Convert: token_out_units is actually in token·sqrt-SOL, divide by price factor
        # Simplified: token_out_sol_value = amount_sol (minus slippage)
        new_price = sqrt_p_new ** 2
        effective_price = new_price   # price after swap
        price_impact = abs(new_price - current_price) / current_price * 100
        # Actual token out quantity estimation (approximate for logging)
        amount_out_sol = amount_sol * (current_price / new_price) if new_price > 0 else amount_sol
    else:
        # token in → SOL out
        # token_in causes price to decrease
        # delta_y = L * (sqrt_p - sqrt_p_new)  → sqrt_p_new = sqrt_p - delta_y / L
        delta_y = amount_sol  # treat SOL-equivalent amount as proxy for token value
        sqrt_p_new = sqrt_p - delta_y / L_eff
        sqrt_p_new = max(sqrt_p_new, sqrt_l)   # cap at lower bound

        new_price = sqrt_p_new ** 2
        effective_price = new_price
        price_impact = abs(current_price - new_price) / current_price * 100
        amount_out_sol = amount_sol * (new_price / current_price) if current_price > 0 else amount_sol

    slippage_vs_mid = abs(effective_price - current_price) / current_price * 100

    return {
        'amount_out_sol': max(0.0, amount_out_sol),
        'effective_price': effective_price,
        'price_impact_pct': price_impact,
        'in_range': True,
        'slippage_vs_mid_pct': slippage_vs_mid,
        'strategy_weight': weight,
        'note': f'{pos.strategy} strategy, weight={weight:.2f}',
    }


# ── DLMM bin helpers ──────────────────────────────────────────────────────────

def dlmm_bin_id(price: float, bin_step_bps: int, base_price: float = 1.0) -> int:
    """
    Compute the active bin ID for a given price.

    Meteora DLMM formula: price(id) = base_price * (1 + bin_step/10000)^id
    → id = log(price / base_price) / log(1 + bin_step/10000)
    """
    if price <= 0 or base_price <= 0:
        return 0
    step = bin_step_bps / 10_000
    if step <= 0:
        return 0
    return int(math.log(price / base_price) / math.log(1 + step))


def dlmm_bin_price(bin_id: int, bin_step_bps: int, base_price: float = 1.0) -> float:
    """Price at the lower edge of a given DLMM bin."""
    step = bin_step_bps / 10_000
    return base_price * (1 + step) ** bin_id


def dlmm_range(center_price: float, range_bps: int, bin_step_bps: int) -> tuple[int, int, int]:
    """
    Return (active_bin, lower_bin, upper_bin) for a DLMM-style virtual position.
    """
    half = range_bps / 2 / 10_000
    lower_price = center_price * (1 - half)
    upper_price = center_price * (1 + half)
    active = dlmm_bin_id(center_price, bin_step_bps, base_price=center_price)
    lower  = dlmm_bin_id(lower_price,  bin_step_bps, base_price=center_price)
    upper  = dlmm_bin_id(upper_price,  bin_step_bps, base_price=center_price)
    return active, lower, upper


# ── Internal helpers ──────────────────────────────────────────────────────────

def _strategy_weight(strategy: str, pos_in_range: float) -> float:
    """
    Liquidity weight at a given position within the range (0 = lower edge, 1 = upper).

    spot:   flat 1.0 everywhere (even distribution, like basic DLMM Spot).
    curve:  bell curve peaking at 0.5 (center-concentrated, like Raydium CLMM or
            HawkFi Precision). Weight = 1 - 4*(pos-0.5)^2 → 0..1
    bidask: more weight at edges (0 or 1), less in center. Ping-Pong style.
            Weight = 4*(pos-0.5)^2 → 0..1 then normalized.
    """
    if strategy == 'curve':
        return max(0.01, 1.0 - 4 * (pos_in_range - 0.5) ** 2)
    if strategy == 'bidask':
        return max(0.01, 4 * (pos_in_range - 0.5) ** 2)
    return 1.0  # spot


def _zero_quote(current_price: float, is_buy: bool) -> dict:
    return {
        'amount_out_sol': 0.0,
        'effective_price': current_price,
        'price_impact_pct': 0.0,
        'in_range': False,
        'slippage_vs_mid_pct': 0.0,
        'note': 'zero liquidity',
    }
