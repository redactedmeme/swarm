"""Retire the burn slice on-chain, with a settlement memo in the same tx.

`settle.py` accumulates what the swarm owes the incinerator. This module is the
half that actually moves it: the standalone `apps/settler` service — the only
component that holds `SWARM_TREASURY_PRIVATE_KEY` — runs `run_worker`, which
drains `burn_accrued - burned_total` by sending `TransferChecked` from the
treasury's token account to the incinerator's, alongside an SPL Memo recording
the settlement that produced the burn.

`solders` is imported lazily inside functions (repo pattern:
`apps/arb-keeper/dex/swap_tx.py`) so this module still imports in CI, where the
`solana` extra is not installed — it is in the workflow's `OPTIONAL` set.

Crash-safety contract: before `sendTransaction` the fully-signed bytes, the
signature and the blockhash are stashed in `swarm:treasury`. On restart
`resume_pending` re-checks that signature and re-broadcasts the *identical*
bytes if it is still unlanded — never builds a fresh burn for a debt that might
already be paid, which is the only way to double-burn.
"""
from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import struct
import time

from .. import tokens
from . import settle
from .rpc import RpcError, rpc, rpc_url
from .verify import _treasury_delta

log = logging.getLogger(__name__)

# ── Program IDs ─────────────────────────────────────────────────────────────
TOKEN_PROGRAM_ID = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"
ATA_PROGRAM_ID = "ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL"
COMPUTE_BUDGET_PROGRAM_ID = "ComputeBudget111111111111111111111111111111"
SYSTEM_PROGRAM_ID = "11111111111111111111111111111111"
#: SPL Memo — the current program (Explorer labels it "Memo Program v2"), the
#: `declare_id!` of the `spl-memo` crate / `@solana/spl-memo`. NOT the
#: deprecated v1 `Memo1UhkJRfHyvLMcVucJwxXeuD728EqVDDwQDxFMNo`. Confirm on an
#: explorer before the first mainnet run.
MEMO_PROGRAM_ID = "MemoSq4gqABAXKb96qnH8TysNcWxMyWCqXgDLGmfcHr"

# ── Tunables ───────────────────────────────────────────────────────────────
_UNIT = 10 ** tokens.TOKEN_DECIMALS
#: Don't send a burn tx for less than this — each one costs a priority fee.
MIN_BURN_BASE_UNITS = int(os.getenv("MIN_BURN_BASE_UNITS", str(1_000 * _UNIT)))
#: Ceiling per tx; the remainder stays owed for the next round.
MAX_BURN_PER_TX = int(os.getenv("MAX_BURN_PER_TX", str(10_000_000 * _UNIT)))
CU_LIMIT = int(os.getenv("COMPUTE_UNIT_LIMIT", "60000"))
CU_PRICE_MICRO = int(os.getenv("COMPUTE_UNIT_PRICE_MICRO", "1000"))
FAIL_STREAK_MAX = int(os.getenv("BURN_FAIL_STREAK_MAX", "5"))
#: Below this the treasury can't pay tx fees — skip and log rather than spew
#: preflight failures.
MIN_TREASURY_SOL = float(os.getenv("MIN_TREASURY_SOL", "0.01"))
MEMO_PREFIX = os.getenv("SETTLEMENT_MEMO_PREFIX", "swarm-settle")
POLL_S = float(os.getenv("SETTLER_POLL_S", "20"))
METRICS_EVERY_S = float(os.getenv("SETTLER_METRICS_EVERY_S", "300"))
_LAMPORTS_PER_SOL = 1_000_000_000

TREASURY_KEY = settle.TREASURY_KEY
BURNED_SEEN_KEY = os.getenv("X402_BURNED_SEEN_KEY", "swarm:treasury:burned:seen")
_PENDING_FIELDS = (
    "burn_pending_sig",
    "burn_pending_amount",
    "burn_pending_at",
    "burn_pending_tx",
    "burn_pending_bh",
)


# ── Keypair ────────────────────────────────────────────────────────────────

_B58 = b"123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
_B58_MAP = {c: i for i, c in enumerate(_B58)}


