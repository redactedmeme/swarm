"""Per-client $REDACTED credit balance — Phase 2 of the token flywheel.

The proxy meters usage exactly (`_record_usage`) but has never charged for it.
This module debits a Redis balance per request and, when `CREDITS_ENFORCE` is
on, refuses a call from a client whose balance has run out.

Deliberately self-contained: `apps/proxy` builds from its own directory and
cannot import `swarm_core`. It shares exactly one number with
`swarm_core.tokens` — `CREDITS_PER_1K_TOKENS` — by reading the *same env var
name*, so a single value on the box keeps them in step. Deposits (crediting the
balance) and turning spend into on-chain burns are `apps/settler`'s job, via
`swarm_core.x402.credits`.

Best-effort, like `_record_usage`: a Redis blip never breaks a request. When
`CREDITS_ENFORCE` is off the balance still moves and a would-be refusal is
logged, so the whole loop is observable before it bites.
"""
from __future__ import annotations

import json
import logging
import os
import time
import uuid

logger = logging.getLogger(__name__)

#: $REDACTED per 1k LLM tokens. Same env var as swarm_core.tokens.
RATE = int(os.getenv("CREDITS_PER_1K_TOKENS", "100"))
#: Whole tokens -> base units. Matches swarm_core.tokens.TOKEN_DECIMALS.
_DECIMALS = int(os.getenv("PROJECT_TOKEN_DECIMALS", "6"))
_UNIT = 10 ** _DECIMALS

ENFORCE = os.getenv("CREDITS_ENFORCE", "").strip().lower() in ("1", "true", "yes")
#: Client names never hard-blocked (the swarm's own bots). They still debit, so
#: usage shows the swarm's own inference cost as a real (negative) balance.
EXEMPT = {
    c.strip().lower()
    for c in os.getenv("CREDITS_EXEMPT", "").split(",")
    if c.strip()
}
TOPUP_HINT = os.getenv(
    "CREDITS_TOPUP_HINT",
    "Send $REDACTED to the treasury with memo 'redacted-credits:<your-client>'. "
    "See https://redacted.meme/api/swarm and docs/TOKENOMICS.md.",
)

BALANCE_PREFIX = "credits:balance:"
DEBITED_PREFIX = "credits:debited:"
SPEND_QUEUE_KEY = "credits:spend:queue"

_warn_seen: dict[str, float] = {}


def _to_base_units(whole: float) -> int:
    return int(round(whole * _UNIT))


async def check(redis, client: str) -> tuple[bool, float]:
    """(allowed, balance). Allowed unless enforcement is on, the client is not
    exempt, and the balance is exhausted. Fails open on a Redis error."""
    try:
        raw = await redis.get(f"{BALANCE_PREFIX}{client}")
        balance = float(raw) if raw not in (None, "") else 0.0
    except Exception as e:  # noqa: BLE001 — never break a request on a Redis blip
        logger.debug("[credits] balance read failed for %s: %s", client, e)
        return True, 0.0

    if not ENFORCE or client in EXEMPT:
        # Not blocked — but if the balance is underwater, say so (rate-limited)
        # so the loop is visible before enforcement is turned on.
        if balance <= 0:
            now = time.monotonic()
            if now - _warn_seen.get(client, 0) > 60:
                _warn_seen[client] = now
                logger.info("[credits] would 402 %s (balance %.4f, enforce=%s exempt=%s)",
                            client, balance, ENFORCE, client in EXEMPT)
        return True, balance

    return balance > 0, balance


async def debit(redis, client: str, prompt_tokens: int, completion_tokens: int) -> float:
    """Charge a completed request and queue the spend for on-chain settlement.
    Returns the new balance (0.0 on a Redis error). Never raises."""
    tokens_used = max(0, int(prompt_tokens)) + max(0, int(completion_tokens))
    if tokens_used == 0:
        return 0.0
    amount = tokens_used / 1000 * RATE
    base_units = _to_base_units(amount)
    nonce = f"{client}:{time.time_ns()}:{uuid.uuid4().hex[:8]}"
    entry = json.dumps({
        "client": client,
        "tokens": tokens_used,
        "redacted": amount,
        "base_units": base_units,
        "nonce": nonce,
        "ts": int(time.time()),
    })
    try:
        pipe = redis.pipeline()
        pipe.incrbyfloat(f"{BALANCE_PREFIX}{client}", -amount)
        pipe.incrbyfloat(f"{DEBITED_PREFIX}{client}", amount)
        pipe.lpush(SPEND_QUEUE_KEY, entry)
        results = await pipe.execute()
        return float(results[0])
    except Exception as e:  # noqa: BLE001
        logger.debug("[credits] debit failed for %s: %s", client, e)
        return 0.0


async def balances(redis, clients: list[str]) -> dict[str, dict]:
    """{client: {balance, debited}} for the /usage endpoint."""
    out: dict[str, dict] = {}
    for c in clients:
        try:
            bal = await redis.get(f"{BALANCE_PREFIX}{c}")
            deb = await redis.get(f"{DEBITED_PREFIX}{c}")
        except Exception:  # noqa: BLE001
            continue
        if bal is None and deb is None:
            continue
        out[c] = {
            "balance": round(float(bal), 6) if bal not in (None, "") else 0.0,
            "debited": round(float(deb), 6) if deb not in (None, "") else 0.0,
        }
    return out


def insufficient_body(balance: float) -> dict:
    """The 402 body for an exhausted client."""
    return {
        "error": {
            "message": "Insufficient $REDACTED credits — top up to continue",
            "type": "insufficient_credits",
            "balance": round(balance, 6),
            "top_up": TOPUP_HINT,
        }
    }
