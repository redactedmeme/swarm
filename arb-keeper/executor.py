"""
executor.py — Raydium CPMM single-leg swap executor + Jito bundle submitter.

Executes a RebalanceOrder as a single Raydium CPMM transaction submitted via
Jito (MEV-protected) or regular RPC (USE_RPC_FALLBACK=true).

Flow:
1. Build signed VersionedTransaction for the single swap leg (SOL→TOKEN or TOKEN→SOL)
2. Build standalone Jito tip transaction
3. Submit as a 2-tx Jito bundle [swap, tip]
4. Poll for confirmation
"""

import base64
import base58
import logging
import random
import asyncio
import os
from dataclasses import dataclass
from typing import Optional

import httpx

import config
from detector import RebalanceOrder

log = logging.getLogger(__name__)

# Alias for backward compat (RECOVER_USDC path in main.py uses this)
ArbOpportunity = RebalanceOrder


@dataclass
class TradeResult:
    success: bool
    bundle_id: Optional[str]
    actual_profit_sol: Optional[float]
    error: Optional[str]
    opportunity: RebalanceOrder


def _rpc_url() -> str:
    key = os.environ.get('HELIUS_API_KEY', config.HELIUS_KEY)
    if key:
        return config.HELIUS_RPC.format(key=key)
    return 'https://api.mainnet-beta.solana.com'


async def _build_tip_tx(keypair, tip_lamports: int, rpc_url: str) -> bytes:
    """Build a standalone tip-only VersionedTransaction."""
    from solders.transaction import VersionedTransaction      # type: ignore
    from solders.system_program import transfer, TransferParams  # type: ignore
    from solders.pubkey import Pubkey                          # type: ignore
    from solders.message import MessageV0                      # type: ignore
    from solders.hash import Hash                              # type: ignore

    tip_acct = Pubkey.from_string(random.choice(config.JITO_TIP_ACCOUNTS))
    tip_ix = transfer(TransferParams(
        from_pubkey=keypair.pubkey(),
        to_pubkey=tip_acct,
        lamports=tip_lamports,
    ))
    async with httpx.AsyncClient() as client:
        resp = await client.post(rpc_url, json={
            'jsonrpc': '2.0', 'id': 1, 'method': 'getLatestBlockhash', 'params': []
        }, timeout=10)
        resp.raise_for_status()
        blockhash_str = resp.json()['result']['value']['blockhash']
    msg = MessageV0.try_compile(
        payer=keypair.pubkey(),
        instructions=[tip_ix],
        address_lookup_table_accounts=[],
        recent_blockhash=Hash.from_string(blockhash_str),
    )
    return bytes(VersionedTransaction(msg, [keypair]))


def _sign_tx(tx_b64: str, keypair) -> bytes:
    """Sign a Jupiter versioned transaction (used by RECOVER_USDC path)."""
    from solders.transaction import VersionedTransaction  # type: ignore
    raw = base64.b64decode(tx_b64)
    tx = VersionedTransaction.from_bytes(raw)
    return bytes(VersionedTransaction(tx.message, [keypair]))


async def _submit_bundle(signed_txns: list[bytes]) -> Optional[str]:
    """Submit as a Jito bundle (base58-encoded). Returns bundle_id or None."""
    encoded = [base58.b58encode(tx).decode() for tx in signed_txns]
    payload = {'jsonrpc': '2.0', 'id': 1, 'method': 'sendBundle', 'params': [encoded]}
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(config.JITO_URL, json=payload, timeout=15)
            if resp.status_code != 200:
                log.error(f'Jito sendBundle HTTP {resp.status_code}: {resp.text[:500]}')
                return None
            data = resp.json()
            if 'error' in data:
                log.error(f'Jito sendBundle error: {data["error"]}')
                return None
            bundle_id = data.get('result')
            log.info(f'Jito bundle submitted: {bundle_id}')
            return bundle_id
    except Exception as e:
        log.error(f'Jito bundle submission failed: {type(e).__name__}: {e}')
        return None


async def _poll_bundle(bundle_id: str, timeout: float = 30.0) -> bool:
    """Poll Jito for bundle status. Returns True if landed."""
    url = f'https://mainnet.block-engine.jito.wtf/api/v1/bundles/status/{bundle_id}'
    deadline = asyncio.get_event_loop().time() + timeout
    async with httpx.AsyncClient() as client:
        while asyncio.get_event_loop().time() < deadline:
            try:
                resp = await client.get(url, timeout=5)
                if resp.status_code == 200:
                    text = resp.text.lower()
                    if 'confirmed' in text or 'finalized' in text:
                        return True
            except Exception:
                pass
            await asyncio.sleep(2)
    return False


