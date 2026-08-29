"""
price_feed.py — Direct Raydium CPMM price discovery.

Reads the pool state on-chain and computes buy/sell quotes locally using the
constant-product formula. No Jupiter dependency for price discovery.
"""

import logging
import time
from dataclasses import dataclass, field
from typing import Optional

import config
from dex.raydium_cpmm import fetch_pool, quote_swap_base_input, CpmmPool, WSOL_MINT

log = logging.getLogger(__name__)


@dataclass
class PriceSnapshot:
    pool: CpmmPool             # raw pool state (for tx building)

    # Quote for probe_sol_lamports SOL → TOKEN
    probe_sol_lamports: int
    probe_tokens: int          # expected token out for probe
    buy_price_impact: float    # approximate, based on pool depth

    # Quote for probe_tokens TOKEN → SOL
    sell_out_lamports: int     # expected SOL out when selling probe_tokens
    sell_price_impact: float

    # Mid-price in SOL per whole token (using pool reserves, no slippage)
    mid_price_sol_per_token: float

    captured_at: float = field(default_factory=time.monotonic)

    # Stub fields kept for executor compatibility (FORCE_FIRST_SWAP path)
    buy_quote: dict = field(default_factory=dict)
    sell_quote: dict = field(default_factory=dict)

    @property
    def buy_price_sol_per_token(self) -> float:
        """Effective SOL cost per whole token (including fee + slippage)."""
        if self.probe_tokens == 0:
            return float('inf')
        return (self.probe_sol_lamports / config.SOL_LAMPORTS) / (self.probe_tokens / 10**config.TOKEN_DECIMALS)

    @property
    def sell_price_sol_per_token(self) -> float:
        """Effective SOL received per whole token (including fee + slippage)."""
        if self.probe_tokens == 0:
            return 0.0
        return (self.sell_out_lamports / config.SOL_LAMPORTS) / (self.probe_tokens / 10**config.TOKEN_DECIMALS)

    @property
    def spread_pct(self) -> float:
        """(sell_price - buy_price) / buy_price * 100."""
        b = self.buy_price_sol_per_token
        s = self.sell_price_sol_per_token
        if b == 0 or b == float('inf'):
            return 0.0
        return (s - b) / b * 100


@dataclass
class DualPoolSnapshot:
    """Combined Raydium on-chain + Meteora DexScreener snapshot for cross-pool routing."""
    raydium: PriceSnapshot
    meteora_mid: float              # 0.0 if Meteora data unavailable
    meteora_volume_1h_usd: float
    discrepancy_bps: float          # (raydium_mid - meteora_mid) / meteora_mid * 10000

    # Proxy properties so main.py can treat DualPoolSnapshot like a PriceSnapshot.
    @property
    def mid_price_sol_per_token(self) -> float:
        return self.raydium.mid_price_sol_per_token

    @property
    def pool(self):
        return self.raydium.pool

    @property
    def probe_sol_lamports(self) -> int:
        return self.raydium.probe_sol_lamports

    @property
    def probe_tokens(self) -> int:
        return self.raydium.probe_tokens

    @property
    def abs_discrepancy_bps(self) -> float:
        return abs(self.discrepancy_bps)

    def cheaper_buy_pool(self) -> str:
        """Pool with lower SOL/token price (cheaper to buy)."""
        if self.meteora_mid <= 0:
            return 'raydium'
        return 'raydium' if self.raydium.mid_price_sol_per_token <= self.meteora_mid else 'meteora'

    def better_sell_pool(self) -> str:
        """Pool with higher SOL/token price (better return when selling)."""
        if self.meteora_mid <= 0:
            return 'raydium'
        return 'raydium' if self.raydium.mid_price_sol_per_token >= self.meteora_mid else 'meteora'


def _mid_price(pool: CpmmPool) -> float:
    """Instantaneous mid-price SOL per whole token from pool reserves."""
    if pool.token_0_mint == WSOL_MINT:
        sol_reserve   = pool.vault_0_balance - pool.protocol_fee_0 - pool.fund_fee_0
        token_reserve = pool.vault_1_balance - pool.protocol_fee_1 - pool.fund_fee_1
        token_decimals = pool.mint_1_decimals
    else:
        sol_reserve   = pool.vault_1_balance - pool.protocol_fee_1 - pool.fund_fee_1
        token_reserve = pool.vault_0_balance - pool.protocol_fee_0 - pool.fund_fee_0
        token_decimals = pool.mint_0_decimals
    if token_reserve == 0:
        return 0.0
    # lamports per raw token unit → convert to SOL per whole token
    return (sol_reserve / token_reserve) * (10**token_decimals / config.SOL_LAMPORTS)


def _price_impact_pct(amount_in: int, reserve_in: int) -> float:
    """Approximate price impact as % (linear approximation)."""
    if reserve_in == 0:
        return 100.0
    return amount_in / reserve_in * 100


