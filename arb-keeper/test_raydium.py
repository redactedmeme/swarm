"""Quick local test: fetch the REDACTED/SOL pool and quote a small swap."""
import asyncio
import sys

from dex.raydium_cpmm import fetch_pool, quote_swap_base_input, WSOL_MINT

POOL = '14qc563Gd2V4nKhoK6Yoj8gYEgPa8JmadLfh45czFWJ1'
RPC  = 'https://api.mainnet-beta.solana.com'


async def main():
    pool = await fetch_pool(RPC, POOL)
    print(f'pool:          {pool.address}')
    print(f'amm_config:    {pool.amm_config}')
    print(f'token_0:       {pool.token_0_mint} ({pool.mint_0_decimals}d) vault={pool.token_0_vault} bal={pool.vault_0_balance}')
    print(f'token_1:       {pool.token_1_mint} ({pool.mint_1_decimals}d) vault={pool.token_1_vault} bal={pool.vault_1_balance}')
    print(f'trade_fee:     {pool.trade_fee_rate} / 1e6  ({pool.trade_fee_rate / 10_000:.4f}%)')
    print(f'observation:   {pool.observation_key}')

    # Quote 0.001 SOL → REDACTED
    amount_in = 1_000_000  # 0.001 SOL
    out, zero_for_one = quote_swap_base_input(pool, WSOL_MINT, amount_in)
    print()
    print(f'Quote: {amount_in} lamports SOL -> {out} raw REDACTED (zero_for_one={zero_for_one})')
    # Convert to ui amounts
    redacted_decimals = pool.mint_0_decimals if pool.token_0_mint != WSOL_MINT else pool.mint_1_decimals
    print(f'       = {out / 10**redacted_decimals:.6f} REDACTED (decimals={redacted_decimals})')


if __name__ == '__main__':
    asyncio.run(main())
