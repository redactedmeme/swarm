"""Swarm SOL Reserve - keeps every agent wallet above a minimum SOL balance.

Runs inside ``apps/settler`` (the only component that holds a treasury/reserve
key). It reuses the crash-safe machinery already proven in
``swarm_core.x402.burn``: the same RPC client, compute-budget instructions,
``build/sign/submit/confirm`` shape, and a Redis hash that stashes the signed
bytes *before* broadcast so a restart re-resolves rather than re-sends.

Safety, in layers:

* ``RESERVE_EXECUTE`` unset  -> dry-run: log + audit ``reserve.dryrun``, send nothing.
* ``RESERVE_MIN_SOL``        -> only tops up wallets below this.
* ``RESERVE_REFUEL_SOL``     -> fixed small amount per top-up.
* ``RESERVE_COOLDOWN_S``     -> no second top-up for the same agent inside the window.
* ``RESERVE_DAILY_CAP_SOL``  -> hard per-agent per-UTC-day ceiling.
* ``authz.require("settler", "funds.refuel")`` before any live send.
* every attempt (dry-run, skip, send, fail) is on the ``swarm:audit`` chain.
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
from datetime import datetime, timezone

from swarm_core.x402 import burn as _burn
from swarm_core.x402.rpc import RpcError, rpc, rpc_url

from . import LIVE_WALLET_AGENTS, keystore

log = logging.getLogger(__name__)

_LAMPORTS_PER_SOL = 1_000_000_000
_SYSTEM_PROGRAM_ID = "11111111111111111111111111111111"

RESERVE_KEY = "swarm:reserve"
_PENDING_FIELDS = (
    "refuel_pending_sig",
    "refuel_pending_agent",
    "refuel_pending_lamports",
    "refuel_pending_tx",
    "refuel_pending_bh",
    "refuel_pending_at",
)


# ── config ────────────────────────────────────────────────────────────────────

def _cfg() -> dict:
    f = float
    return {
        "execute": os.getenv("RESERVE_EXECUTE", "").strip().lower() in ("1", "true", "yes"),
        "min_sol": f(os.getenv("RESERVE_MIN_SOL", "0.02")),
        "refuel_sol": f(os.getenv("RESERVE_REFUEL_SOL", "0.05")),
        "daily_cap_sol": f(os.getenv("RESERVE_DAILY_CAP_SOL", "0.2")),
        "cooldown_s": f(os.getenv("RESERVE_COOLDOWN_S", "900")),
        "every_s": f(os.getenv("RESERVE_EVERY_S", "300")),
    }


def reserve_keypair():
    """The wallet that funds refuels: ``SWARM_RESERVE_PRIVATE_KEY`` if set, else
    the treasury key (reserve == treasury by default)."""
    raw = (os.getenv("SWARM_RESERVE_PRIVATE_KEY", "").strip()
           or os.getenv("SWARM_TREASURY_PRIVATE_KEY", "").strip())
    if not raw:
        raise RuntimeError(
            "RESERVE_EXECUTE set but neither SWARM_RESERVE_PRIVATE_KEY nor "
            "SWARM_TREASURY_PRIVATE_KEY is available"
        )
    return _burn.load_keypair(raw)


# ── instruction + tx build ────────────────────────────────────────────────────

def _ix_sol_transfer(from_pubkey: str, to_pubkey: str, lamports: int):
    """System Program ``Transfer`` (instruction index 2, then u64 LE lamports).
    ``burn.py`` only builds SPL ``TransferChecked``; a plain SOL move needs this."""
    import struct

    from solders.instruction import AccountMeta, Instruction  # type: ignore
    from solders.pubkey import Pubkey  # type: ignore

    P = Pubkey.from_string
    return Instruction(
        program_id=P(_SYSTEM_PROGRAM_ID),
        accounts=[
            AccountMeta(P(from_pubkey), True, True),
            AccountMeta(P(to_pubkey), False, True),
        ],
        data=struct.pack("<I", 2) + struct.pack("<Q", lamports),
    )


async def build_and_sign_transfer(kp, to_addr: str, lamports: int, *, session=None):
    """Returns ``(raw_bytes, signature, blockhash)`` for a single-signer SOL
    transfer with a compute-budget prefix (mirrors ``burn.build_and_sign``)."""
    from solders.hash import Hash  # type: ignore
    from solders.message import MessageV0  # type: ignore
    from solders.pubkey import Pubkey  # type: ignore
    from solders.transaction import VersionedTransaction  # type: ignore

    src = str(kp.pubkey())
    ixs = [
        _burn._ix_cu_price(_burn.CU_PRICE_MICRO),
        _burn._ix_cu_limit(20_000),
        _ix_sol_transfer(src, to_addr, lamports),
    ]
    res = await rpc("getLatestBlockhash", [{"commitment": "confirmed"}], session=session)
    bh = res["value"]["blockhash"]
    msg = MessageV0.try_compile(
        payer=Pubkey.from_string(src),
        instructions=ixs,
        address_lookup_table_accounts=[],
        recent_blockhash=Hash.from_string(bh),
    )
    signed = VersionedTransaction(msg, [kp])
    return bytes(signed), str(signed.signatures[0]), bh


# ── audit helper ──────────────────────────────────────────────────────────────

def _audit(event: str, detail: dict, *, decision: str = "n/a", severity: str = "info") -> None:
    try:
        from swarm_core.security import audit as _a

        _a.record(event, actor="settler", decision=decision, severity=severity, detail=detail)
    except Exception:  # audit must never break a refuel
        pass


def _authorized() -> bool:
    try:
        from swarm_core.security import authz

        authz.require("settler", "funds.refuel")
        return True
    except Exception as exc:
        log.error("[reserve] funds.refuel not authorized: %s", exc)
        _audit("reserve.denied", {"reason": str(exc)}, decision="deny", severity="warning")
        return False


# ── core ──────────────────────────────────────────────────────────────────────

async def check_and_refuel_agent(redis, agent: str, *, cfg: dict | None = None,
                                 kp=None, session=None) -> dict:
    """Evaluate one agent and, when warranted + permitted, send one top-up.

    Returns a status dict; ``status`` is one of: ``no_wallet``, ``rpc_error``,
    ``ok`` (above threshold), ``cooldown``, ``capped``, ``dryrun``,
    ``refuelled``, ``send_failed``.
    """
    cfg = cfg or _cfg()
    address = keystore.get_address(agent)
    if not address:
        return {"agent": agent, "status": "no_wallet"}

    bal = await _burn._sol_balance(address, session=session)
    if bal is None:
        return {"agent": agent, "status": "rpc_error", "address": address}
    if bal >= cfg["min_sol"]:
        return {"agent": agent, "status": "ok", "sol": bal, "address": address}

    now = time.time()
    last = await redis.get(f"swarm:reserve:last:{agent}")
    if last and (now - float(last)) < cfg["cooldown_s"]:
        return {"agent": agent, "status": "cooldown", "sol": bal, "address": address}

    day = datetime.now(timezone.utc).strftime("%Y%m%d")
    spent_key = f"swarm:reserve:spent:{agent}:{day}"
    spent = float(await redis.get(spent_key) or 0.0)
    if spent + cfg["refuel_sol"] > cfg["daily_cap_sol"] + 1e-9:
        _audit("reserve.capped", {"agent": agent, "spent_today": spent,
                                  "cap": cfg["daily_cap_sol"]}, severity="warning")
        return {"agent": agent, "status": "capped", "sol": bal, "address": address}

    lamports = int(round(cfg["refuel_sol"] * _LAMPORTS_PER_SOL))
    intent = {"agent": agent, "address": address, "sol_balance": bal,
              "refuel_sol": cfg["refuel_sol"], "lamports": lamports}

    if not cfg["execute"]:
        _audit("reserve.dryrun", intent)
        log.info("[reserve] DRY-RUN would send %.4f SOL to %s (%s), bal=%.5f",
                 cfg["refuel_sol"], agent, address, bal)
        return {**intent, "status": "dryrun"}

    if not _authorized():
        return {**intent, "status": "denied"}

    if kp is None:
        kp = reserve_keypair()

    raw, sig, bh = await build_and_sign_transfer(kp, address, lamports, session=session)
    await redis.hset(RESERVE_KEY, mapping={
        "refuel_pending_sig": sig,
        "refuel_pending_agent": agent,
        "refuel_pending_lamports": lamports,
        "refuel_pending_tx": raw.hex(),
        "refuel_pending_bh": bh,
        "refuel_pending_at": int(now),
    })
    try:
        await _burn.submit(raw, session=session)
    except RpcError as exc:
        _audit("reserve.send_failed", {**intent, "sig": sig, "error": str(exc)},
               decision="deny", severity="warning")
        await redis.hdel(RESERVE_KEY, *_PENDING_FIELDS)
        return {**intent, "status": "send_failed", "error": str(exc)}

    state = await _burn.confirm(sig, session=session)
    await redis.hdel(RESERVE_KEY, *_PENDING_FIELDS)
    if state == "confirmed":
        async with redis.pipeline(transaction=True) as p:
            p.incrbyfloat(spent_key, cfg["refuel_sol"])
            p.expire(spent_key, 172800)
            p.set(f"swarm:reserve:last:{agent}", now)
            await p.execute()
        _audit("reserve.refuel", {**intent, "sig": sig}, decision="allow")
        log.info("[reserve] refuelled %s with %.4f SOL (sig %s)", agent, cfg["refuel_sol"], sig[:16])
        return {**intent, "status": "refuelled", "sig": sig}

    _audit("reserve.unconfirmed", {**intent, "sig": sig, "state": state}, severity="warning")
    return {**intent, "status": "send_failed", "sig": sig, "state": state}


async def refuel_all_low_agents(redis, *, agents=LIVE_WALLET_AGENTS, session=None) -> list[dict]:
    cfg = _cfg()
    known = keystore.all_addresses()
    targets = [a for a in agents if a in known]
    if not targets:
        return []
    kp = None
    if cfg["execute"]:
        try:
            kp = reserve_keypair()
        except RuntimeError as exc:
            log.error("[reserve] %s", exc)
            return [{"status": "no_key", "error": str(exc)}]
    out = []
    for agent in targets:
        try:
            out.append(await check_and_refuel_agent(redis, agent, cfg=cfg, kp=kp, session=session))
        except Exception as exc:  # one bad agent must not stop the sweep
            log.exception("[reserve] refuel check failed for %s", agent)
            out.append({"agent": agent, "status": "error", "error": str(exc)})
    return out


async def run_reserve_loop(redis) -> None:
    """Forever: sweep the roster every ``RESERVE_EVERY_S``. Safe to start
    unconditionally - it no-ops (dry-run) until ``RESERVE_EXECUTE`` is set."""
    import aiohttp

    cfg = _cfg()
    log.info("[reserve] loop start - execute=%s min=%.3f top-up=%.3f cap/day=%.3f rpc=%s",
             cfg["execute"], cfg["min_sol"], cfg["refuel_sol"], cfg["daily_cap_sol"], rpc_url())
    while True:
        try:
            async with aiohttp.ClientSession() as session:
                await refuel_all_low_agents(redis, session=session)
        except Exception:
            log.exception("[reserve] sweep failed")
        await asyncio.sleep(_cfg()["every_s"])
