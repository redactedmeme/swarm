"""
main.py — arb-keeper entry point.

Phase 1 (EXECUTE_TRADES=false): detect opportunities, log to Redis, no execution.
Phase 2+ (EXECUTE_TRADES=true):  execute arbs as Jito bundles.

Env vars required:
  SOLANA_PRIVATE_KEY  — 64-byte base58 keypair
  HELIUS_API_KEY      — for Solana RPC
  REDIS_URL           — redis://swarm-redis.railway.internal:6379
  EXECUTE_TRADES      — "true" to enable execution (default: false)
"""

import asyncio
import logging
import time

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    datefmt='%H:%M:%S',
)

import config
import logger as swarm_log
from price_feed import get_price_snapshot
from detector import find_opportunity
from circuit_breaker import CircuitBreaker

log = logging.getLogger('arb-keeper')

# Suppress noisy httpx logs
logging.getLogger('httpx').setLevel(logging.WARNING)
logging.getLogger('httpcore').setLevel(logging.WARNING)


def _load_wallet():
    """Load keypair if execution is enabled. Returns (keypair, pubkey_str)."""
    if not config.EXECUTE_TRADES:
        return None, None
    from wallet import load_keypair
    kp = load_keypair()
    pubkey = str(kp.pubkey())
    log.info(f'Keeper wallet: {pubkey}')
    return kp, pubkey


async def _get_balance(pubkey: str) -> float:
    if not pubkey:
        return 999.0  # dummy balance for detect-only mode
    from wallet import get_sol_balance
    try:
        return await get_sol_balance(pubkey)
    except Exception as e:
        log.warning(f'Balance check failed: {e}')
        return 0.0


async def _get_token_balance(pubkey: str) -> int:
    if not pubkey:
        return 0
    from wallet import get_token_balance
    try:
        return await get_token_balance(pubkey, config.TOKEN_MINT)
    except Exception as e:
        log.warning(f'Token balance check failed: {e}')
        return 0


