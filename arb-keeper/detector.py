"""
detector.py — Rebalancing detector supporting two strategy modes:

  inventory (default / backward-compat):
    Classic Uniswap v2 / CPMM full-range logic. Rebalance when the portfolio
    ratio (SOL vs TOKEN by value) drifts beyond REBALANCE_TOLERANCE.

  virtual_clmm / virtual_dlmm:
    Off-chain concentrated liquidity emulation (Raydium CLMM / Meteora DLMM
    style). The bot tracks a VirtualPosition in memory. Rebalances are
    triggered primarily when price exits the virtual range, not on every ratio
    drift. Inside the range, smaller ratio drift thresholds apply.

Select the mode with STRATEGY_MODE env var (default: inventory).
"""

import logging
from dataclasses import dataclass, field
import time
from typing import Optional

import config
from price_feed import PriceSnapshot
from virtual_position import (
    VirtualPosition,
    create_virtual_position,
    recenter_position,
    simulate_clmm_quote,
)
from volume_feed import VolumeFeed

log = logging.getLogger(__name__)

# Module-level virtual position state (one position per process).
# Re-created / re-centered after each rebalance trade.
_virtual_pos: Optional[VirtualPosition] = None

# Module-level volume feed (initialized on first call).
_volume_feed: Optional[VolumeFeed] = None
_last_volume_capture_time: float = 0.0


@dataclass
class RebalanceOrder:
    """A single-leg rebalance trade."""
    is_buy_token: bool          # True = spend SOL to buy TOKEN; False = sell TOKEN for SOL
    sol_amount: float           # SOL value of the trade (positive)
    sol_lamports: int           # lamports to spend (buy) or receive estimate (sell)
    token_amount: int           # raw token units to buy or sell

    # Portfolio snapshot at decision time
    sol_balance: float
    token_balance_raw: int
    total_value_sol: float
    current_ratio: float        # actual token fraction by value
    target_ratio: float         # config.TARGET_RATIO
    deviation: float            # |current_ratio - target_ratio|

    # Price info
    price_sol_per_token: float  # mid-price used for valuation
    pool: object                # CpmmPool (for tx building)
    snapshot_at: float = field(default_factory=time.monotonic)

    # Kept for executor/logger compatibility
    buy_quote: dict = field(default_factory=dict)
    sell_quote: dict = field(default_factory=dict)

    # Trade source (for logging)
    trade_source: str = 'rebalance'  # 'rebalance' or 'volume_capture'

    def describe(self) -> str:
        direction = 'BUY TOKEN' if self.is_buy_token else 'SELL TOKEN'
        source_tag = f'[{self.trade_source.upper()}]' if self.trade_source != 'rebalance' else ''
        return (
            f'{source_tag} {direction}: {self.sol_amount*1000:.3f} mSOL equiv | '
            f'ratio {self.current_ratio*100:.1f}% → {self.target_ratio*100:.1f}% '
            f'(Δ={self.deviation*100:.2f}%)'
        )


def compute_rebalance_delta(
    sol_bal: float,
    token_bal_raw: int,
    price_sol_per_token: float,
    target_ratio: float = config.TARGET_RATIO,
) -> tuple[float, float, bool]:
    """
    Compute the rebalance trade size using Uniswap v2 inventory logic.

    Returns (delta_sol, current_ratio, is_buy_token):
      delta_sol      — SOL value to trade (always positive)
      current_ratio  — current token fraction of total portfolio by value
      is_buy_token   — True if we need to buy token (token underweight)
    """
    token_decimals = config.TOKEN_DECIMALS
    token_bal_whole = token_bal_raw / 10**token_decimals
    token_value_sol = token_bal_whole * price_sol_per_token
    total_value_sol = sol_bal + token_value_sol

    if total_value_sol <= 0:
        return 0.0, 0.0, True

    current_ratio = token_value_sol / total_value_sol
    target_token_value_sol = total_value_sol * target_ratio
    delta_token_value_sol  = abs(target_token_value_sol - token_value_sol)
    is_buy_token = token_value_sol < target_token_value_sol

    return delta_token_value_sol, current_ratio, is_buy_token


