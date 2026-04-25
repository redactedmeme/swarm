"""
bankr_wallet.py — Bankr Wallet API client for smolting.

Provides headless, API-key-authenticated wallet operations on Base (and
cross-chain via Bankr's portfolio endpoint).  Designed to sit alongside
wallet.py (Solana) as a parallel Base/EVM wallet layer.

Required env var:
    BANKR_API_KEY — generated at bankr.bot/api (dedicated agent key)

Optional:
    BANKR_BASE_URL — defaults to https://api.bankr.bot
"""

import os
import logging
import aiohttp
from typing import Optional

logger = logging.getLogger(__name__)

BANKR_BASE_URL = os.environ.get("BANKR_BASE_URL", "https://api.bankr.bot").rstrip("/")

# USDC on Base
USDC_BASE = "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913"


def _api_key() -> Optional[str]:
    key = os.environ.get("BANKR_API_KEY", "").strip()
    return key if key else None


def _headers() -> dict:
    key = _api_key()
    if not key:
        raise RuntimeError("BANKR_API_KEY not set")
    return {"X-API-Key": key, "Content-Type": "application/json"}


# ── Low-level request helpers ─────────────────────────────────────────────────

async def _get(path: str, params: Optional[dict] = None) -> Optional[dict]:
    url = f"{BANKR_BASE_URL}{path}"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                url,
                headers=_headers(),
                params=params or {},
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                body = await resp.json()
                if resp.status >= 400:
                    logger.warning(f"[bankr] GET {path} → {resp.status}: {body}")
                    return None
                return body
    except Exception as e:
        logger.warning(f"[bankr] GET {path} error: {e}")
        return None


async def _post(path: str, payload: dict) -> Optional[dict]:
    url = f"{BANKR_BASE_URL}{path}"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                url,
                headers=_headers(),
                json=payload,
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                body = await resp.json()
                if resp.status >= 400:
                    logger.warning(f"[bankr] POST {path} → {resp.status}: {body}")
                    return None
                return body
    except Exception as e:
        logger.warning(f"[bankr] POST {path} error: {e}")
        return None


# ── Wallet info ───────────────────────────────────────────────────────────────

async def get_wallet_info() -> Optional[dict]:
    """Return wallet metadata (addresses, socials, club status)."""
    return await _get("/wallet/me")


async def get_base_address() -> Optional[str]:
    """Return the EVM/Base address for this API key's wallet."""
    info = await get_wallet_info()
    if not info:
        return None
    # Bankr returns evmAddress or address at top level
    return info.get("evmAddress") or info.get("address")


# ── Portfolio / balances ──────────────────────────────────────────────────────

async def get_portfolio(chains: str = "base", include_low_value: bool = False) -> Optional[dict]:
    """
    Return token balances and USD values across specified chains.

    chains: comma-separated e.g. "base,solana"
    """
    params = {"chains": chains}
    if include_low_value:
        params["showLowValueTokens"] = "true"
    return await _get("/wallet/portfolio", params=params)


async def get_base_balance() -> dict:
    """
    Return a summary of Base chain balances.

    Returns dict with: address, eth_balance, usdc_balance, total_usd, ready.
    """
    address = await get_base_address()
    if not address:
        return {"ready": False, "address": None, "eth_balance": None, "usdc_balance": None, "total_usd": None}

    portfolio = await get_portfolio(chains="base")
    if not portfolio:
        return {"ready": True, "address": address, "eth_balance": None, "usdc_balance": None, "total_usd": None}

    eth_balance = None
    usdc_balance = None
    total_usd = 0.0

    tokens = portfolio.get("tokens") or portfolio.get("balances") or []
    for token in tokens:
        symbol = (token.get("symbol") or "").upper()
        usd_val = token.get("usdValue") or token.get("valueUsd") or 0
        amount = token.get("amount") or token.get("balance") or 0
        total_usd += float(usd_val)
        if symbol == "ETH":
            eth_balance = float(amount)
        elif symbol == "USDC":
            usdc_balance = float(amount)

    return {
        "ready": True,
        "address": address,
        "eth_balance": eth_balance,
        "usdc_balance": usdc_balance,
        "total_usd": round(total_usd, 2),
    }


# ── Transfers ─────────────────────────────────────────────────────────────────

async def transfer_usdc(recipient: str, amount: str) -> Optional[dict]:
    """
    Send USDC on Base.

    amount: human-readable string e.g. "10" for 10 USDC
    Returns {"success": True, "txHash": "0x..."} or None on failure.
    """
    return await _post("/wallet/transfer", {
        "tokenAddress": USDC_BASE,
        "recipientAddress": recipient,
        "amount": amount,
        "isNativeToken": False,
    })


async def transfer_eth(recipient: str, amount: str) -> Optional[dict]:
    """
    Send native ETH on Base.

    amount: human-readable string e.g. "0.01"
    """
    return await _post("/wallet/transfer", {
        "tokenAddress": "",
        "recipientAddress": recipient,
        "amount": amount,
        "isNativeToken": True,
    })


# ── Agent prompt (natural language) ──────────────────────────────────────────

async def agent_prompt(prompt: str) -> Optional[str]:
    """
    Submit a natural language command to the Bankr agent (async job).

    Returns job_id for polling, or None on failure.
    Use agent_job_result(job_id) to retrieve the completed response.
    """
    result = await _post("/agent/prompt", {"prompt": prompt})
    if result and result.get("success"):
        return result.get("jobId")
    return None


async def agent_job_result(job_id: str) -> Optional[dict]:
    """Poll /agent/job/{jobId} for completion."""
    return await _get(f"/agent/job/{job_id}")


async def agent_run(prompt: str, max_polls: int = 12, poll_interval: float = 5.0) -> Optional[str]:
    """
    Submit a natural language prompt and wait for the result.

    Polls up to max_polls times with poll_interval seconds between each.
    Returns the agent's text response, or None on failure/timeout.
    """
    import asyncio

    job_id = await agent_prompt(prompt)
    if not job_id:
        logger.warning("[bankr] agent_prompt returned no job_id")
        return None

    for _ in range(max_polls):
        await asyncio.sleep(poll_interval)
        result = await agent_job_result(job_id)
        if not result:
            continue
        status = result.get("status")
        if status == "completed":
            return result.get("response") or result.get("message")
        if status in ("failed", "cancelled"):
            logger.warning(f"[bankr] job {job_id} ended with status: {status}")
            return None

    logger.warning(f"[bankr] job {job_id} timed out after {max_polls} polls")
    return None


# ── Wallet summary (mirrors wallet.py interface) ──────────────────────────────

async def get_wallet_summary() -> dict:
    """
    Unified summary matching wallet.py's get_wallet_summary() shape.

    Returns: ready, address, eth_balance, usdc_balance, total_usd.
    """
    if not _api_key():
        return {"ready": False, "address": None, "eth_balance": None, "usdc_balance": None, "total_usd": None}
    return await get_base_balance()