async def run():
    mode = 'EXECUTE' if config.EXECUTE_TRADES else 'DETECT-ONLY'
    log.info(f'arb-keeper starting — mode: {mode}')
    log.info(
        f'TARGET_RATIO={config.TARGET_RATIO*100:.0f}%  '
        f'TOLERANCE={config.REBALANCE_TOLERANCE*100:.0f}%  '
        f'MAX_TRADE={config.MAX_TRADE_SOL} SOL  '
        f'POLL={config.POLL_INTERVAL}s  '
        f'POOL={config.RAYDIUM_POOL_ID[:16]}...'
    )

    keypair, pubkey = _load_wallet()
    cb = CircuitBreaker()

    heartbeat  = 0
    opps_seen  = 0
    trades_run = 0
    token_balance_raw = 0  # updated each loop when wallet is loaded

    while True:
        loop_start = time.monotonic()

        try:
            # ── Circuit check ────────────────────────────────────────────────
            if config.EXECUTE_TRADES and cb.is_open():
                await asyncio.sleep(config.POLL_INTERVAL)
                continue

            # ── Price snapshot ───────────────────────────────────────────────
            snapshot = await get_price_snapshot(probe_sol=config.PROBE_SOL)
            if snapshot is None:
                log.debug('Price snapshot unavailable — skipping')
                await asyncio.sleep(config.POLL_INTERVAL)
                continue

            # ── Balance check ────────────────────────────────────────────────
            sol_balance = await _get_balance(pubkey)
            token_balance_raw = await _get_token_balance(pubkey)

            # ── Detect rebalance opportunity ─────────────────────────────────
            opp = find_opportunity(snapshot, sol_balance, token_balance_raw)

            # ── DIRECT_DEX_TEST: SOL → REDACTED → SOL via Raydium CPMM directly ──
            if config.EXECUTE_TRADES and trades_run == 0 and __import__('os').environ.get('DIRECT_DEX_TEST', '').lower() == 'true':
                import os, httpx, base58
                from dex.raydium_cpmm import fetch_pool, WSOL_MINT
                from dex.swap_tx import build_sol_to_token_tx, build_token_to_sol_tx, get_associated_token_address
                pool_addr = os.environ.get('TEST_POOL_ADDR', '14qc563Gd2V4nKhoK6Yoj8gYEgPa8JmadLfh45czFWJ1')
                sol_in    = int(float(os.environ.get('TEST_SOL_AMOUNT', '0.0005')) * 1e9)
                rpc_url   = os.environ.get('SOLANA_RPC_URL', 'https://api.mainnet-beta.solana.com')

                log.warning(f'DIRECT_DEX_TEST: pool={pool_addr} sol_in={sol_in}')
                pool = await fetch_pool(rpc_url, pool_addr)
                log.warning(f'pool token0={pool.token_0_mint[:8]} ({pool.vault_0_balance}) token1={pool.token_1_mint[:8]} ({pool.vault_1_balance}) fee={pool.trade_fee_rate}')

                async with httpx.AsyncClient() as c:
                    # Check current REDACTED balance — if we already have some, sell it first
                    r = await c.post(rpc_url, json={'jsonrpc':'2.0','id':1,'method':'getTokenAccountsByOwner','params':[pubkey,{'mint':pool.token_1_mint if pool.token_0_mint == WSOL_MINT else pool.token_0_mint},{'encoding':'jsonParsed'}]}, timeout=10)
                    accs = r.json().get('result', {}).get('value', [])
                    redacted_balance = int(accs[0]['account']['data']['parsed']['info']['tokenAmount']['amount']) if accs else 0
                    log.warning(f'Current REDACTED balance: {redacted_balance}')

                    if redacted_balance > 0:
                        # Refresh pool state (rates may have changed)
                        pool = await fetch_pool(rpc_url, pool_addr)
                        tx, expected = await build_token_to_sol_tx(rpc_url, keypair, pool, redacted_balance, slippage_bps=500)
                        log.warning(f'SELL: {redacted_balance} REDACTED -> expected {expected} lamports SOL')
                        r = await c.post(rpc_url, json={
                            'jsonrpc':'2.0','id':1,'method':'sendTransaction',
                            'params':[base58.b58encode(tx).decode(),{'encoding':'base58','skipPreflight':False,'maxRetries':3}]
                        }, timeout=15)
                        log.warning(f'SELL result: {r.text[:400]}')
                    else:
                        # Buy: SOL → REDACTED
                        tx, expected = await build_sol_to_token_tx(rpc_url, keypair, pool, sol_in, slippage_bps=500)
                        log.warning(f'BUY: {sol_in} lamports SOL -> expected {expected} REDACTED')
                        r = await c.post(rpc_url, json={
                            'jsonrpc':'2.0','id':1,'method':'sendTransaction',
                            'params':[base58.b58encode(tx).decode(),{'encoding':'base58','skipPreflight':False,'maxRetries':3}]
                        }, timeout=15)
                        log.warning(f'BUY result: {r.text[:400]}')

                trades_run += 1
                await asyncio.sleep(config.POLL_INTERVAL)
                continue

            # ── RECOVER_USDC: convert any USDC in wallet back to SOL via Jupiter ──
            if config.EXECUTE_TRADES and trades_run == 0 and __import__('os').environ.get('RECOVER_USDC', '').lower() == 'true':
                import os, httpx, base58
                from price_feed import _get_quote
                from executor import _sign_tx
                rpc_url = config.HELIUS_RPC.format(key=os.environ.get('HELIUS_API_KEY', ''))
                USDC = 'EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v'
                async with httpx.AsyncClient() as c:
                    # Read USDC balance
                    r = await c.post(rpc_url, json={'jsonrpc':'2.0','id':1,'method':'getTokenAccountsByOwner','params':[pubkey,{'mint':USDC},{'encoding':'jsonParsed'}]}, timeout=10)
                    accs = r.json()['result']['value']
                    if not accs:
                        log.warning('RECOVER_USDC: no USDC account found')
                        trades_run += 1
                        continue
                    amount = int(accs[0]['account']['data']['parsed']['info']['tokenAmount']['amount'])
                    log.warning(f'RECOVER_USDC: selling {amount} USDC lamports')
                    quote = await _get_quote(c, USDC, config.SOL_MINT, amount, slippage_bps=500)
                    if not quote:
                        log.error('RECOVER_USDC: quote failed')
                        trades_run += 1
                        continue
                    sr = await c.post(config.JUPITER_SWAP, json={
                        'quoteResponse': quote, 'userPublicKey': pubkey,
                        'wrapAndUnwrapSol': True, 'dynamicComputeUnitLimit': True,
                        'prioritizationFeeLamports': 0,
                    }, timeout=15)
                    swap_b64 = sr.json().get('swapTransaction')
                    signed = _sign_tx(swap_b64, keypair)
                    tr = await c.post(rpc_url, json={
                        'jsonrpc':'2.0','id':1,'method':'sendTransaction',
                        'params':[base58.b58encode(signed).decode(),{'encoding':'base58','skipPreflight':False,'maxRetries':3}]
                    }, timeout=15)
                    log.warning(f'RECOVER_USDC sendTx: {tr.text[:300]}')
                trades_run += 1
                await asyncio.sleep(config.POLL_INTERVAL)
                continue

            # ── TIP_ONLY_TEST: try both regular RPC send and Jito bundle ──
            if config.EXECUTE_TRADES and trades_run == 0 and __import__('os').environ.get('TIP_ONLY_TEST', '').lower() == 'true':
                import os, base64, base58, httpx
                from executor import _build_tip_tx, _submit_bundle
                rpc_url = config.HELIUS_RPC.format(key=os.environ.get('HELIUS_API_KEY', ''))
                log.warning('TIP_ONLY_TEST: building tip tx')
                tip_tx = await _build_tip_tx(keypair, config.JITO_TIP_LAMPORTS, rpc_url)
                log.warning(f'TIP_ONLY_TEST: tx size {len(tip_tx)} bytes')

                # Attempt A: regular Solana RPC sendTransaction (verifies tx validity)
                try:
                    async with httpx.AsyncClient() as c:
                        r = await c.post(rpc_url, json={
                            'jsonrpc': '2.0', 'id': 1, 'method': 'sendTransaction',
                            'params': [base58.b58encode(tip_tx).decode(),
                                       {'encoding': 'base58', 'skipPreflight': False}]
                        }, timeout=15)
                        log.warning(f'TIP_ONLY_TEST regular RPC: {r.status_code} {r.text[:400]}')
                except Exception as e:
                    log.error(f'regular sendTransaction failed: {e}')

                # Attempt B: Jito bundle
                bid = await _submit_bundle([tip_tx])
                log.warning(f'TIP_ONLY_TEST Jito bundle_id={bid}')
                trades_run += 1
                await asyncio.sleep(config.POLL_INTERVAL)
                continue

            # ── FORCE_FIRST_SWAP override: synthesize a rebalance order to ──
            # validate the on-chain execution pipeline (buy TOKEN with probe SOL).
            if not opp and config.FORCE_FIRST_SWAP and config.EXECUTE_TRADES and trades_run == 0:
                from detector import RebalanceOrder
                from dex.raydium_cpmm import WSOL_MINT, quote_swap_base_input
                log.warning('FORCE_FIRST_SWAP active — synthesizing buy-token order for pipeline test')
                sol_lam = snapshot.probe_sol_lamports
                tok_out, _ = quote_swap_base_input(snapshot.pool, WSOL_MINT, sol_lam)
                opp = RebalanceOrder(
                    is_buy_token=True,
                    sol_amount=sol_lam / config.SOL_LAMPORTS,
                    sol_lamports=sol_lam,
                    token_amount=tok_out,
                    sol_balance=sol_balance,
                    token_balance_raw=token_balance_raw,
                    total_value_sol=sol_balance,
                    current_ratio=0.0,
                    target_ratio=config.TARGET_RATIO,
                    deviation=config.TARGET_RATIO,
                    price_sol_per_token=snapshot.mid_price_sol_per_token,
                    pool=snapshot.pool,
                )

            if opp:
                opps_seen += 1
                swarm_log.log_opportunity(opp)

                if config.EXECUTE_TRADES:
                    # ── Execute ──────────────────────────────────────────────
                    from executor import execute_arb
                    result = await execute_arb(opp, keypair)
                    trades_run += 1
                    swarm_log.log_trade(result)

                    if not result.success:
                        log.error(f'Trade FAILED: bundle_id={result.bundle_id} error={result.error}')

                    if result.success:
                        cb.record_success(result.actual_profit_sol or 0.0)
                    else:
                        # Only count as a loss if the bundle was submitted (not a build failure)
                        loss = 0.0
                        if result.bundle_id:
                            # Tip was spent even if bundle timed out
                            loss = config.JITO_TIP_LAMPORTS / config.SOL_LAMPORTS
                        cb.record_failure(loss)
                else:
                    log.info(f'[DETECT-ONLY] Would execute: {opp.describe()}')

            # ── Periodic heartbeat ───────────────────────────────────────────
            heartbeat += 1
            if heartbeat % 60 == 0:
                bal_str = f'{sol_balance:.4f} SOL' if pubkey else 'n/a'
                tok_str = f'{token_balance_raw / 10**config.TOKEN_DECIMALS:.2f} tok'
                log.info(
                    f'Heartbeat: {opps_seen} rebalances detected | {trades_run} trades run | '
                    f'balance {bal_str} + {tok_str} | mid={snapshot.mid_price_sol_per_token:.8f} SOL/tok'
                )
                swarm_log.log_circuit_status({**cb.status(), 'opps_seen': opps_seen, 'trades_run': trades_run})

        except Exception as e:
            log.error(f'Main loop error: {e}', exc_info=True)

        # ── Pace to poll interval ────────────────────────────────────────────
        elapsed = time.monotonic() - loop_start
        sleep_for = max(0.0, config.POLL_INTERVAL - elapsed)
        await asyncio.sleep(sleep_for)


if __name__ == '__main__':
    asyncio.run(run())
