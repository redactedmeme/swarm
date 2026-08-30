"""Settlement accounting: split a verified payment, record it, never touch a key.

`verify.py` proves a payment landed. This module is what happens next: the
amount is divided burn / compute / rewards per `tokens.revenue_split()`, the
slices are accumulated in the Redis hash `swarm:treasury`, and the payment is
appended to a capped feed. `apps/status` already *reads* that hash
(`burned_total`, `settlements_24h`, `last_settlement_sig`); this is the writer it
was waiting for.

Deliberately redis-only — **no `solders`, no chain calls**. It runs inline in
the payment middleware, so it has to be as cheap as the `claim_signature` SET
that path already awaits, and it has to import cleanly in CI where the `solana`
extra is not installed. The on-chain half (actually retiring the burn slice)
lives in `burn.py`, which the standalone `apps/settler` service runs.

Accounting model: every field here is a **monotonic accumulator** written by
exactly one party. `record_settlement` only ever `HINCRBY`s `*_accrued`;
`burn.py` only ever `HINCRBY`s `burn_settled`. "How much is owed to the burn"
is *derived* (`burn_accrued - burn_settled`), never a counter that two sides
mutate — that would be a lost-update bug the first time anything raced.
"""
from __future__ import annotations

import json
import logging
import os
import time

from .. import tokens

log = logging.getLogger(__name__)

#: The hash `apps/status.app._treasury` reads. Keep the name in step with it.
TREASURY_KEY = os.getenv("TREASURY_KEY", "swarm:treasury")

#: Payment signatures already accounted for. The idempotency guard: a settlement
#: can be re-delivered (middleware retry, worker restart, the chain-reconcile
#: backstop in `burn.py`) and must not double-count revenue.
SEEN_KEY = os.getenv("X402_SETTLED_SEEN_KEY", "swarm:settlements:seen")

#: Sorted set of settlement signatures scored by block time, trimmed to a 24h
#: window by `recount_24h`. Backs the `settlements_24h` figure.
SETTLEMENTS_TS_KEY = os.getenv("X402_SETTLEMENTS_TS_KEY", "swarm:settlements:ts")

#: Capped list of recent settlement records (newest first) for the site feed.
SETTLEMENTS_LOG_KEY = os.getenv("X402_SETTLEMENTS_LOG_KEY", "swarm:settlements:log")
LOG_MAX = int(os.getenv("SETTLEMENTS_LOG_MAX", "50"))

_runway_none_warned = False


def compute_split(amount_raw: int) -> tuple[int, int, int]:
    """Divide `amount_raw` base units into (burn, compute, rewards).

    `compute` and `rewards` are floored; **burn absorbs the integer remainder**
    so the three slices sum to exactly `amount_raw` with no base unit lost, and
    the dust favours the irreversible, custody-free slice.
    """
    if amount_raw < 0:
        raise ValueError(f"amount_raw must be non-negative, got {amount_raw}")
    split = tokens.revenue_split()
    compute = amount_raw * split.compute // 100
    rewards = amount_raw * split.rewards // 100
    burn = amount_raw - compute - rewards
    return burn, compute, rewards


def _cap_days() -> int:
    return getattr(tokens, "COMPUTE_RUNWAY_CAP_DAYS", 90)


def apply_runway_cap(
    compute_slice: int, runway_days: float | None, cap_days: int
) -> tuple[int, int]:
    """Roll the compute slice into the burn once the treasury is over-funded.

    Returns `(compute_kept, overflow_to_burn)`. The check is binary rather than
    proportional: computing "how far this one payment pushes the treasury past
    the cap" would need the treasury's live balance in the payment hot path,
    which is exactly the price-oracle-in-the-auth-path fragility the tokenomics
    doc calls out. So: already past `cap_days` of runway → the whole compute
    slice burns; otherwise compute keeps it.

    `runway_days is None` (the metrics loop has not populated it yet, or the
    proxy is unreachable) → pass through. Starving compute on missing data is
    the wrong failure direction — a swarm with no inference budget produces
    nothing to burn against.
    """
    global _runway_none_warned
    if runway_days is None:
        if not _runway_none_warned:
            log.info(
                "runway_days unset — compute slice passes through uncapped "
                "until the metrics loop populates it"
            )
            _runway_none_warned = True
        return compute_slice, 0
    if runway_days > cap_days:
        return 0, compute_slice
    return compute_slice, 0


