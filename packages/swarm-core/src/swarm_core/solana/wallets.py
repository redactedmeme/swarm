"""Read-only view over the per-agent wallets: on-chain balances + a manifest.

RPC goes through ``swarm_core.x402.rpc`` (Helius-aware, aiohttp) - the same
client the payment path uses. Nothing here signs or sends.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Optional

from swarm_core.x402 import rpc as _rpc

from . import LIVE_WALLET_AGENTS
from . import keystore

log = logging.getLogger(__name__)

_LAMPORTS_PER_SOL = 1_000_000_000


async def _sol_balance(address: str, *, session=None) -> float:
    res = await _rpc.rpc("getBalance", [address], session=session)
    lamports = (res or {}).get("value", 0) if isinstance(res, dict) else (res or 0)
    return lamports / _LAMPORTS_PER_SOL


async def _spl_balance(owner: str, mint: str, *, session=None) -> float:
    try:
        res = await _rpc.rpc(
            "getTokenAccountsByOwner",
            [owner, {"mint": mint}, {"encoding": "jsonParsed"}],
            session=session,
        )
    except _rpc.RpcError as exc:
        log.debug("[wallets] token balance rpc failed for %s: %s", owner, exc)
        return 0.0
    total = 0.0
    for acc in (res or {}).get("value", []):
        info = acc["account"]["data"]["parsed"]["info"]["tokenAmount"]
        total += float(info.get("uiAmount") or 0.0)
    return total


def _token_mint() -> Optional[str]:
    try:
        from swarm_core.tokens import token_mint

        return token_mint()
    except Exception:
        return None


async def agent_balances(agent: str, *, session=None) -> dict:
    """``{"agent", "address", "sol", "redacted"}`` for one agent. ``sol`` /
    ``redacted`` are ``None`` when the address is unknown or the RPC failed."""
    address = keystore.get_address(agent)
    out = {"agent": agent, "address": address, "sol": None, "redacted": None}
    if not address:
        return out
    mint = _token_mint()
    try:
        out["sol"] = await _sol_balance(address, session=session)
        if mint:
            out["redacted"] = await _spl_balance(address, mint, session=session)
    except _rpc.RpcError as exc:
        log.warning("[wallets] balance lookup failed for %s: %s", agent, exc)
    return out


async def manifest_async(agents=LIVE_WALLET_AGENTS) -> list[dict]:
    import aiohttp

    known = keystore.all_addresses()
    async with aiohttp.ClientSession() as session:
        rows = await asyncio.gather(
            *(agent_balances(a, session=session) for a in agents if a in known)
        )
    return list(rows)


def manifest(agents=LIVE_WALLET_AGENTS) -> list[dict]:
    """Blocking wrapper around :func:`manifest_async` for CLI use."""
    return asyncio.run(manifest_async(agents))


def address_manifest() -> dict[str, str]:
    """Addresses only - safe to write to a world-readable file."""
    return keystore.all_addresses()
