"""
wallet.py — smolting's Solana wallet.

Reads SOLANA_PRIVATE_KEY (base58-encoded 64-byte Solana keypair).
No external Solana libraries needed — uses inline base58 + Solana JSON-RPC.

Public address: FaZMc2NXbMFiiaFuvzBJtrS66hM3kaedKXEdxFZNPQ9c
"""

import os
import logging
import aiohttp
from typing import Optional

logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

SOLANA_RPC = "https://api.mainnet-beta.solana.com"
REDACTED_MINT = "9mtKd1o8Ht7F1daumKgs5D8EdVyopWBfYQwNmMojpump"  # V2
TOKEN_PROGRAM = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"

_B58_ALPHABET = b"123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
_B58_MAP = {c: i for i, c in enumerate(_B58_ALPHABET)}


# ── Base58 ────────────────────────────────────────────────────────────────────

def _b58decode(s: str) -> bytes:
    n = 0
    for char in s.encode():
        n = n * 58 + _B58_MAP[char]
    result = n.to_bytes((n.bit_length() + 7) // 8, "big") if n else b""
    leading = len(s) - len(s.lstrip("1"))
    return b"\x00" * leading + result


def _b58encode(data: bytes) -> str:
    n = int.from_bytes(data, "big")
    result = []
    while n > 0:
        n, r = divmod(n, 58)
        result.append(_B58_ALPHABET[r:r+1])
    result.extend(b"1" * (len(data) - len(data.lstrip(b"\x00"))))
    return b"".join(reversed(result)).decode()


# ── Key loading ───────────────────────────────────────────────────────────────

def _load_keypair() -> Optional[tuple[bytes, str]]:
    """
    Returns (private_seed_32_bytes, public_address_b58) or None.
    Accepts:
      - 64-byte base58 keypair (standard Solana/Phantom export)
      - 32-byte base58 seed only
    """
    raw = os.environ.get("SOLANA_PRIVATE_KEY", "").strip()
    if not raw:
        return None
    try:
        decoded = _b58decode(raw)
        if len(decoded) == 64:
            seed = decoded[:32]
            pubkey_bytes = decoded[32:]
        elif len(decoded) == 32:
            # Seed only — derive public key
            from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
            from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
            priv = Ed25519PrivateKey.from_private_bytes(decoded)
            pubkey_bytes = priv.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
            seed = decoded
        else:
            logger.error(f"[wallet] Unexpected key length: {len(decoded)} bytes")
            return None
        return seed, _b58encode(pubkey_bytes)
    except Exception as e:
        logger.error(f"[wallet] Failed to load keypair: {e}")
        return None


def get_public_address() -> Optional[str]:
    """Return smolting's public Solana address, or None if key not set."""
    kp = _load_keypair()
    return kp[1] if kp else None


# ── RPC helpers ───────────────────────────────────────────────────────────────

async def _rpc(method: str, params: list) -> Optional[dict]:
    payload = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                SOLANA_RPC,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status == 200:
                    return await resp.json()
    except Exception as e:
        logger.warning(f"[wallet] RPC {method} error: {e}")
    return None


async def get_sol_balance(address: str) -> Optional[float]:
    """Return SOL balance for address (in SOL, not lamports)."""
    result = await _rpc("getBalance", [address, {"commitment": "confirmed"}])
    if result and "result" in result:
        lamports = result["result"].get("value", 0)
        return lamports / 1_000_000_000
    return None


async def get_token_balance(address: str, mint: str = REDACTED_MINT) -> Optional[float]:
    """Return SPL token balance for a given mint."""
    result = await _rpc(
        "getTokenAccountsByOwner",
        [
            address,
            {"mint": mint},
            {"encoding": "jsonParsed", "commitment": "confirmed"},
        ],
    )
    if not result or "result" not in result:
        return None
    accounts = result["result"].get("value", [])
    if not accounts:
        return 0.0
    # Sum across all token accounts for this mint (usually just one)
    total = 0.0
    for acct in accounts:
        info = (
            acct.get("account", {})
            .get("data", {})
            .get("parsed", {})
            .get("info", {})
            .get("tokenAmount", {})
        )
        amt = info.get("uiAmount")
        if amt is not None:
            total += float(amt)
    return total


async def get_wallet_summary() -> dict:
    """
    Return a dict with: address, sol_balance, redacted_balance, ready.
    All fields present; numeric fields are None if fetch failed.
    """
    address = get_public_address()
    if not address:
        return {"ready": False, "address": None, "sol_balance": None, "redacted_balance": None}

    import asyncio
    sol, redacted = await asyncio.gather(
        get_sol_balance(address),
        get_token_balance(address, REDACTED_MINT),
        return_exceptions=True,
    )
    return {
        "ready": True,
        "address": address,
        "sol_balance": sol if isinstance(sol, float) else None,
        "redacted_balance": redacted if isinstance(redacted, float) else None,
    }