def calculate_volume_capture_size(
    recent_volume_1h_usd: float,
    target_share: float = config.TARGET_VOLUME_SHARE,
    sol_price_usd: float = 200.0,  # default SOL/USD estimate
) -> float:
    """
    Calculate appropriate trade size based on market volume.

    Takes 1h volume and target share percentage, returns SOL amount to trade.
    Formula: (1h_volume_usd * target_share * 0.15) / sol_price_usd
    The 0.15 factor means we capture 15% of target_share per 6-second polling interval.

    Returns SOL amount to trade (clamped to MIN_TRADE_SOL .. MAX_TRADE_SOL).
    """
    if recent_volume_1h_usd <= 0:
        return 0.0

    # Scale target_share to match 6-second polling (3600s / 6s = 600 intervals/hour)
    # To capture 22% per hour, we take ~0.03% per interval (0.22 / 600 ≈ 0.0003)
    # But we use a 0.15 factor as conservative estimate of our actual capture per trade
    per_interval_usd = (recent_volume_1h_usd * target_share * 0.15) / 600.0

    # Convert USD to SOL
    trade_sol = per_interval_usd / sol_price_usd

    # Clamp to config limits
    trade_sol = max(config.MIN_TRADE_SOL, min(config.MAX_TRADE_SOL, trade_sol))

    return trade_sol


def find_opportunity(
    snapshot: PriceSnapshot,
    sol_balance: float,
    token_balance_raw: int = 0,
) -> Optional[RebalanceOrder]:
    """Dispatch to the correct strategy based on STRATEGY_MODE."""
    if config.STRATEGY_MODE in ('virtual_clmm', 'virtual_dlmm'):
        return _find_opportunity_virtual(snapshot, sol_balance, token_balance_raw)
    return _find_opportunity_inventory(snapshot, sol_balance, token_balance_raw)


def _find_opportunity_inventory(
    snapshot: PriceSnapshot,
    sol_balance: float,
    token_balance_raw: int = 0,
) -> Optional[RebalanceOrder]:
    """
    Return a RebalanceOrder if the portfolio has drifted beyond REBALANCE_TOLERANCE.
    Returns None if within tolerance or if the computed trade is too small.
    """
    price = snapshot.mid_price_sol_per_token
    if price <= 0:
        log.debug('Price is zero — skipping')
        return None

    delta_sol, current_ratio, is_buy_token = compute_rebalance_delta(
        sol_balance, token_balance_raw, price,
    )

    token_bal_whole  = token_balance_raw / 10**config.TOKEN_DECIMALS
    token_value_sol  = token_bal_whole * price
    total_value_sol  = sol_balance + token_value_sol
    deviation        = abs(current_ratio - config.TARGET_RATIO)

    log.debug(
        f'Portfolio: {sol_balance:.4f} SOL + {token_bal_whole:.2f} tok '
        f'(={token_value_sol:.4f} SOL) = {total_value_sol:.4f} SOL total | '
        f'ratio={current_ratio*100:.1f}% target={config.TARGET_RATIO*100:.0f}% '
        f'dev={deviation*100:.2f}%'
    )

    if deviation < config.REBALANCE_TOLERANCE:
        log.debug(f'Within tolerance ({deviation*100:.2f}% < {config.REBALANCE_TOLERANCE*100:.0f}%) — no trade')
        return None

    # For buys, cap at 50% of SOL balance (need SOL to spend). Sells don't need SOL.
    if is_buy_token:
        trade_sol = min(delta_sol, config.MAX_TRADE_SOL, sol_balance * 0.5)
    else:
        trade_sol = min(delta_sol, config.MAX_TRADE_SOL)

    if trade_sol < config.MIN_TRADE_SOL:
        log.debug(f'Trade too small: {trade_sol*1000:.3f} mSOL < {config.MIN_TRADE_SOL*1000:.0f} mSOL minimum')
        return None

    if is_buy_token:
        # Spend SOL to buy TOKEN
        sol_lamports = int(trade_sol * config.SOL_LAMPORTS)
        from dex.raydium_cpmm import quote_swap_base_input, WSOL_MINT
        token_out, _ = quote_swap_base_input(snapshot.pool, WSOL_MINT, sol_lamports)
        token_amount = token_out
    else:
        # Sell TOKEN for SOL — compute raw token amount equivalent to trade_sol
        token_amount = int((trade_sol / price) * 10**config.TOKEN_DECIMALS)
        # Cap at available balance
        token_amount = min(token_amount, token_balance_raw)
        trade_sol = (token_amount / 10**config.TOKEN_DECIMALS) * price
        sol_lamports = int(trade_sol * config.SOL_LAMPORTS)

    if token_amount <= 0:
        log.debug('Token amount rounds to zero — skipping')
        return None

    order = RebalanceOrder(
        is_buy_token=is_buy_token,
        sol_amount=trade_sol,
        sol_lamports=sol_lamports,
        token_amount=token_amount,
        sol_balance=sol_balance,
        token_balance_raw=token_balance_raw,
        total_value_sol=total_value_sol,
        current_ratio=current_ratio,
        target_ratio=config.TARGET_RATIO,
        deviation=deviation,
        price_sol_per_token=price,
        pool=snapshot.pool,
    )

    log.info(f'Rebalance needed: {order.describe()}')
    log.info(
        f'  Price: {price:.8f} SOL/tok | '
        f'Trade: {trade_sol*1000:.3f} mSOL worth | '
        f'Tokens: {token_amount/10**config.TOKEN_DECIMALS:.4f}'
    )
    return order


