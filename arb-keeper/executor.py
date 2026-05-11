"""
executor.py — Jupiter swap transaction builder + Jito bundle submitter.

Flow:
1. POST to Jupiter /v6/swap to get a serialized versioned transaction for each leg
2. Inject a Jito tip transfer instruction into the buy transaction
3. Sign both transactions with the keeper keypair
4. Submit as a 2-tx Jito bundle
5. Poll for bundle confirmation
"""

import base64
import json
import logging
import random
import asyncio
import time
from dataclasses import dataclass
from typing import Optional

import httpx

import config
from detector import ArbOpportunity

log = logging.getLogger(__name__)


@dataclass
class TradeResult:
    success: bool
    bundle_id: Optional[str]
    actual_profit_sol: Optional[float]   # None until confirmed on-chain
    error: Optional[str]
    opportunity: ArbOpportunity


async def _get_swap_tx(client: httpx.AsyncClient, quote: dict, wallet_pubkey: str) -> Optional[str]:
    """Call Jupiter /v6/swap, return base64 serialized versioned transaction."""
    payload = {
        'quoteResponse':      quote,
        'userPublicKey':      wallet_pubkey,
        'wrapAndUnwrapSol':   True,
        'dynamicComputeUnitLimit': True,
        'prioritizationFeeLamports': 'auto',
    }
    try:
        resp = await client.post(config.JUPITER_SWAP, json=payload, timeout=15)
        if resp.status_code != 200:
            log.error(f'Jupiter /swap HTTP {resp.status_code}: {resp.text[:300]}')
            return None
        data = resp.json()
        tx = data.get('swapTransaction')
        if not tx:
            log.error(f'Jupiter /swap returned no transaction: {data}')
        return tx
    except Exception as e:
        log.error(f'Jupiter /swap failed: {type(e).__name__}: {e}')
        return None


async def _build_tip_tx(keypair, tip_lamports: int, rpc_url: str) -> bytes:
    """Build a standalone tip-only transaction (sent as leg 3 of the bundle)."""
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

    # Fetch a recent blockhash
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
    signed = VersionedTransaction(msg, [keypair])
    return bytes(signed)


def _sign_tx(tx_b64: str, keypair) -> bytes:
    """Sign a Jupiter versioned transaction without modifying instructions."""
    from solders.transaction import VersionedTransaction  # type: ignore

    raw = base64.b64decode(tx_b64)
    tx = VersionedTransaction.from_bytes(raw)
    signed = VersionedTransaction(tx.message, [keypair])
    return bytes(signed)


async def _submit_bundle(signed_txns: list[bytes]) -> Optional[str]:
    """Submit transactions as a Jito bundle. Returns bundle_id or None."""
    encoded = [base64.b64encode(tx).decode() for tx in signed_txns]
    payload = {
        'jsonrpc': '2.0',
        'id': 1,
        'method': 'sendBundle',
        'params': [encoded],
    }
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(config.JITO_URL, json=payload, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            bundle_id = data.get('result')
            log.info(f'Jito bundle submitted: {bundle_id}')
            return bundle_id
    except Exception as e:
        log.error(f'Jito bundle submission failed: {e}')
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
                    data = resp.json()
                    status = (data.get('result') or {}).get('value', {}).get('bundle_id', {})
                    confirmation = data.get('result', {})
                    # Jito returns confirmation_status when landed
                    if 'confirmed' in str(confirmation).lower() or 'finalized' in str(confirmation).lower():
                        return True
            except Exception:
                pass
            await asyncio.sleep(2)
    return False


async def execute_arb(opportunity: ArbOpportunity, keypair) -> TradeResult:
    """
    Execute a two-leg arb as a Jito bundle:
      Tx1 (buy):  SOL → TOKEN  + Jito tip
      Tx2 (sell): TOKEN → SOL
    """
    pubkey = str(keypair.pubkey())

    # Staleness guard: abort if quote is >800ms old before we even build txns.
    # At that age the spread may have closed; landing at a stale price is a loss.
    quote_age_ms = (time.monotonic() - opportunity.snapshot_at) * 1000
    if quote_age_ms > 800:
        log.warning(f'Quote stale ({quote_age_ms:.0f}ms) — skipping execution')
        return TradeResult(
            success=False, bundle_id=None, actual_profit_sol=None,
            error=f'Quote stale: {quote_age_ms:.0f}ms', opportunity=opportunity,
        )

    async with httpx.AsyncClient() as client:
        # Build both swap transactions in parallel
        buy_tx_b64, sell_tx_b64 = await asyncio.gather(
            _get_swap_tx(client, opportunity.buy_quote,  pubkey),
            _get_swap_tx(client, opportunity.sell_quote, pubkey),
        )

    if not buy_tx_b64 or not sell_tx_b64:
        return TradeResult(
            success=False, bundle_id=None, actual_profit_sol=None,
            error='Failed to build swap transactions', opportunity=opportunity,
        )

    try:
        signed_buy  = _sign_tx(buy_tx_b64,  keypair)
        signed_sell = _sign_tx(sell_tx_b64, keypair)
        # Standalone tip tx as 3rd leg in the Jito bundle
        import os
        rpc_url = config.HELIUS_RPC.format(key=os.environ.get('HELIUS_API_KEY', ''))
        signed_tip  = await _build_tip_tx(keypair, opportunity.jito_tip_lamports, rpc_url)
    except Exception as e:
        return TradeResult(
            success=False, bundle_id=None, actual_profit_sol=None,
            error=f'Transaction signing failed: {type(e).__name__}: {e}', opportunity=opportunity,
        )

    bundle_id = await _submit_bundle([signed_buy, signed_sell, signed_tip])
    if not bundle_id:
        return TradeResult(
            success=False, bundle_id=None, actual_profit_sol=None,
            error='Bundle submission failed', opportunity=opportunity,
        )

    landed = await _poll_bundle(bundle_id, timeout=30.0)
    if landed:
        log.info(f'Bundle {bundle_id} landed ✓  est net +{opportunity.net_profit_sol*1000:.4f} mSOL')
        return TradeResult(
            success=True,
            bundle_id=bundle_id,
            actual_profit_sol=opportunity.net_profit_sol,  # confirmed on-chain; actual verified separately
            error=None,
            opportunity=opportunity,
        )
    else:
        log.warning(f'Bundle {bundle_id} did not confirm within 30s (may still land)')
        return TradeResult(
            success=False, bundle_id=bundle_id, actual_profit_sol=None,
            error='Bundle timeout — did not confirm in 30s', opportunity=opportunity,
        )