async def record_settlement(redis, receipt: dict) -> bool:
    """Account one verified payment. Returns False if it was already recorded.

    `receipt` is `PaymentReceipt.to_dict()` — needs `signature` and `amount_raw`
    at minimum. Idempotent on the signature: a duplicate is a no-op.

    The guard is a `SISMEMBER` fast-path plus a `SADD` *inside* the same
    `MULTI/EXEC` as the accumulators, so if the transaction fails mid-flight
    nothing commits and the signature stays un-seen for the reconcile backstop
    to retry. A malformed receipt raises before any write.
    """
    sig = receipt.get("signature")
    if not sig or "amount_raw" not in receipt:
        raise ValueError("malformed receipt: needs 'signature' and 'amount_raw'")
    amount_raw = int(receipt["amount_raw"])

    if await redis.sismember(SEEN_KEY, sig):
        return False

    burn, compute, rewards = compute_split(amount_raw)

    raw_runway = await redis.hget(TREASURY_KEY, "runway_days")
    runway_days = None
    if raw_runway not in (None, ""):
        try:
            runway_days = float(raw_runway)
        except (TypeError, ValueError):
            runway_days = None
    compute, overflow = apply_runway_cap(compute, runway_days, _cap_days())
    burn += overflow

    block_time = int(receipt.get("block_time") or time.time())
    entry = json.dumps(
        {
            "sig": sig,
            "payer": receipt.get("payer", ""),
            "endpoint": receipt.get("endpoint", ""),
            "amount_raw": amount_raw,
            "burn": burn,
            "compute": compute,
            "rewards": rewards,
            "ts": block_time,
        }
    )

    pipe = redis.pipeline(transaction=True)
    pipe.sadd(SEEN_KEY, sig)
    pipe.hincrby(TREASURY_KEY, "revenue_total", amount_raw)
    pipe.hincrby(TREASURY_KEY, "burn_accrued", burn)
    pipe.hincrby(TREASURY_KEY, "compute_accrued", compute)
    pipe.hincrby(TREASURY_KEY, "rewards_accrued", rewards)
    pipe.hincrby(TREASURY_KEY, "settlements_total", 1)
    pipe.hset(TREASURY_KEY, "last_settlement_sig", sig)
    pipe.zadd(SETTLEMENTS_TS_KEY, {sig: block_time})
    pipe.lpush(SETTLEMENTS_LOG_KEY, entry)
    pipe.ltrim(SETTLEMENTS_LOG_KEY, 0, LOG_MAX - 1)
    await pipe.execute()

    log.info(
        "settled %s: revenue=%d burn=%d compute=%d rewards=%d",
        sig[:16], amount_raw, burn, compute, rewards,
    )
    return True


async def recount_24h(redis, now: float | None = None) -> int:
    """Trim the settlements zset to the last 24h and publish the count.

    Idempotent and cheap — safe to call every worker tick.
    """
    now = time.time() if now is None else now
    cutoff = now - 86400
    await redis.zremrangebyscore(SETTLEMENTS_TS_KEY, "-inf", f"({cutoff}")
    count = await redis.zcard(SETTLEMENTS_TS_KEY)
    await redis.hset(TREASURY_KEY, "settlements_24h", count)
    return count


def owed_burn(hash_fields: dict) -> int:
    """Base units accrued to the burn but not yet retired on-chain.

    `hash_fields` is an `HGETALL` of `swarm:treasury`. `burned_total` is the
    single canonical "retired on chain" counter (the name `apps/status` reads);
    subtract a burn that is mid-flight (`burn_pending_amount`) too, so the
    worker does not queue a second one for the same debt.
    """
    accrued = int(hash_fields.get("burn_accrued", 0) or 0)
    burned = int(hash_fields.get("burned_total", 0) or 0)
    pending = int(hash_fields.get("burn_pending_amount", 0) or 0)
    return max(0, accrued - burned - pending)
