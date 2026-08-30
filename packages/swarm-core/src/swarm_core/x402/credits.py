"""Credit deposits and proxy-spend settlement — the settler's half of Phase 2.

`apps/proxy` can't import `swarm_core` (it builds standalone), so it keeps a
plain Redis balance and pushes what it spends to `credits:spend:queue`. This
module — run by `apps/settler`, which has both `swarm_core` and Solana RPC —
does the two things the proxy can't:

* **`credit_deposits`** — a top-up is a `$REDACTED` transfer to the treasury
  carrying an SPL Memo `redacted-credits:<client>`. Parse the memo, credit
  `credits:balance:<client>` by the on-chain delta, and mark the signature so
  `burn.reconcile_chain` doesn't *also* record it as a burn-split settlement (a
  deposit is prepayment, not a completed job — the burn happens as the credit
  is spent).

* **`drain_spend_queue`** — each proxied inference the proxy debited becomes a
  settlement here, so proxied revenue flows through the same 50/30/20 split and
  burn as any other paid job. The signature is synthetic and
  `record_settlement` is idempotent on it, so a crash mid-drain is safe.

Redis + `rpc` only — no `solders`. Imports clean in CI without the `solana`
extra.
"""
from __future__ import annotations

import json
import logging
import os
import re
import time

from .. import tokens
from . import settle
from .rpc import RpcError, rpc
from .verify import _treasury_delta

#: SPL Memo program (same as `burn.MEMO_PROGRAM_ID`; duplicated here to keep the
#: import graph acyclic — `burn` imports this module for the worker wiring).
MEMO_PROGRAM_ID = "MemoSq4gqABAXKb96qnH8TysNcWxMyWCqXgDLGmfcHr"

log = logging.getLogger(__name__)

#: A deposit's memo must start with this for the client name to follow.
DEPOSIT_MEMO_PREFIX = os.getenv("CREDITS_DEPOSIT_MEMO_PREFIX", "redacted-credits:")

BALANCE_PREFIX = "credits:balance:"
SPEND_QUEUE_KEY = os.getenv("CREDITS_SPEND_QUEUE_KEY", "credits:spend:queue")
DEPOSITS_SEEN_KEY = os.getenv("CREDITS_DEPOSITS_SEEN_KEY", "credits:deposits:seen")
DEPOSITS_LOG_KEY = os.getenv("CREDITS_DEPOSITS_LOG_KEY", "credits:deposits:log")
DEPOSITS_LOG_MAX = int(os.getenv("CREDITS_DEPOSITS_LOG_MAX", "50"))

_CLIENT_RE = re.compile(r"[^a-z0-9_.-]+")


def _sanitize_client(name: str) -> str:
    """Same shape as the proxy's `_sanitize_client` so a memo names the same
    bucket the proxy debits."""
    s = _CLIENT_RE.sub("-", (name or "").strip().lower())[:64].strip("-")
    return s or "unknown"


def _memo_of(tx: dict) -> str | None:
    """The SPL Memo string in a jsonParsed `getTransaction`, or None.

    Prefers the parsed instruction; falls back to the `Program log: Memo ...`
    line, which is where a memo shows up when the tx isn't fully jsonParsed.
    """
    msg = (tx.get("transaction") or {}).get("message") or {}
    for ix in msg.get("instructions") or []:
        if ix.get("programId") == MEMO_PROGRAM_ID or ix.get("program") == "spl-memo":
            parsed = ix.get("parsed")
            if isinstance(parsed, str):
                return parsed
            if isinstance(parsed, dict):
                inner = parsed.get("info") or parsed
                if isinstance(inner, str):
                    return inner
    for line in (tx.get("meta") or {}).get("logMessages") or []:
        m = re.search(r'Program (?:data|log): Memo \(len \d+\): "(.*)"', line)
        if m:
            return m.group(1)
    return None


async def credit_deposits(redis, *, limit: int = 50, session=None) -> int:
    """Scan recent treasury transactions; credit any memo-tagged top-ups.

    Returns the number of new deposits credited.
    """
    treasury = tokens.treasury_address()
    mint = tokens.token_mint()
    try:
        sigs = await rpc("getSignaturesForAddress", [treasury, {"limit": limit}],
                         session=session)
    except RpcError as exc:
        log.warning("credit_deposits: getSignaturesForAddress failed: %s", exc)
        return 0

    credited = 0
    for row in sigs or []:
        sig = row.get("signature")
        if not sig or row.get("err") is not None:
            continue
        if await redis.sismember(DEPOSITS_SEEN_KEY, sig):
            continue
        if await redis.sismember(settle.SEEN_KEY, sig):
            continue  # already handled as a settlement
        try:
            tx = await rpc(
                "getTransaction",
                [sig, {"encoding": "jsonParsed", "commitment": "confirmed",
                       "maxSupportedTransactionVersion": 0}],
                session=session,
            )
        except RpcError:
            continue
        if not tx or (tx.get("meta") or {}).get("err") is not None:
            continue

        memo = _memo_of(tx)
        if not memo or not memo.startswith(DEPOSIT_MEMO_PREFIX):
            continue
        client = _sanitize_client(memo[len(DEPOSIT_MEMO_PREFIX):])
        delta = _treasury_delta(tx.get("meta") or {}, treasury, mint)
        if delta <= 0:
            continue
        whole = tokens.from_base_units(delta)

        pipe = redis.pipeline(transaction=True)
        # `credits:balance:<client>` is a plain string counter — same type the
        # proxy debits with INCRBYFLOAT.
        pipe.incrbyfloat(f"{BALANCE_PREFIX}{client}", float(whole))
        pipe.sadd(DEPOSITS_SEEN_KEY, sig)
        # A deposit is prepayment, not a completed job: keep reconcile_chain
        # from splitting+burning it. It burns as the credit is spent.
        pipe.sadd(settle.SEEN_KEY, sig)
        pipe.lpush(DEPOSITS_LOG_KEY, json.dumps({
            "sig": sig, "client": client, "amount": str(whole),
            "ts": int(tx.get("blockTime") or time.time()),
        }))
        pipe.ltrim(DEPOSITS_LOG_KEY, 0, DEPOSITS_LOG_MAX - 1)
        await pipe.execute()
        credited += 1
        log.info("credit deposit: %s +%s $REDACTED to %s", sig[:16], whole, client)
    return credited


async def drain_spend_queue(redis, *, max_items: int = 200) -> int:
    """Turn proxied-inference debits into burn-split settlements.

    Returns the number of spend entries settled.
    """
    settled = 0
    for _ in range(max_items):
        raw = await redis.rpop(SPEND_QUEUE_KEY)
        if raw is None:
            break
        try:
            e = json.loads(raw)
            nonce = e["nonce"]
            base_units = int(e["base_units"])
        except (TypeError, ValueError, KeyError):
            log.warning("drain_spend_queue: dropping malformed entry %r", raw)
            continue
        if base_units <= 0:
            continue
        try:
            await settle.record_settlement(redis, {
                "signature": f"credit-spend:{nonce}",
                "amount_raw": base_units,
                "payer": str(e.get("client") or "")[:64],
                "endpoint": "proxy",
                "block_time": int(e.get("ts") or time.time()),
            })
        except Exception:  # noqa: BLE001 — requeue and retry next tick
            log.warning("drain_spend_queue: record_settlement failed, requeuing",
                        exc_info=True)
            await redis.lpush(SPEND_QUEUE_KEY, raw)
            break
        settled += 1
    if settled:
        log.info("drain_spend_queue: settled %d proxied-inference spend(s)", settled)
    return settled