def _b58decode(s: str) -> bytes:
    n = 0
    for ch in s.encode():
        n = n * 58 + _B58_MAP[ch]
    body = n.to_bytes((n.bit_length() + 7) // 8, "big") if n else b""
    pad = len(s) - len(s.lstrip("1"))
    return b"\x00" * pad + body


def load_keypair(raw: str):
    """A `solders.keypair.Keypair` from a 64-byte base58 export, a 32-byte
    seed, or a JSON int array — the three shapes Phantom / the CLI produce.
    Mirrors `apps/arb-keeper/wallet.py:load_keypair`."""
    from solders.keypair import Keypair  # type: ignore

    raw = (raw or "").strip()
    if not raw:
        raise RuntimeError("SWARM_TREASURY_PRIVATE_KEY is empty")
    try:
        decoded = _b58decode(raw)
    except Exception:
        try:
            decoded = bytes(json.loads(raw))
        except Exception as exc:
            raise RuntimeError(
                "SWARM_TREASURY_PRIVATE_KEY is not valid base58 or a JSON array"
            ) from exc
    if len(decoded) == 64:
        return Keypair.from_bytes(decoded)
    if len(decoded) == 32:
        return Keypair.from_seed(decoded)
    raise RuntimeError(
        f"SWARM_TREASURY_PRIVATE_KEY decoded to {len(decoded)} bytes, expected 32 or 64"
    )


# ── Instruction builders ───────────────────────────────────────────────────

def _ata(owner: str, mint: str) -> str:
    from solders.pubkey import Pubkey  # type: ignore

    pda, _ = Pubkey.find_program_address(
        [bytes(Pubkey.from_string(owner)),
         bytes(Pubkey.from_string(TOKEN_PROGRAM_ID)),
         bytes(Pubkey.from_string(mint))],
        Pubkey.from_string(ATA_PROGRAM_ID),
    )
    return str(pda)


def _ix_cu_price(micro_lamports: int):
    from solders.instruction import Instruction  # type: ignore
    from solders.pubkey import Pubkey  # type: ignore

    return Instruction(
        program_id=Pubkey.from_string(COMPUTE_BUDGET_PROGRAM_ID),
        accounts=[],
        data=bytes([3]) + struct.pack("<Q", micro_lamports),
    )


def _ix_cu_limit(units: int):
    from solders.instruction import Instruction  # type: ignore
    from solders.pubkey import Pubkey  # type: ignore

    return Instruction(
        program_id=Pubkey.from_string(COMPUTE_BUDGET_PROGRAM_ID),
        accounts=[],
        data=bytes([2]) + struct.pack("<I", units),
    )


def _ix_create_idempotent_ata(payer: str, owner: str, mint: str):
    from solders.instruction import AccountMeta, Instruction  # type: ignore
    from solders.pubkey import Pubkey  # type: ignore

    P = Pubkey.from_string
    return Instruction(
        program_id=P(ATA_PROGRAM_ID),
        accounts=[
            AccountMeta(P(payer), True, True),
            AccountMeta(P(_ata(owner, mint)), False, True),
            AccountMeta(P(owner), False, False),
            AccountMeta(P(mint), False, False),
            AccountMeta(P(SYSTEM_PROGRAM_ID), False, False),
            AccountMeta(P(TOKEN_PROGRAM_ID), False, False),
        ],
        data=bytes([1]),  # CreateIdempotent
    )


def _ix_transfer_checked(source_ata: str, mint: str, dest_ata: str,
                         authority: str, amount: int, decimals: int):
    from solders.instruction import AccountMeta, Instruction  # type: ignore
    from solders.pubkey import Pubkey  # type: ignore

    P = Pubkey.from_string
    return Instruction(
        program_id=P(TOKEN_PROGRAM_ID),
        accounts=[
            AccountMeta(P(source_ata), False, True),
            AccountMeta(P(mint), False, False),
            AccountMeta(P(dest_ata), False, True),
            AccountMeta(P(authority), True, False),
        ],
        # TransferChecked = 12, u64 amount LE, u8 decimals. Pins mint+decimals
        # so a misconfigured PROJECT_TOKEN_MINT / TOKEN_DECIMALS fails the tx
        # instead of irreversibly burning the wrong asset.
        data=bytes([12]) + struct.pack("<Q", amount) + struct.pack("<B", decimals),
    )


def _ix_memo(text: str):
    from solders.instruction import Instruction  # type: ignore
    from solders.pubkey import Pubkey  # type: ignore

    return Instruction(
        program_id=Pubkey.from_string(MEMO_PROGRAM_ID),
        accounts=[],
        data=text.encode("utf-8"),
    )


def build_burn_ixs(treasury_pubkey: str, mint: str, amount_base_units: int,
                   memo_text: str, *, cu_limit: int = CU_LIMIT,
                   cu_price_micro: int = CU_PRICE_MICRO) -> list:
    """`[cu price, cu limit, create incinerator ATA, transferChecked, memo]`.

    The incinerator's ATA for an arbitrary mint almost never exists — the
    createIdempotent is a no-op once it does, and skipping the `getAccountInfo`
    probe avoids a race and an RPC. Rent (~0.00204 SOL) is paid by the treasury.
    """
    incinerator = tokens.burn_address()
    return [
        _ix_cu_price(cu_price_micro),
        _ix_cu_limit(cu_limit),
        _ix_create_idempotent_ata(treasury_pubkey, incinerator, mint),
        _ix_transfer_checked(
            _ata(treasury_pubkey, mint), mint, _ata(incinerator, mint),
            treasury_pubkey, amount_base_units, tokens.TOKEN_DECIMALS,
        ),
        _ix_memo(memo_text),
    ]


async def build_and_sign(kp, mint: str, amount_base_units: int, memo_text: str,
                         *, session=None) -> tuple[bytes, str, str]:
    """Compile + sign the burn tx. Returns `(raw_bytes, signature, blockhash)`.

    Single signer: the treasury is fee payer, ATA-rent payer and transfer
    authority, so the message needs exactly one signature and
    `account_keys[0] == treasury`.
    """
    from solders.hash import Hash  # type: ignore
    from solders.message import MessageV0  # type: ignore
    from solders.pubkey import Pubkey  # type: ignore
    from solders.transaction import VersionedTransaction  # type: ignore

    treasury = str(kp.pubkey())
    ixs = build_burn_ixs(treasury, mint, amount_base_units, memo_text)
    res = await rpc("getLatestBlockhash", [{"commitment": "confirmed"}], session=session)
    bh = res["value"]["blockhash"]
    msg = MessageV0.try_compile(
        payer=Pubkey.from_string(treasury),
        instructions=ixs,
        address_lookup_table_accounts=[],
        recent_blockhash=Hash.from_string(bh),
    )
    signed = VersionedTransaction(msg, [kp])
    return bytes(signed), str(signed.signatures[0]), bh


async def submit(raw: bytes, *, session=None) -> str:
    """`sendTransaction` with preflight ON — a stale blockhash / underfunded
    treasury / bad ATA surfaces here as `RpcError` before any pending state is
    written."""
    b64 = base64.b64encode(raw).decode()
    return await rpc(
        "sendTransaction",
        [b64, {"encoding": "base64", "skipPreflight": False,
               "maxRetries": 3, "preflightCommitment": "confirmed"}],
        session=session,
    )


async def status_once(sig: str, *, search_history: bool = False, session=None) -> str:
    """One `getSignatureStatuses` check → 'confirmed' | 'failed' | 'unknown'."""
    res = await rpc(
        "getSignatureStatuses",
        [[sig], {"searchTransactionHistory": search_history}],
        session=session,
    )
    st = (res.get("value") or [None])[0]
    if st is None:
        return "unknown"
    if st.get("err") is not None:
        return "failed"
    if st.get("confirmationStatus") in ("confirmed", "finalized"):
        return "confirmed"
    return "unknown"


async def confirm(sig: str, *, timeout_s: float = 90.0, poll_s: float = 2.0,
                  search_history: bool = False, session=None) -> str:
    """Poll `status_once` until confirmed/failed or the deadline. The resume
    path calls `status_once` directly — on restart we only need "did it land",
    not "wait for it to land"."""
    deadline = time.monotonic() + timeout_s
    while True:
        st = await status_once(sig, search_history=search_history, session=session)
        if st in ("confirmed", "failed"):
            return st
        if time.monotonic() >= deadline:
            return "unknown"
        await asyncio.sleep(poll_s)


# ── Redis accounting transitions ───────────────────────────────────────────

async def _clear_pending(redis, *, fail: bool) -> None:
    await redis.hdel(TREASURY_KEY, *_PENDING_FIELDS)
    if fail:
        await redis.hincrby(TREASURY_KEY, "burn_fail_streak", 1)


async def _finalize(redis, sig: str, amount: int) -> None:
    """Confirmed burn → move `owed` to burned, clear pending, reset the streak.

    Guarded by `BURNED_SEEN_KEY` so a double resume can't double-count, and done
    as one MULTI/EXEC so a crash can't credit `burned_total` yet leave the
    pending marker behind.
    """
    if await redis.sismember(BURNED_SEEN_KEY, sig):
        await redis.hdel(TREASURY_KEY, *_PENDING_FIELDS)
        return
    async with redis.pipeline(transaction=True) as p:
        p.sadd(BURNED_SEEN_KEY, sig)
        p.hincrby(TREASURY_KEY, "burned_total", amount)
        p.hset(TREASURY_KEY, mapping={
            "last_burn_sig": sig, "last_burn_at": int(time.time()),
            "burn_fail_streak": 0,
        })
        p.hdel(TREASURY_KEY, *_PENDING_FIELDS)
        await p.execute()
    log.info("burn confirmed: %s retired %d base units", sig[:16], amount)


async def resume_pending(redis, kp, *, execute: bool, session=None) -> None:
    """Resolve an in-flight burn before doing anything else. Idempotent."""
    h = await redis.hgetall(TREASURY_KEY)
    sig = h.get("burn_pending_sig")
    if not sig:
        return
    amount = int(h.get("burn_pending_amount", 0) or 0)
    status = await status_once(sig, search_history=True, session=session)
    if status == "confirmed":
        await _finalize(redis, sig, amount)
        return
    if status == "failed":
        log.warning("pending burn %s landed reverted — clearing", sig[:16])
        await _clear_pending(redis, fail=True)
        return
    # unknown — is the blockhash still usable?
    still_valid = False
    bh = h.get("burn_pending_bh") or ""
    if bh:
        try:
            r = await rpc("isBlockhashValid", [bh, {"commitment": "confirmed"}],
                          session=session)
            still_valid = bool(r.get("value"))
        except RpcError:
            still_valid = False
    tx_hex = h.get("burn_pending_tx") or ""
    if still_valid and tx_hex and execute:
        log.info("re-broadcasting pending burn %s (identical bytes)", sig[:16])
        try:
            await submit(bytes.fromhex(tx_hex), session=session)
        except RpcError as exc:
            log.warning("re-broadcast failed: %s", exc)
        # leave pending in place; next tick re-checks
    else:
        log.warning("pending burn %s dropped (blockhash expired) — clearing", sig[:16])
        await _clear_pending(redis, fail=True)


# ── Burn drive ─────────────────────────────────────────────────────────────

async def _sol_balance(pubkey: str, *, session=None) -> float | None:
    try:
        res = await rpc("getBalance", [pubkey], session=session)
        return (res.get("value") or 0) / _LAMPORTS_PER_SOL
    except RpcError as exc:
        log.warning("getBalance failed: %s", exc)
        return None


async def maybe_burn(redis, kp, *, session=None) -> None:
    """Send at most one burn tx for the currently-owed amount."""
    h = await redis.hgetall(TREASURY_KEY)
    if h.get("burn_pending_sig"):
        return  # resume_pending owns it
    if h.get("burn_halted"):
        return
    if int(h.get("burn_fail_streak", 0) or 0) >= FAIL_STREAK_MAX:
        log.error("burn circuit breaker: %s consecutive failures — halting. "
                  "Clear swarm:treasury burn_halted / burn_fail_streak to resume.",
                  h.get("burn_fail_streak"))
        await redis.hset(TREASURY_KEY, "burn_halted", "1")
        return

    owed = settle.owed_burn(h)
    if owed < MIN_BURN_BASE_UNITS:
        return
    amount = min(owed, MAX_BURN_PER_TX)

    bal = await _sol_balance(str(kp.pubkey()), session=session)
    if bal is not None and bal < MIN_TREASURY_SOL:
        log.warning("treasury SOL %.5f < %.5f — deferring burn of %d base units",
                    bal, MIN_TREASURY_SOL, amount)
        return

    memo = (f"{MEMO_PREFIX} v1 burn={amount} "
            f"rev={str(h.get('last_settlement_sig') or '')[:24]}")
    raw, sig, bh = await build_and_sign(
        kp, tokens.token_mint(), amount, memo, session=session)

    # Stash the signed bytes BEFORE broadcasting — the resume path re-sends
    # these exact bytes rather than building a new burn.
    await redis.hset(TREASURY_KEY, mapping={
        "burn_pending_sig": sig,
        "burn_pending_amount": amount,
        "burn_pending_at": int(time.time()),
        "burn_pending_tx": raw.hex(),
        "burn_pending_bh": bh,
    })
    try:
        await submit(raw, session=session)
    except RpcError as exc:
        log.warning("burn submit failed (%s) — pending kept, re-resolved next tick", exc)
        return
    status = await confirm(sig, session=session)
    if status == "confirmed":
        await _finalize(redis, sig, amount)
    elif status == "failed":
        log.warning("burn %s reverted", sig[:16])
        await _clear_pending(redis, fail=True)
    # unknown → leave pending for resume_pending


# ── Metrics + reconciliation ───────────────────────────────────────────────

async def _proxy_spend_30d_usd(*, session=None) -> float | None:
    base = os.getenv("PROXY_URL", "").rstrip("/")
    token = os.getenv("PROXY_TOKEN", "")
    if not base or not token:
        return None
    import aiohttp

    owned = session is None
    session = session or aiohttp.ClientSession()
    try:
        async with session.get(
            f"{base}/usage?days=30",
            headers={"Authorization": f"Bearer {token}"},
            timeout=aiohttp.ClientTimeout(total=15),
        ) as resp:
            if resp.status != 200:
                return None
            data = await resp.json()
    except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
        log.warning("proxy /usage fetch failed: %s", exc)
        return None
    finally:
        if owned:
            await session.close()
    total = 0.0
    for rec in (data.get("clients") or {}).values():
        for day in (rec.get("daily") or {}).values():
            total += float(day.get("cost_usd", 0) or 0)
    return total


async def _redacted_price_usd(*, session=None) -> float | None:
    import aiohttp

    owned = session is None
    session = session or aiohttp.ClientSession()
    try:
        async with session.get(
            f"https://api.dexscreener.com/latest/dex/tokens/{tokens.token_mint()}",
            timeout=aiohttp.ClientTimeout(total=15),
        ) as resp:
            if resp.status != 200:
                return None
            data = await resp.json()
    except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
        log.warning("dexscreener fetch failed: %s", exc)
        return None
    finally:
        if owned:
            await session.close()
    pairs = data.get("pairs") or []
    prices = [float(p["priceUsd"]) for p in pairs if p.get("priceUsd")]
    return max(prices) if prices else None


async def _treasury_token_balance(*, session=None) -> float | None:
    """Whole $REDACTED held in the treasury's ATA."""
    try:
        res = await rpc(
            "getTokenAccountsByOwner",
            [tokens.treasury_address(),
             {"mint": tokens.token_mint()},
             {"encoding": "jsonParsed"}],
            session=session,
        )
    except RpcError as exc:
        log.warning("getTokenAccountsByOwner failed: %s", exc)
        return None
    total = 0.0
    for acc in res.get("value") or []:
        info = acc["account"]["data"]["parsed"]["info"]["tokenAmount"]
        total += float(info.get("uiAmount") or 0)
    return total


async def refresh_metrics(redis, *, session=None) -> None:
    """Publish `runway_days`, `compute_spend_30d_usd`, `treasury_balance`.
    Best-effort; a missing input leaves that field untouched."""
    spend = await _proxy_spend_30d_usd(session=session)
    price = await _redacted_price_usd(session=session)
    bal = await _treasury_token_balance(session=session)
    fields: dict[str, str] = {}
    if spend is not None:
        fields["compute_spend_30d_usd"] = f"{spend:.6f}"
    if bal is not None:
        fields["treasury_balance"] = f"{bal:.6f}"
    if spend not in (None, 0) and price and bal is not None:
        daily = spend / 30.0
        if daily > 0:
            fields["runway_days"] = f"{(bal * price) / daily:.2f}"
    if fields:
        await redis.hset(TREASURY_KEY, mapping=fields)


async def reconcile_chain(redis, *, limit: int = 50, session=None) -> int:
    """Backstop: replay any inbound treasury payment `record_settlement` missed
    (e.g. a redis blip during the paid call). Outbound burns net negative and
    are skipped by `_treasury_delta`."""
    treasury = tokens.treasury_address()
    try:
        sigs = await rpc("getSignaturesForAddress", [treasury, {"limit": limit}],
                         session=session)
    except RpcError as exc:
        log.warning("reconcile: getSignaturesForAddress failed: %s", exc)
        return 0
    recovered = 0
    for row in sigs or []:
        sig = row.get("signature")
        if not sig or row.get("err") is not None:
            continue
        if await redis.sismember(settle.SEEN_KEY, sig):
            continue
        try:
            tx = await rpc(
                "getTransaction",
                [sig, {"encoding": "jsonParsed", "commitment": "confirmed",
                       "maxSupportedTransactionVersion": 0}],
                session=session,
            )
        except RpcError:
            continue
        if not tx:
            continue
        meta = tx.get("meta") or {}
        if meta.get("err") is not None:
            continue
        # A memo-tagged credit deposit is prepayment, not a completed job —
        # credit_deposits handles it. Skip here even if it hasn't run yet.
        from . import credits  # lazy

        memo = credits._memo_of(tx)
        if memo and memo.startswith(credits.DEPOSIT_MEMO_PREFIX):
            continue
        delta = _treasury_delta(meta, treasury, tokens.token_mint())
        if delta <= 0:
            continue
        keys = (tx.get("transaction") or {}).get("message", {}).get("accountKeys") or []
        payer = ""
        if keys:
            first = keys[0]
            payer = first.get("pubkey", "") if isinstance(first, dict) else str(first)
        await settle.record_settlement(redis, {
            "signature": sig,
            "payer": payer,
            "amount_raw": delta,
            "endpoint": "reconciled",
            "block_time": int(tx.get("blockTime") or time.time()),
        })
        recovered += 1
    if recovered:
        log.info("reconcile: recovered %d missed settlement(s)", recovered)
    return recovered


# ── Worker ─────────────────────────────────────────────────────────────────

async def run_worker(redis, *, execute: bool, poll_s: float = POLL_S,
                     metrics_every_s: float = METRICS_EVERY_S) -> None:
    """Forever: resolve any pending burn, refresh the 24h count, periodically
    refresh metrics + reconcile, and (when `execute`) drain the owed burn."""
    kp = None
    if execute:
        kp = load_keypair(os.environ["SWARM_TREASURY_PRIVATE_KEY"])
        if str(kp.pubkey()) != tokens.treasury_address():
            raise RuntimeError(
                f"treasury key {kp.pubkey()} != SWARM_TREASURY_ADDRESS "
                f"{tokens.treasury_address()}"
            )
        log.info("settler executing — treasury %s, rpc %s", kp.pubkey(), rpc_url())
    else:
        log.warning("SETTLEMENT_EXECUTE off — recording ledger only, no burns")

    last_metrics = 0.0
    while True:
        try:
            await resume_pending(redis, kp, execute=execute)
            await settle.recount_24h(redis)
            # Credits: turn proxied-inference debits into burn-split settlements
            # every tick (cheap, redis-only); credit any memo-tagged deposits on
            # the slower metrics cadence (an RPC walk). Both run regardless of
            # `execute` — no key needed.
            from . import credits  # lazy: credits imports burn's constants

            await credits.drain_spend_queue(redis)
            now = time.monotonic()
            if now - last_metrics >= metrics_every_s:
                await credits.credit_deposits(redis)
                await refresh_metrics(redis)
                await reconcile_chain(redis)
                last_metrics = now
            if execute:
                await maybe_burn(redis, kp)
        except Exception:  # noqa: BLE001 — one bad tick must not kill the worker
            log.exception("settler tick failed")
        await asyncio.sleep(poll_s)