async def get_price_snapshot(probe_sol: float = config.PROBE_SOL) -> Optional[PriceSnapshot]:
    """Fetch Raydium CPMM pool state and compute buy/sell quotes locally."""
    rpc_url = config.HELIUS_RPC.format(key=config.HELIUS_KEY) if config.HELIUS_KEY else 'https://api.mainnet-beta.solana.com'
    try:
        pool = await fetch_pool(rpc_url, config.RAYDIUM_POOL_ID)
    except Exception as e:
        log.warning(f'fetch_pool failed: {e}')
        return None

    probe_lamports = int(probe_sol * config.SOL_LAMPORTS)

    # Quote: SOL → TOKEN
    buy_out, _ = quote_swap_base_input(pool, WSOL_MINT, probe_lamports)
    if buy_out <= 0:
        log.warning('buy quote returned 0')
        return None

    # Quote: TOKEN → SOL (round-trip on the probe tokens)
    sell_out, _ = quote_swap_base_input(pool, pool.token_1_mint if pool.token_0_mint == WSOL_MINT else pool.token_0_mint, buy_out)
    if sell_out <= 0:
        log.warning('sell quote returned 0')
        return None

    # Pool reserves for impact estimate
    if pool.token_0_mint == WSOL_MINT:
        sol_reserve = pool.vault_0_balance - pool.protocol_fee_0 - pool.fund_fee_0
        tok_reserve = pool.vault_1_balance - pool.protocol_fee_1 - pool.fund_fee_1
    else:
        sol_reserve = pool.vault_1_balance - pool.protocol_fee_1 - pool.fund_fee_1
        tok_reserve = pool.vault_0_balance - pool.protocol_fee_0 - pool.fund_fee_0

    buy_impact  = _price_impact_pct(probe_lamports, sol_reserve)
    sell_impact = _price_impact_pct(buy_out, tok_reserve)
    mid         = _mid_price(pool)

    snap = PriceSnapshot(
        pool=pool,
        probe_sol_lamports=probe_lamports,
        probe_tokens=buy_out,
        buy_price_impact=buy_impact,
        sell_out_lamports=sell_out,
        sell_price_impact=sell_impact,
        mid_price_sol_per_token=mid,
    )

    log.debug(
        f'Pool: mid={mid:.8f} SOL/tok  '
        f'buy={snap.buy_price_sol_per_token:.8f}  '
        f'sell={snap.sell_price_sol_per_token:.8f}  '
        f'spread={snap.spread_pct:.4f}%  '
        f'sol_liq={sol_reserve/1e9:.3f} SOL  '
        f'tok_liq={tok_reserve/10**config.TOKEN_DECIMALS:.0f} tok'
    )
    return snap


async def get_dual_snapshot(probe_sol: float = config.PROBE_SOL) -> Optional[DualPoolSnapshot]:
    """Fetch Raydium on-chain + Meteora DexScreener price snapshots."""
    from dex.meteora_dlmm import get_meteora_snapshot

    raydium_snap = await get_price_snapshot(probe_sol)
    if raydium_snap is None:
        return None

    meteora_snap = get_meteora_snapshot()
    if meteora_snap is None or meteora_snap.mid_price_sol_per_token <= 0:
        return DualPoolSnapshot(
            raydium=raydium_snap,
            meteora_mid=0.0,
            meteora_volume_1h_usd=0.0,
            discrepancy_bps=0.0,
        )

    raydium_mid = raydium_snap.mid_price_sol_per_token
    meteora_mid = meteora_snap.mid_price_sol_per_token
    discrepancy_bps = (raydium_mid - meteora_mid) / meteora_mid * 10_000

    log.info(
        f'[DualPool] Raydium={raydium_mid:.8f} Meteora={meteora_mid:.8f} '
        f'discrepancy={discrepancy_bps:+.1f}bps  1h_vol=${meteora_snap.volume_1h_usd:.0f}'
    )

    return DualPoolSnapshot(
        raydium=raydium_snap,
        meteora_mid=meteora_mid,
        meteora_volume_1h_usd=meteora_snap.volume_1h_usd,
        discrepancy_bps=discrepancy_bps,
    )


# Keep _get_quote available for RECOVER_USDC path in main.py
async def _get_quote(client, input_mint, output_mint, amount, slippage_bps=config.SLIPPAGE_BPS):
    """Jupiter quote (used only for USDC recovery path)."""
    params = {
        'inputMint': input_mint, 'outputMint': output_mint,
        'amount': str(amount), 'slippageBps': str(slippage_bps),
    }
    try:
        resp = await client.get(config.JUPITER_QUOTE, params=params, timeout=8)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        log.warning(f'Jupiter quote failed: {e}')
        return None
