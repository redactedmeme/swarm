"""On-chain verification of an x402 payment.

This is the file the whole flywheel rests on. `apps/x402/public/wallet-connector.js`
has always built `x402-payment:{sig}:{ts}` headers and `apps/x402/index.js` has
always forwarded the `x-payment-*` headers, but nothing anywhere in the repo
ever *checked* them — `grep "status(402)"` across the gateway returned nothing.
So the swarm has six live services and has never charged for one call.

`verify_payment` closes that. It answers exactly one question: did this
signature move at least this much of our mint into our treasury, recently, and
has it not already been spent?

Balances are read from `meta.pre/postTokenBalances` rather than by decoding
instructions. That way a payment counts however it was routed — a plain
transfer, a `transferChecked`, or a swap that lands tokens in the treasury as
its final leg — because what is verified is the treasury's balance delta, which
is the thing we actually care about.
"""
from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, asdict
from decimal import Decimal

import aiohttp

from .. import tokens
from .rpc import RpcError, rpc

log = logging.getLogger(__name__)

#: How old a payment signature may be and still buy a call. Long enough to
#: absorb Solana confirmation plus a slow client, short enough that the replay
#: guard's TTL stays cheap.
FRESHNESS_WINDOW_S = int(os.getenv("X402_FRESHNESS_WINDOW_S", "300"))

#: Redis key namespace for spent signatures.
SPENT_PREFIX = os.getenv("X402_SPENT_PREFIX", "x402:spent:")


class PaymentError(Exception):
    """A payment was presented and is not acceptable.

    Carries a machine-readable `reason` so the 402 body can tell the caller
    what to fix without leaking verification internals.
    """

    def __init__(self, reason: str, detail: str = ""):
        self.reason = reason
        self.detail = detail
        super().__init__(f"{reason}: {detail}" if detail else reason)


@dataclass(frozen=True)
class PaymentReceipt:
    """Proof that a specific on-chain transfer paid for a specific call."""

    signature: str
    payer: str
    amount: Decimal  # whole $REDACTED
    amount_raw: int  # base units, as seen on chain
    mint: str
    endpoint: str
    block_time: int

    def to_dict(self) -> dict:
        d = asdict(self)
        d["amount"] = str(self.amount)
        return d


def _treasury_delta(meta: dict, treasury: str, mint: str) -> int:
    """Base units of `mint` credited to `treasury` by this transaction.

    Pre-balances omit accounts that did not exist beforehand, so a first-ever
    payment into a fresh ATA has no `pre` entry at all — treated as zero rather
    than as missing data.
    """
    def _index(entries: list[dict]) -> dict[int, int]:
        out: dict[int, int] = {}
        for e in entries or []:
            if e.get("mint") != mint or e.get("owner") != treasury:
                continue
            raw = (e.get("uiTokenAmount") or {}).get("amount")
            if raw is None:
                continue
            out[e.get("accountIndex")] = int(raw)
        return out

    pre = _index(meta.get("preTokenBalances"))
    post = _index(meta.get("postTokenBalances"))
    return sum(amount - pre.get(idx, 0) for idx, amount in post.items())


async def verify_payment(
    signature: str,
    *,
    endpoint: str,
    min_amount: int | Decimal,
    treasury: str | None = None,
    mint: str | None = None,
    session: aiohttp.ClientSession | None = None,
) -> PaymentReceipt:
    """Verify one payment signature, or raise `PaymentError`.

    `min_amount` is in whole $REDACTED; the comparison happens in base units so
    no float ever touches an on-chain quantity.

    Does *not* mark the signature spent — call `claim_signature` for that, and
    call it before serving the work. The two are separate so a caller can check
    a payment without consuming it (useful for quoting and for tests).
    """
    treasury = treasury or tokens.treasury_address()
    mint = mint or tokens.token_mint()

    if not signature or len(signature) < 64:
        raise PaymentError("malformed_signature", "not a base58 Solana signature")

    try:
        tx = await rpc(
            "getTransaction",
            [
                signature,
                {
                    "encoding": "jsonParsed",
                    "commitment": "confirmed",
                    "maxSupportedTransactionVersion": 0,
                },
            ],
            session=session,
        )
    except RpcError as exc:
        # An unreachable RPC is our problem, not the caller's. Surfacing it as a
        # payment failure would tell a paying user their good payment was bad.
        log.warning("payment verification RPC failed for %s: %s", signature, exc)
        raise

    if tx is None:
        raise PaymentError("not_found", "transaction not found or not yet confirmed")

    meta = tx.get("meta") or {}
    if meta.get("err") is not None:
        raise PaymentError("failed_transaction", str(meta["err"]))

    block_time = tx.get("blockTime")
    if block_time is None:
        raise PaymentError("unconfirmed", "transaction has no block time yet")
    age = time.time() - block_time
    if age > FRESHNESS_WINDOW_S:
        raise PaymentError(
            "stale", f"payment is {int(age)}s old, limit is {FRESHNESS_WINDOW_S}s"
        )

    delta_raw = _treasury_delta(meta, treasury, mint)
    if delta_raw <= 0:
        raise PaymentError(
            "wrong_recipient",
            "transaction moved none of the expected mint into the treasury",
        )

    required_raw = tokens.to_base_units(min_amount)
    if delta_raw < required_raw:
        raise PaymentError(
            "insufficient",
            f"paid {tokens.from_base_units(delta_raw)}, "
            f"need {tokens.from_base_units(required_raw)}",
        )

    # The fee payer is the first account key and is always a signer — the right
    # identity to credit, since it is the account that authorised the spend.
    keys = (tx.get("transaction") or {}).get("message", {}).get("accountKeys") or []
    payer = ""
    if keys:
        first = keys[0]
        payer = first.get("pubkey", "") if isinstance(first, dict) else str(first)

    return PaymentReceipt(
        signature=signature,
        payer=payer,
        amount=tokens.from_base_units(delta_raw),
        amount_raw=delta_raw,
        mint=mint,
        endpoint=endpoint,
        block_time=int(block_time),
    )


async def claim_signature(redis, signature: str) -> bool:
    """Atomically mark a signature spent. False if it was already claimed.

    This is the security-critical line in the payment path: without it one
    valid payment buys unlimited calls, because the same signature verifies
    correctly every time it is presented.

    TTL runs to twice the freshness window — past that the staleness check
    rejects the signature anyway, so remembering it longer only costs memory.
    """
    key = f"{SPENT_PREFIX}{signature}"
    claimed = await redis.set(key, int(time.time()), nx=True, ex=FRESHNESS_WINDOW_S * 2)
    return bool(claimed)


async def verify_and_claim(
    redis,
    signature: str,
    *,
    endpoint: str,
    min_amount: int | Decimal,
    treasury: str | None = None,
    mint: str | None = None,
    session: aiohttp.ClientSession | None = None,
) -> PaymentReceipt:
    """Verify a payment and consume it in one step.

    Claims *after* verifying, so a rejected payment does not burn its own
    signature — otherwise a caller who paid too little could never retry by
    topping up, and an attacker could grief a pending payment by presenting it
    early against the wrong endpoint.
    """
    receipt = await verify_payment(
        signature,
        endpoint=endpoint,
        min_amount=min_amount,
        treasury=treasury,
        mint=mint,
        session=session,
    )
    if not await claim_signature(redis, signature):
        raise PaymentError("replayed", "this payment has already been spent")
    return receipt
