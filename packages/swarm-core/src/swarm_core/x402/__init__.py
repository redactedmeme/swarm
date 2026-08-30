"""x402 micropayments: verify a Solana payment, then serve the call.

The gateway in `apps/x402/` has always advertised micropayments and never
charged for anything. This package is the server half that was missing.
"""
from .middleware import PAYMENT_HEADER, payment_required_body, require_payment
from .rpc import RpcError, rpc, rpc_url
from .verify import (
    FRESHNESS_WINDOW_S,
    PaymentError,
    PaymentReceipt,
    claim_signature,
    verify_and_claim,
    verify_payment,
)

__all__ = [
    "FRESHNESS_WINDOW_S",
    "PAYMENT_HEADER",
    "PaymentError",
    "PaymentReceipt",
    "RpcError",
    "claim_signature",
    "payment_required_body",
    "require_payment",
    "rpc",
    "rpc_url",
    "verify_and_claim",
    "verify_payment",
]