def _find_opportunity_virtual(
    snapshot: PriceSnapshot,
    sol_balance: float,
    token_balance_raw: int = 0,
) -> Optional[RebalanceOrder]:
    """
    Virtual CLMM/DLMM strategy:
      1. Ensure a VirtualPosition exists (create on first call).
      2. Check if current price is inside or outside the virtual range.
      3. OUT-OF-RANGE → strong rebalance signal (re-center trade required).
      4. IN-RANGE → only rebalance if ratio drift exceeds a tighter threshold
         (half of REBALANCE_TOLERANCE, since the range already caps our exposure).
    """
    global _virtual_pos

    price = snapshot.mid_price_sol_per_token
    if price <= 0:
        log.debug('Price is zero — skipping')
        return None

    total_sol = sol_balance + (token_balance_raw / 10**config.TOKEN_DECIMALS) * price

    # ── Initialise virtual position on first call ────────────────────────────
    if _virtual_pos is None:
        _virtual_pos = create_virtual_position(
            center_price=price,
            range_bps=config.VIRTUAL_RANGE_BPS,
            strategy=config.VIRTUAL_STRATEGY,
            mode=config.STRATEGY_MODE,
            bin_step_bps=config.VIRTUAL_BIN_STEP_BPS,
            capital_sol=total_sol,
        )

    pos = _virtual_pos
    in_range = pos.lower_price <= price <= pos.upper_price
    range_status = pos.range_status(price)

    # ── Virtual quote (for logging / future fee simulation) ──────────────────
    vq = simulate_clmm_quote(price, pos, config.PROBE_SOL, is_buy=True)

    log.info(
        f'[{config.STRATEGY_MODE.upper()}] {range_status} | '
        f'range=[{pos.lower_price:.8f}, {pos.upper_price:.8f}] '
        f'slippage={vq["slippage_vs_mid_pct"]:.4f}%'
    )

    # Compute ratio deviation (same as inventory path)
    token_bal_whole = token_balance_raw / 10**config.TOKEN_DECIMALS
    token_value_sol = token_bal_whole * price
    total_value_sol = sol_balance + token_value_sol
    if total_value_sol <= 0:
        return None
    current_ratio = token_value_sol / total_value_sol
    deviation = abs(current_ratio - config.TARGET_RATIO)

    # ── Decision logic: REBALANCE vs VOLUME CAPTURE ──────────────────────────
    should_rebalance = False

    if not in_range:
        should_rebalance = True
        log.info(
            f'[{config.STRATEGY_MODE.upper()}] Price {range_status} — '
            f'rebalance to recenter virtual position'
        )
    else:
        # Inside range — only rebalance if ratio has drifted significantly.
        # Use half the normal tolerance (range keeps us tighter).
        inner_tol = config.REBALANCE_TOLERANCE * 0.5
        if deviation >= inner_tol:
            should_rebalance = True
            log.info(
                f'[{config.STRATEGY_MODE.upper()}] In-range but ratio drift {deviation*100:.2f}% '
                f'exceeds inner tolerance {inner_tol*100:.2f}% — rebalancing'
            )

    if should_rebalance:
        # ── Build rebalance order ──────────────────────────────────────────────
        delta_sol, _, is_buy_token = compute_rebalance_delta(sol_balance, token_balance_raw, price)

        if is_buy_token:
            trade_sol = min(delta_sol, config.MAX_TRADE_SOL, sol_balance * 0.5)
        else:
            trade_sol = min(delta_sol, config.MAX_TRADE_SOL)

        if trade_sol < config.MIN_TRADE_SOL:
            log.debug(f'Trade too small: {trade_sol*1000:.3f} mSOL — skipping')
            return None

        if is_buy_token:
            sol_lamports = int(trade_sol * config.SOL_LAMPORTS)
            from dex.raydium_cpmm import quote_swap_base_input, WSOL_MINT
            token_out, _ = quote_swap_base_input(snapshot.pool, WSOL_MINT, sol_lamports)
            token_amount = token_out
        else:
            token_amount = int((trade_sol / price) * 10**config.TOKEN_DECIMALS)
            token_amount = min(token_amount, token_balance_raw)
            trade_sol = (token_amount / 10**config.TOKEN_DECIMALS) * price
            sol_lamports = int(trade_sol * config.SOL_LAMPORTS)

        if token_amount <= 0:
            return None

        order = RebalanceOrder(
            is_buy_token=is_buy_token,
            sol_amount=trade_sol,
            sol_lamports=sol_lamports,
            token_amount=token_amount,
            sol_balance=sol_balance,
            token_balance_raw=token_balance_raw,
            total_value_sol=total_value_sol,
            current_ratio=current_ratio,
            target_ratio=config.TARGET_RATIO,
            deviation=deviation,
            price_sol_per_token=price,
            pool=snapshot.pool,
            trade_source='rebalance',
        )

        log.info(
            f'[{config.STRATEGY_MODE.upper()}] {order.describe()} | '
            f'virtual_range=[{pos.lower_price:.8f}, {pos.upper_price:.8f}] '
            f'virtual_slippage={vq["slippage_vs_mid_pct"]:.4f}%'
        )
        return order

    else:
        # ── No rebalance needed. Check for VOLUME CAPTURE opportunity ─────────
        return _try_volume_capture_order(
            snapshot, sol_balance, token_balance_raw, price, current_ratio, total_value_sol
        )