async def _execute_via_jupiter(
    opportunity: RebalanceOrder, keypair, pubkey: str, rpc_url: str,
) -> TradeResult:
    """Execute via Jupiter API (for Meteora-routed orders)."""
    if opportunity.is_buy_token:
        input_mint  = config.SOL_MINT
        output_mint = config.TOKEN_MINT
        amount      = opportunity.sol_lamports
    else:
        input_mint  = config.TOKEN_MINT
        output_mint = config.SOL_MINT
        amount      = opportunity.token_amount

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(config.JUPITER_QUOTE, params={
                'inputMint':        input_mint,
                'outputMint':       output_mint,
                'amount':           str(amount),
                'slippageBps':      str(config.SLIPPAGE_BPS),
                'onlyDirectRoutes': 'true',
            }, timeout=8)
            resp.raise_for_status()
            quote = resp.json()

            swap_resp = await client.post(config.JUPITER_SWAP, json={
                'quoteResponse':              quote,
                'userPublicKey':              pubkey,
                'wrapAndUnwrapSol':           True,
                'dynamicComputeUnitLimit':    True,
                'prioritizationFeeLamports':  config.COMPUTE_UNIT_PRICE_MICRO,
            }, timeout=15)
            swap_resp.raise_for_status()
            swap_b64 = swap_resp.json().get('swapTransaction')
    except Exception as e:
        return TradeResult(
            success=False, bundle_id=None, actual_profit_sol=None,
            error=f'Jupiter quote/swap failed: {type(e).__name__}: {e}',
            opportunity=opportunity,
        )

    try:
        swap_tx = _sign_tx(swap_b64, keypair)
    except Exception as e:
        return TradeResult(
            success=False, bundle_id=None, actual_profit_sol=None,
            error=f'Jupiter tx signing failed: {e}', opportunity=opportunity,
        )

    use_rpc = os.environ.get('USE_RPC_FALLBACK', '').lower() == 'true'
    if use_rpc:
        async with httpx.AsyncClient() as client:
            r = await client.post(rpc_url, json={
                'jsonrpc': '2.0', 'id': 1, 'method': 'sendTransaction',
                'params': [base58.b58encode(swap_tx).decode(),
                           {'encoding': 'base58', 'skipPreflight': False, 'maxRetries': 3}],
            }, timeout=15)
            data = r.json()
            if 'error' in data:
                return TradeResult(
                    success=False, bundle_id=None, actual_profit_sol=None,
                    error=f'Jupiter sendTransaction failed: {data["error"]}',
                    opportunity=opportunity,
                )
            return TradeResult(
                success=True, bundle_id=data.get('result'), actual_profit_sol=None,
                error=None, opportunity=opportunity,
            )

    try:
        tip_tx = await _build_tip_tx(keypair, config.JITO_TIP_LAMPORTS, rpc_url)
    except Exception as e:
        return TradeResult(
            success=False, bundle_id=None, actual_profit_sol=None,
            error=f'Tip tx build failed: {e}', opportunity=opportunity,
        )

    bundle_id = await _submit_bundle([swap_tx, tip_tx])
    if not bundle_id:
        return TradeResult(
            success=False, bundle_id=None, actual_profit_sol=None,
            error='Jupiter+Jito bundle submission failed', opportunity=opportunity,
        )

    landed = await _poll_bundle(bundle_id, timeout=30.0)
    if landed:
        log.info(f'Jupiter/Meteora bundle {bundle_id} landed ✓')
        return TradeResult(
            success=True, bundle_id=bundle_id, actual_profit_sol=None,
            error=None, opportunity=opportunity,
        )
    else:
        log.warning(f'Jupiter/Meteora bundle {bundle_id} did not confirm within 30s (may still land)')
        return TradeResult(
            success=False, bundle_id=bundle_id, actual_profit_sol=None,
            error='Jupiter bundle timeout — did not confirm in 30s', opportunity=opportunity,
        )


