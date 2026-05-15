"""
wallet.py — arb-keeper Solana wallet.

Extends the smolting-telegram-bot keypair loading pattern with transaction
signing via solders and balance queries via Helius RPC.

Accepts SOLANA_PRIVATE_KEY as base58 64-byte keypair or 32-byte seed.
"""

import json
import logging
import asyncio
import httpx
from typing import Optional

import config

log = logging.getLogger(__name__)

_B58_ALPHABET = b'123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz'
_B58_MAP = {c: i for i, c in enumerate(_B58_ALPHABET)}


# ── Base58 ────────────────────────────────────────────────────────────────────

def b58decode(s: str) -> bytes:
    n = 0
    for char in s.encode():
        n = n * 58 + _B58_MAP[char]
    result = n.to_bytes((n.bit_length() + 7) // 8, 'big') if n else b''
    leading = len(s) - len(s.lstrip('1'))
    return b'\x00' * leading + result


def b58encode(data: bytes) -> str:
    n = int.from_bytes(data, 'big')
    result = []
    while n > 0:
        n, r = divmod(n, 58)
        result.append(_B58_ALPHABET[r:r+1])
    result.extend(b'1' * (len(data) - len(data.lstrip(b'\x00'))))
    return b''.join(reversed(result)).decode()


# ── Keypair loading ───────────────────────────────────────────────────────────

def load_keypair():
    """
    Returns a solders.keypair.Keypair, or raises if key is missing/invalid.
    Accepts 64-byte base58 (Phantom export) or 32-byte seed.
    """
    from solders.keypair import Keypair  # type: ignore

    raw = config.PRIVATE_KEY.strip()
    if not raw:
        raise RuntimeError('SOLANA_PRIVATE_KEY env var not set')

    try:
        decoded = b58decode(raw)
    except Exception:
        # Try JSON array format [1,2,3,...]
        try:
            arr = json.loads(raw)
            decoded = bytes(arr)
        except Exception:
            raise RuntimeError('SOLANA_PRIVATE_KEY is not valid base58 or JSON array')

    if len(decoded) == 64:
        return Keypair.from_bytes(decoded)
    elif len(decoded) == 32:
        return Keypair.from_seed(decoded)
    else:
        raise RuntimeError(f'SOLANA_PRIVATE_KEY decoded to {len(decoded)} bytes, expected 32 or 64')


# ── RPC helpers ───────────────────────────────────────────────────────────────

def _rpc_url() -> str:
    if config.HELIUS_KEY:
        return config.HELIUS_RPC.format(key=config.HELIUS_KEY)
    return 'https://api.mainnet-beta.solana.com'


async def _rpc(client: httpx.AsyncClient, method: str, params: list) -> dict:
    resp = await client.post(_rpc_url(), json={
        'jsonrpc': '2.0', 'id': 1, 'method': method, 'params': params
    }, timeout=10)
    resp.raise_for_status()
    return resp.json()


async def get_sol_balance(pubkey: str) -> float:
    """Returns SOL balance as a float."""
    async with httpx.AsyncClient() as client:
        data = await _rpc(client, 'getBalance', [pubkey])
    lamports = data.get('result', {}).get('value', 0)
    return lamports / config.SOL_LAMPORTS


async def get_token_balance(pubkey: str, mint: str) -> int:
    """Returns raw token balance in base units (u64).

    Derives the ATA deterministically, fetches with base64 encoding, and reads
    amount at offset 64 — same layout used for vault accounts in raydium_cpmm.py.
    More robust than jsonParsed which can silently fall back to base64 under load.
    """
    import base64, struct
    from dex.swap_tx import get_associated_token_address
    ata = get_associated_token_address(pubkey, mint)
    log.info(f'get_token_balance: ATA={ata}')
    async with httpx.AsyncClient() as client:
        data = await _rpc(client, 'getAccountInfo', [ata, {'encoding': 'base64'}])
    value = (data.get('result') or {}).get('value')
    if not value:
        log.warning(f'get_token_balance: no account data for ATA={ata} (account may not exist)')
        return 0
    raw_data = value.get('data')
    if isinstance(raw_data, list):
        raw_bytes = base64.b64decode(raw_data[0])
        log.info(f'get_token_balance: raw_bytes len={len(raw_bytes)}')
    else:
        log.warning(f'get_token_balance: unexpected data format: {type(raw_data)} val={str(raw_data)[:80]}')
        return 0
    if len(raw_bytes) < 72:
        log.warning(f'get_token_balance: raw_bytes too short ({len(raw_bytes)} bytes)')
        return 0
    amount = struct.unpack_from('<Q', raw_bytes, 64)[0]
    log.info(f'get_token_balance: amount={amount}')
    return amount


# ── Transaction signing ───────────────────────────────────────────────────────

def sign_versioned_transaction(tx_b64: str, keypair) -> bytes:
    """
    Deserialize a base64 versioned transaction from Jupiter, sign it with
    the keeper keypair, and return the signed bytes.
    """
    import base64
    from solders.transaction import VersionedTransaction  # type: ignore

    raw = base64.b64decode(tx_b64)
    tx = VersionedTransaction.from_bytes(raw)
    # solders sign: replace existing placeholder signature
    signed = VersionedTransaction(tx.message, [keypair])
    return bytes(signed)