def _try_volume_capture_order(
    snapshot: PriceSnapshot,
    sol_balance: float,
    token_balance_raw: int,
    price: float,
    current_ratio: float,
    total_value_sol: float,
) -> Optional[RebalanceOrder]:
    """
    Attempt to create a volume-capture trade when no rebalance is needed.

    Checks volume feed and portfolio imbalance to decide if a proactive trade is warranted.
    Returns None if conditions aren't met.
    """
    global _volume_feed, _last_volume_capture_time

    # Initialize volume feed on first call
    if _volume_feed is None:
        _volume_feed = VolumeFeed(config.RAYDIUM_POOL_ID, polling_interval=config.VOLUME_UPDATE_INTERVAL)

    # Try to update volume data
    _volume_feed.update()

    vol_1h = _volume_feed.get_volume_rate_1h()
    if vol_1h < config.VOLUME_THRESHOLD_USD:
        log.debug(f'Volume too low: ${vol_1h:.0f} < ${config.VOLUME_THRESHOLD_USD:.0f} threshold')
        return None

    # Check cooldown: don't execute volume-capture trades too frequently
    now = time.monotonic()
    if now - _last_volume_capture_time < config.VOLUME_TRADE_COOLDOWN:
        log.debug(
            f'Volume capture cooldown: {config.VOLUME_TRADE_COOLDOWN - (now - _last_volume_capture_time):.1f}s remaining'
        )
        return None

    # Portfolio imbalance check: allow volume-capture only if ratio is close to target
    # (not already heavily skewed in one direction)
    max_vol_capture_deviation = config.REBALANCE_TOLERANCE * 2  # Wider tolerance for vol-capture trades
    deviation = abs(current_ratio - config.TARGET_RATIO)
    if deviation > max_vol_capture_deviation:
        log.debug(
            f'Portfolio too imbalanced for volume capture: ratio={current_ratio*100:.2f}% '
            f'deviation={deviation*100:.2f}% > {max_vol_capture_deviation*100:.2f}%'
        )
        return None

    # Calculate trade size based on market volume
    is_buy_token = determine_volume_capture_direction(sol_balance, token_balance_raw, price)

    # Use current price as SOL/USD estimate (simplified; could improve with feed)
    sol_price_usd_est = 200.0  # Fallback; DexScreener has this info too
    trade_sol = calculate_volume_capture_size(vol_1h, target_share=config.TARGET_VOLUME_SHARE, sol_price_usd=sol_price_usd_est)

    if trade_sol < config.MIN_TRADE_SOL:
        log.debug(f'Volume-capture trade too small: {trade_sol*1000:.3f} mSOL < {config.MIN_TRADE_SOL*1000:.0f} mSOL')
        return None

    # Build the order
    if is_buy_token:
        # Spend SOL to buy TOKEN
        sol_lamports = int(trade_sol * config.SOL_LAMPORTS)
        from dex.raydium_cpmm import quote_swap_base_input, WSOL_MINT
        token_out, _ = quote_swap_base_input(snapshot.pool, WSOL_MINT, sol_lamports)
        token_amount = token_out

        if token_amount <= 0:
            log.debug('Buy quote returned zero tokens')
            return None
    else:
        # Sell TOKEN for SOL
        token_amount = int((trade_sol / price) * 10**config.TOKEN_DECIMALS)
        token_amount = min(token_amount, token_balance_raw)
        if token_amount <= 0:
            log.debug('Sell amount would be zero or we have no tokens')
            return None
        trade_sol = (token_amount / 10**config.TOKEN_DECIMALS) * price
        sol_lamports = int(trade_sol * config.SOL_LAMPORTS)

    order = RebalanceOrder(
        is_buy_token=is_buy_token,
        sol_amount=trade_sol,
        sol_lamports=sol_lamports,
        token_amount=token_amount,
        sol_balance=sol_balance,
        token_balance_raw=token_balance_raw,
        total_value_sol=total_value_sol,
        current_ratio=current_ratio,
        target_ratio=config.TARGET_RATIO,
        deviation=deviation,
        price_sol_per_token=price,
        pool=snapshot.pool,
        trade_source='volume_capture',
    )

    _last_volume_capture_time = now
    log.info(
        f'[VOLUME-CAPTURE] {order.describe()} | '
        f'1h_volume=${vol_1h:.0f} target_share={config.TARGET_VOLUME_SHARE*100:.1f}%'
    )
    return order


