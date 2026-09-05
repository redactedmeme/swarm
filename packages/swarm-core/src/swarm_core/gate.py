"""Holder gate — prove a wallet, read its $REDACTED balance, resolve its tier.

`swarm_core.tokens` has defined `TIERS` / `tier_for` / `grants_for` since Phase 1
and nothing read them. This is the reader: a sign-a-nonce challenge that a
service (today: `apps/terminal`) uses to gate access at the `operator` tier
(1,000,000 $REDACTED → `terminal`).

The higher grants (`architect`, `monolith` → `private-agents`,
`proxy-rpm-boost`, `committee-included`) have no consumer yet, so `authorize`
records the full grant set in `gate:grants:<wallet>` (Redis, TTL'd) for a
future reader and returns `ok` only for the `terminal` grant.

Redis + `swarm_core.x402.rpc` + `cryptography` — no `solders`. Imports clean in
CI.
"""
from __future__ import annotations

import base64
import json
import logging
import os
import re
import secrets
import time
from datetime import datetime, timezone
from decimal import Decimal

from . import tokens
from .x402.rpc import RpcError, rpc

log = logging.getLogger(__name__)

NONCE_KEY = "gate:nonce:"
GRANTS_KEY = "gate:grants:"
NONCE_TTL = int(os.getenv("GATE_NONCE_TTL", "300"))
GRANTS_TTL = int(os.getenv("GATE_GRANTS_TTL", "3600"))

_B58_ALPHABET = b"123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
_B58_MAP = {c: i for i, c in enumerate(_B58_ALPHABET)}
_NONCE_LINE = re.compile(r"^nonce:\s*(\S+)\s*$", re.MULTILINE)


class GateError(Exception):
    """A challenge could not be issued or authorized. `.reason` is machine-readable."""

    def __init__(self, reason: str, detail: str = ""):
        self.reason = reason
        self.detail = detail
        super().__init__(f"{reason}: {detail}" if detail else reason)


def _b58decode(s: str) -> bytes:
    n = 0
    for ch in s.encode():
        n = n * 58 + _B58_MAP[ch]  # KeyError on a non-base58 char
    body = n.to_bytes((n.bit_length() + 7) // 8, "big") if n else b""
    pad = len(s) - len(s.lstrip("1"))
    return b"\x00" * pad + body


def _pubkey_bytes(wallet: str) -> bytes:
    """32 raw bytes of a base58 Solana address, or raise GateError."""
    try:
        raw = _b58decode(wallet.strip())
    except (KeyError, AttributeError):
        raise GateError("bad_wallet", "not a base58 address") from None
    if len(raw) != 32:
        raise GateError("bad_wallet", f"decoded to {len(raw)} bytes, expected 32")
    return raw


def challenge_message(wallet: str, nonce: str, issued_iso: str) -> str:
    return (
        "REDACTED — prove wallet ownership\n"
        f"wallet: {wallet}\n"
        f"nonce: {nonce}\n"
        f"issued: {issued_iso}\n"
        "Signing grants terminal access based on your $REDACTED balance. "
        "It moves no funds."
    )


async def issue_nonce(redis, wallet: str) -> dict:
    """Mint a single-use challenge for `wallet`. Raises GateError on a bad address."""
    _pubkey_bytes(wallet)
    nonce = secrets.token_urlsafe(24)
    issued = datetime.now(timezone.utc).isoformat(timespec="seconds")
    await redis.set(f"{NONCE_KEY}{wallet}", nonce, ex=NONCE_TTL)
    return {
        "message": challenge_message(wallet, nonce, issued),
        "nonce": nonce,
        "expires_in": NONCE_TTL,
    }


def verify_signature(wallet: str, message: str, signature_b64: str) -> bool:
    """True iff `signature_b64` is `wallet`'s ed25519 signature over `message`
    (UTF-8). Never raises."""
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

    try:
        pub = Ed25519PublicKey.from_public_bytes(_pubkey_bytes(wallet))
        sig = base64.b64decode(signature_b64, validate=True)
        pub.verify(sig, message.encode("utf-8"))
        return True
    except (InvalidSignature, GateError, ValueError, TypeError):
        return False


async def token_balance(owner: str, *, mint: str | None = None, session=None) -> Decimal | None:
    """Whole $REDACTED held by `owner`, or None if the RPC is unreachable."""
    mint = mint or tokens.token_mint()
    try:
        res = await rpc(
            "getTokenAccountsByOwner",
            [owner, {"mint": mint}, {"encoding": "jsonParsed"}],
            session=session,
        )
    except RpcError as exc:
        log.warning("gate: getTokenAccountsByOwner failed for %s: %s", owner[:8], exc)
        return None
    total = Decimal(0)
    for acc in (res or {}).get("value") or []:
        try:
            amt = acc["account"]["data"]["parsed"]["info"]["tokenAmount"]["uiAmountString"]
            total += Decimal(str(amt))
        except (KeyError, TypeError, ValueError):
            continue
    return total


async def authorize(redis, wallet: str, message: str, signature_b64: str,
                    *, required_grant: str = "terminal") -> dict:
    """Consume the nonce, verify the signature, read the balance, resolve the tier.

    Returns `{ok, wallet, balance, tier, grants, required_grant, min_required}`.
    `ok` is True when the wallet holds `required_grant` — `terminal` by default,
    so existing callers keep the operator-tier behaviour they had. `min_required`
    is the lowest threshold that actually confers that grant, so a caller can
    tell the user the real number to hold rather than the bottom of the ladder.

    Raises GateError for anything that isn't a clean allow/deny — a
    missing/mismatched nonce, a bad signature, an unreachable RPC — so the
    caller can 4xx precisely and the nonce is only spent on a real decision.
    """
    _pubkey_bytes(wallet)

    m = _NONCE_LINE.search(message or "")
    if not m:
        raise GateError("bad_message", "no nonce line")
    claimed = m.group(1)

    stored = await redis.get(f"{NONCE_KEY}{wallet}")
    if not stored or stored != claimed:
        raise GateError("nonce", "no matching challenge (expired, replayed, or wrong wallet)")

    if not verify_signature(wallet, message, signature_b64):
        # Leave the nonce in place so a genuine client can retry the signature.
        raise GateError("bad_signature", "signature does not verify for this wallet")

    bal = await token_balance(wallet)
    if bal is None:
        raise GateError("rpc_unavailable", "could not read the wallet balance")

    # Decision made — spend the nonce now so it can't be replayed.
    await redis.delete(f"{NONCE_KEY}{wallet}")

    tier = tokens.tier_for(bal)
    grants = sorted(tokens.grants_for(bal))
    await redis.hset(f"{GRANTS_KEY}{wallet}", mapping={
        "tier": tier.name if tier else "",
        "grants": json.dumps(grants),
        "balance": str(bal),
        "checked_at": str(int(time.time())),
    })
    await redis.expire(f"{GRANTS_KEY}{wallet}", GRANTS_TTL)

    return {
        "ok": required_grant in grants,
        "wallet": wallet,
        "balance": str(bal),
        "tier": tier.name if tier else None,
        "grants": grants,
        "required_grant": required_grant,
        "min_required": tokens.threshold_for_grant(required_grant),
    }
