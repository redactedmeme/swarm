"""Minimal async Solana JSON-RPC client for the payment path.

`apps/arb-keeper/wallet.py` has an httpx version of this and
`apps/dashboard/serve.py` has a urllib one, but both live inside deployables
that the shared packages must not import from. This is the same three-line
pattern on aiohttp, which `swarm-core` already depends on.

Deliberately small: the payment path needs exactly two methods, and a thin
surface is easier to reason about when it is the thing standing between the
swarm and unpaid access.
"""
from __future__ import annotations

import os

import aiohttp


class RpcError(RuntimeError):
    """The RPC call failed, or returned an `error` member.

    Distinct from "the transaction is invalid": callers must not treat an
    unreachable RPC as a failed payment, or an outage becomes a free-access
    window in one direction and a lockout in the other.
    """


def rpc_url() -> str:
    """Helius when a key is configured, else whatever `SOLANA_RPC_URL` names."""
    key = os.getenv("HELIUS_API_KEY", "").strip()
    if key:
        return f"https://mainnet.helius-rpc.com/?api-key={key}"
    return os.getenv("SOLANA_RPC_URL", "https://api.mainnet-beta.solana.com")


async def rpc(
    method: str,
    params: list,
    *,
    session: aiohttp.ClientSession | None = None,
    timeout: float = 15.0,
) -> dict:
    """One JSON-RPC round trip. Returns the `result` member.

    Accepts an optional session so a long-lived server reuses its connection
    pool instead of opening a socket per verification.
    """
    payload = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
    owned = session is None
    session = session or aiohttp.ClientSession()
    try:
        async with session.post(
            rpc_url(), json=payload, timeout=aiohttp.ClientTimeout(total=timeout)
        ) as resp:
            if resp.status != 200:
                raise RpcError(f"{method}: HTTP {resp.status}")
            body = await resp.json()
    except aiohttp.ClientError as exc:
        raise RpcError(f"{method}: {exc}") from exc
    if "error" in body:
        raise RpcError(f"{method}: {body['error']}")
    return body.get("result")