def determine_volume_capture_direction(
    sol_balance: float,
    token_balance_raw: int,
    price_sol_per_token: float,
) -> bool:
    """
    Determine whether a volume-capture trade should be a BUY or SELL.

    Returns True (buy token) if underweight, False (sell token) if overweight.
    Uses the target ratio to decide direction.
    """
    token_bal_whole = token_balance_raw / 10**config.TOKEN_DECIMALS
    token_value_sol = token_bal_whole * price_sol_per_token
    total_value_sol = sol_balance + token_value_sol

    if total_value_sol <= 0:
        return True  # Default to buy

    current_ratio = token_value_sol / total_value_sol
    return current_ratio < config.TARGET_RATIO  # Buy if underweight


def notify_trade_executed(new_price: float, total_sol: float) -> None:
    """
    Call this after a rebalance trade lands to re-center the virtual position.
    No-op in inventory mode.
    """
    global _virtual_pos
    if config.STRATEGY_MODE not in ('virtual_clmm', 'virtual_dlmm'):
        return
    if not config.REBALANCE_ON_RANGE_EXIT:
        return
    if _virtual_pos is None:
        return
    old_count = _virtual_pos.rebalance_count
    _virtual_pos = recenter_position(_virtual_pos, new_price, config.VIRTUAL_RANGE_BPS, capital_sol=total_sol)
    log.info(
        f'[{config.STRATEGY_MODE.upper()}] Virtual position re-centered at {new_price:.8f} '
        f'(rebalance #{old_count + 1}) '
        f'new range=[{_virtual_pos.lower_price:.8f}, {_virtual_pos.upper_price:.8f}]'
    )


# Alias so main.py / logger.py / executor.py that reference ArbOpportunity still work
ArbOpportunity = RebalanceOrder


def _route_summary(quote: dict) -> str:
    plans = quote.get('routePlan', [])
    labels = []
    for step in plans[:3]:
        swap = step.get('swapInfo', {})
        label = swap.get('label') or swap.get('ammKey', '')[:8]
        labels.append(label)
    return ' → '.join(labels) if labels else 'Raydium CPMM'
