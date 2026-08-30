"""swarm-settler — the only component that holds the treasury private key.

It reads the settlement ledger the payment path writes to Redis
(`swarm:treasury` accumulators, via `swarm_core.x402.settle`) and, when
`SETTLEMENT_EXECUTE` is truthy, retires the owed burn slice on-chain: a
`TransferChecked` from the treasury's token account to the incinerator's, with
an SPL Memo recording the settlement, in one transaction.

With `SETTLEMENT_EXECUTE` unset it still runs — recounting the 24h window and
refreshing runway metrics — but signs nothing and needs no key. That is the
honest default: the ledger accrues, `burned_total` stays 0, and the site shows
"owed, not yet burned".
"""
from __future__ import annotations

import asyncio
import logging
import os
import sys

import redis.asyncio as aioredis

from swarm_core import tokens
from swarm_core.x402.burn import load_keypair, run_worker

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s [settler] %(levelname)s %(message)s",
)
log = logging.getLogger("swarm-settler")

REDIS_URL = os.getenv("REDIS_URL", "redis://127.0.0.1:6379")
EXECUTE = os.getenv("SETTLEMENT_EXECUTE", "").strip().lower() in ("1", "true", "yes")


def _preflight() -> None:
    # Raises if SWARM_TREASURY_ADDRESS is unset — an empty payTo would let the
    # verifier accept any transaction, and here it would misdirect a burn.
    treasury = tokens.treasury_address()
    log.info("treasury address: %s", treasury)
    log.info("project mint: %s", tokens.token_mint())
    log.info("burn address: %s", tokens.burn_address())

    if not EXECUTE:
        log.warning("SETTLEMENT_EXECUTE off — ledger only, no on-chain burns")
        return

    raw = os.getenv("SWARM_TREASURY_PRIVATE_KEY", "").strip()
    if not raw:
        sys.exit("SETTLEMENT_EXECUTE=true but SWARM_TREASURY_PRIVATE_KEY is unset")
    kp = load_keypair(raw)
    if str(kp.pubkey()) != treasury:
        sys.exit(
            f"key mismatch: SWARM_TREASURY_PRIVATE_KEY is for {kp.pubkey()}, "
            f"SWARM_TREASURY_ADDRESS is {treasury} — refusing to burn from the "
            f"wrong wallet"
        )
    log.info("treasury key verified — executing burns")


async def _main() -> None:
    _preflight()
    redis = aioredis.from_url(REDIS_URL, decode_responses=True)
    try:
        await run_worker(redis, execute=EXECUTE)
    finally:
        await redis.aclose()


if __name__ == "__main__":
    try:
        asyncio.run(_main())
    except KeyboardInterrupt:
        pass
