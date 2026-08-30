"""aiohttp middleware that turns a route into a paid endpoint.

The 402 body is built to satisfy `validateStrictX402ScanSchema()` in
`apps/x402/index.js` — the strict x402scan.com shape, not just the loose one.
We already ship that validator, so conforming to the stricter of the two costs
nothing and makes the endpoints indexable by x402scan, which is free
distribution for a swarm nobody can currently discover.
"""
from __future__ import annotations

import logging
from collections.abc import Callable
from decimal import Decimal

from aiohttp import web

from .. import tokens
from .rpc import RpcError
from .verify import PaymentError, verify_and_claim

log = logging.getLogger(__name__)

X402_VERSION = 1
NETWORK = "solana"

#: Header the existing Phantom client already sends. `apps/x402/index.js`
#: forwards it; until now nothing consumed it.
PAYMENT_HEADER = "X-Payment-Signature"


def payment_required_body(
    offer_id: str,
    *,
    resource: str,
    description: str = "",
    mime_type: str = "application/json",
    reason: str | None = None,
    detail: str | None = None,
) -> dict:
    """The 402 payload: what to pay, to whom, in what, for which resource."""
    price = tokens.price_of(offer_id)
    body = {
        "x402Version": X402_VERSION,
        "accepts": [
            {
                "scheme": "exact",
                "network": NETWORK,
                "maxAmountRequired": str(tokens.to_base_units(price)),
                "resource": resource,
                "description": description or tokens.offer(offer_id).summary,
                "mimeType": mime_type,
                "payTo": tokens.treasury_address(),
                "maxTimeoutSeconds": 60,
                "asset": tokens.token_mint(),
                "extra": {
                    "offer": offer_id,
                    "priceTokens": str(price),
                    "decimals": tokens.TOKEN_DECIMALS,
                },
            }
        ],
    }
    if reason:
        body["error"] = {"reason": reason, "detail": detail or ""}
    return body


async def _safe_record(redis, receipt) -> None:
    """Account a settlement without ever failing the paid call it belongs to.

    The write is redis-only and cheap, so it runs inline rather than as a
    fire-and-forget task (which can be GC'd before it runs, swallows its own
    exceptions, and is dropped on shutdown — all "lost revenue, no trace").
    A redis blip here is survivable: `burn.py`'s reconcile loop walks inbound
    treasury transfers and replays anything `record_settlement` missed.
    """
    try:
        from .settle import record_settlement

        await record_settlement(redis, receipt.to_dict())
    except Exception:  # noqa: BLE001 — accounting must never break the payment
        log.warning(
            "settlement accounting failed for %s (payment still served)",
            receipt.signature[:16],
            exc_info=True,
        )


def require_payment(
    offer_id: str,
    *,
    redis_key: str = "redis",
    bypass: Callable[[web.Request], bool] | None = None,
    settle: bool = True,
):
    """Decorate an aiohttp handler so it serves only against a fresh payment.

    Expects `request.app[redis_key]` to be an async Redis client — the replay
    guard is not optional, so a route configured without one fails closed
    rather than quietly accepting every signature twice.

    `bypass` lets a service exempt its own callers — the agents on the mesh
    consume these endpoints constantly and charging the swarm to talk to itself
    would just move tokens between our own wallets. It must be a positive
    identity check (a shared operator token), never the absence of something.

    On success the handler can read `request["receipt"]`, which the settlement
    writer needs to record what was paid and by whom. A bypassed call leaves
    `receipt` unset, so settlement writers must treat it as optional.

    `settle` (default on) records each genuinely-paid call into the
    `swarm:treasury` ledger via `settle.record_settlement`. Turn it off only for
    a route whose payments are accounted elsewhere.
    """

    def decorator(handler):
        async def wrapped(request: web.Request) -> web.StreamResponse:
            if bypass is not None and bypass(request):
                return await handler(request)

            price = tokens.price_of(offer_id)
            resource = str(request.url.with_query(None))
            signature = (request.headers.get(PAYMENT_HEADER) or "").strip()

            if not signature:
                return web.json_response(
                    payment_required_body(offer_id, resource=resource), status=402
                )

            redis = request.app.get(redis_key)
            if redis is None:
                log.error(
                    "route %s is priced but has no redis client at app[%r]; "
                    "refusing to serve rather than skip the replay guard",
                    resource,
                    redis_key,
                )
                return web.json_response(
                    {"error": "payment verification unavailable"}, status=503
                )

            try:
                receipt = await verify_and_claim(
                    redis,
                    signature,
                    endpoint=offer_id,
                    min_amount=Decimal(price),
                )
            except PaymentError as exc:
                return web.json_response(
                    payment_required_body(
                        offer_id,
                        resource=resource,
                        reason=exc.reason,
                        detail=exc.detail,
                    ),
                    status=402,
                )
            except RpcError:
                # Our infrastructure failed, not their payment. A 402 here would
                # tell a paying caller their good payment was rejected.
                return web.json_response(
                    {"error": "payment verification temporarily unavailable"},
                    status=503,
                )

            request["receipt"] = receipt
            log.info(
                "paid call: offer=%s payer=%s amount=%s sig=%s",
                offer_id,
                receipt.payer,
                receipt.amount,
                receipt.signature[:16],
            )
            if settle:
                await _safe_record(redis, receipt)
            return await handler(request)

        wrapped.__name__ = getattr(handler, "__name__", "wrapped")
        wrapped.__doc__ = handler.__doc__
        return wrapped

    return decorator