async def execute_arb(opportunity: RebalanceOrder, keypair) -> TradeResult:
    """
    Execute a single-leg rebalance swap.
    Routes to Raydium CPMM directly, or Meteora via Jupiter, based on opportunity.route_pool.
    Submits as a Jito bundle [swap_tx, tip_tx] unless USE_RPC_FALLBACK=true.
    """
    from dex.swap_tx import build_sol_to_token_tx, build_token_to_sol_tx
    from dex.raydium_cpmm import fetch_pool

    pubkey  = str(keypair.pubkey())
    rpc_url = _rpc_url()

    # Route to Meteora via Jupiter if the order was cross-pool-routed
    if getattr(opportunity, 'route_pool', 'raydium') == 'meteora':
        log.info(
            f'[METEORA] Executing via Jupiter '
            f'(discrepancy >= {config.ARB_MIN_DISCREPANCY_BPS}bps)'
        )
        return await _execute_via_jupiter(opportunity, keypair, pubkey, rpc_url)

    # Refresh pool state right before building the tx to avoid stale reserves
    try:
        pool = await fetch_pool(rpc_url, config.RAYDIUM_POOL_ID)
    except Exception as e:
        return TradeResult(
            success=False, bundle_id=None, actual_profit_sol=None,
            error=f'Pool refresh failed: {e}', opportunity=opportunity,
        )

    try:
        if opportunity.is_buy_token:
            log.info(f'Building BUY tx: {opportunity.sol_lamports} lamports SOL → TOKEN')
            swap_tx, expected_out = await build_sol_to_token_tx(
                rpc_url, keypair, pool, opportunity.sol_lamports,
                slippage_bps=config.SLIPPAGE_BPS,
            )
            log.info(f'Expected token out: {expected_out / 10**config.TOKEN_DECIMALS:.4f}')
        else:
            log.info(f'Building SELL tx: {opportunity.token_amount / 10**config.TOKEN_DECIMALS:.4f} TOKEN → SOL')
            swap_tx, expected_out = await build_token_to_sol_tx(
                rpc_url, keypair, pool, opportunity.token_amount,
                slippage_bps=config.SLIPPAGE_BPS,
            )
            log.info(f'Expected SOL out: {expected_out / 1e9:.6f} SOL')
    except Exception as e:
        return TradeResult(
            success=False, bundle_id=None, actual_profit_sol=None,
            error=f'Swap tx build failed: {type(e).__name__}: {e}', opportunity=opportunity,
        )

    use_rpc = os.environ.get('USE_RPC_FALLBACK', '').lower() == 'true'
    if use_rpc:
        async with httpx.AsyncClient() as client:
            r = await client.post(rpc_url, json={
                'jsonrpc': '2.0', 'id': 1, 'method': 'sendTransaction',
                'params': [base58.b58encode(swap_tx).decode(),
                           {'encoding': 'base58', 'skipPreflight': False, 'maxRetries': 3}]
            }, timeout=15)
            data = r.json()
            if 'error' in data:
                return TradeResult(
                    success=False, bundle_id=None, actual_profit_sol=None,
                    error=f'sendTransaction failed: {data["error"]}', opportunity=opportunity,
                )
            sig = data.get('result', '')
            log.info(f'Swap tx sent: {sig}')
            return TradeResult(
                success=True, bundle_id=sig, actual_profit_sol=None,
                error=None, opportunity=opportunity,
            )

    try:
        tip_tx = await _build_tip_tx(keypair, config.JITO_TIP_LAMPORTS, rpc_url)
    except Exception as e:
        return TradeResult(
            success=False, bundle_id=None, actual_profit_sol=None,
            error=f'Tip tx build failed: {e}', opportunity=opportunity,
        )

    bundle_id = await _submit_bundle([swap_tx, tip_tx])
    if not bundle_id:
        return TradeResult(
            success=False, bundle_id=None, actual_profit_sol=None,
            error='Bundle submission failed', opportunity=opportunity,
        )

    landed = await _poll_bundle(bundle_id, timeout=30.0)
    if landed:
        log.info(f'Bundle {bundle_id} landed ✓')
        return TradeResult(
            success=True, bundle_id=bundle_id, actual_profit_sol=None,
            error=None, opportunity=opportunity,
        )
    else:
        log.warning(f'Bundle {bundle_id} did not confirm within 30s (may still land)')
        return TradeResult(
            success=False, bundle_id=bundle_id, actual_profit_sol=None,
            error='Bundle timeout — did not confirm in 30s', opportunity=opportunity,
        )
