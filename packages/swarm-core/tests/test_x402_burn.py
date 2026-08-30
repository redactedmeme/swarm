"""The burn path signs transactions that move the treasury wallet. Every test
here is a way it could burn the wrong thing, the wrong amount, or the same debt
twice.

`solders` is required (the `solana` extra); the whole module skips without it,
the way CI runs. Network calls are stubbed — these assert instruction shape and
the crash-safe owed→burned transition, not mainnet.
"""
from __future__ import annotations

import time

import pytest

solders = pytest.importorskip("solders")

from solders.keypair import Keypair  # noqa: E402
from solders.pubkey import Pubkey  # noqa: E402

from swarm_core import tokens  # noqa: E402
from swarm_core.x402 import burn as B  # noqa: E402
from swarm_core.x402 import settle as S  # noqa: E402
from fakeredis import FakeRedis  # noqa: E402

MINT = tokens.token_mint()


@pytest.fixture
def kp():
    return Keypair()


@pytest.fixture(autouse=True)
def treasury_env(kp, monkeypatch):
    monkeypatch.setenv("SWARM_TREASURY_ADDRESS", str(kp.pubkey()))
    monkeypatch.setattr(B, "MIN_BURN_BASE_UNITS", 1_000)
    monkeypatch.setattr(B, "MAX_BURN_PER_TX", 10_000)


@pytest.fixture
def redis():
    return FakeRedis()


def _stub_rpc(monkeypatch, handlers: dict):
    async def fake_rpc(method, params, *, session=None, timeout=15.0):
        h = handlers.get(method)
        if h is None:
            raise AssertionError(f"unexpected rpc {method}")
        return h(params) if callable(h) else h
    monkeypatch.setattr(B, "rpc", fake_rpc)


# ── Instruction shape ─────────────────────────────────────────────────────

def test_build_burn_ixs_order_and_programs(kp):
    ixs = B.build_burn_ixs(str(kp.pubkey()), MINT, 5_000, "memo")
    assert len(ixs) == 5
    progs = [str(ix.program_id) for ix in ixs]
    assert progs == [
        B.COMPUTE_BUDGET_PROGRAM_ID,
        B.COMPUTE_BUDGET_PROGRAM_ID,
        B.ATA_PROGRAM_ID,
        B.TOKEN_PROGRAM_ID,
        B.MEMO_PROGRAM_ID,
    ]


def test_transfer_checked_data_and_metas(kp):
    treasury = str(kp.pubkey())
    ixs = B.build_burn_ixs(treasury, MINT, 7_777, "m")
    tc = ixs[3]
    import struct
    assert tc.data == bytes([12]) + struct.pack("<Q", 7_777) + bytes([tokens.TOKEN_DECIMALS])
    src = B._ata(treasury, MINT)
    dest = B._ata(tokens.burn_address(), MINT)
    metas = [(str(m.pubkey), m.is_signer, m.is_writable) for m in tc.accounts]
    assert metas == [
        (src, False, True),
        (MINT, False, False),
        (dest, False, True),
        (treasury, True, False),
    ]


def test_create_idempotent_targets_incinerator_ata_paid_by_treasury(kp):
    treasury = str(kp.pubkey())
    ata_ix = B.build_burn_ixs(treasury, MINT, 1, "m")[2]
    payer, ata, owner = ata_ix.accounts[0], ata_ix.accounts[1], ata_ix.accounts[2]
    assert (str(payer.pubkey), payer.is_signer, payer.is_writable) == (treasury, True, True)
    assert str(ata.pubkey) == B._ata(tokens.burn_address(), MINT)
    assert str(owner.pubkey) == tokens.burn_address()
    assert ata_ix.data == bytes([1])


def test_memo_ix_has_no_accounts_and_utf8_data(kp):
    memo = B.build_burn_ixs(str(kp.pubkey()), MINT, 1, "swarm-settle v1 burn=42")[4]
    assert list(memo.accounts) == []
    assert memo.data == b"swarm-settle v1 burn=42"


# ── build_and_sign ───────────────────────────────────────────────────────

async def test_build_and_sign_single_signer_and_roundtrip(kp, monkeypatch):
    _stub_rpc(monkeypatch, {
        "getLatestBlockhash": {"value": {"blockhash": str(Pubkey.default())}},
    })
    raw, sig, bh = await B.build_and_sign(kp, MINT, 1_000, "memo")
    from solders.transaction import VersionedTransaction
    tx = VersionedTransaction.from_bytes(raw)
    assert tx.message.header.num_required_signatures == 1
    assert str(tx.message.account_keys[0]) == str(kp.pubkey())
    assert str(tx.signatures[0]) == sig
    assert bh == str(Pubkey.default())


# ── confirm ──────────────────────────────────────────────────────────────

async def test_confirm_confirmed(monkeypatch):
    seq = iter([
        {"value": [None]},
        {"value": [{"err": None, "confirmationStatus": "processed"}]},
        {"value": [{"err": None, "confirmationStatus": "confirmed"}]},
    ])
    _stub_rpc(monkeypatch, {"getSignatureStatuses": lambda p: next(seq)})
    assert await B.confirm("s", poll_s=0.001, timeout_s=5) == "confirmed"


async def test_confirm_failed(monkeypatch):
    _stub_rpc(monkeypatch, {
        "getSignatureStatuses": {"value": [{"err": {"InstructionError": [0, "X"]}}]},
    })
    assert await B.confirm("s", poll_s=0.001, timeout_s=5) == "failed"


async def test_confirm_unknown_on_timeout(monkeypatch):
    _stub_rpc(monkeypatch, {"getSignatureStatuses": {"value": [None]}})
    assert await B.confirm("s", poll_s=0.005, timeout_s=0.02) == "unknown"


# ── _finalize ────────────────────────────────────────────────────────────

async def test_finalize_moves_burned_total_and_clears_pending(redis):
    await redis.hset(S.TREASURY_KEY, mapping={
        "burn_accrued": "1000", "burn_pending_sig": "sig1",
        "burn_pending_amount": "600", "burn_pending_tx": "aa", "burn_fail_streak": "2",
    })
    await B._finalize(redis, "sig1", 600)
    h = redis.h[S.TREASURY_KEY]
    assert h["burned_total"] == "600"
    assert h["last_burn_sig"] == "sig1"
    assert h["burn_fail_streak"] == "0"
    assert "burn_pending_sig" not in h and "burn_pending_tx" not in h
    assert S.owed_burn(h) == 400


async def test_finalize_is_idempotent(redis):
    await redis.hset(S.TREASURY_KEY, mapping={"burn_accrued": "1000"})
    await B._finalize(redis, "sig1", 600)
    await B._finalize(redis, "sig1", 600)  # second resume must not double-count
    assert redis.h[S.TREASURY_KEY]["burned_total"] == "600"


# ── resume_pending ───────────────────────────────────────────────────────

async def _set_pending(redis, *, amount=600, bh="BH", tx="aa"):
    await redis.hset(S.TREASURY_KEY, mapping={
        "burn_accrued": "1000", "burn_pending_sig": "sigP",
        "burn_pending_amount": str(amount), "burn_pending_bh": bh,
        "burn_pending_tx": tx, "burn_pending_at": str(int(time.time())),
    })


async def test_resume_confirmed_finalizes_once(redis, kp, monkeypatch):
    await _set_pending(redis)
    _stub_rpc(monkeypatch, {
        "getSignatureStatuses": {"value": [{"err": None, "confirmationStatus": "finalized"}]},
    })
    await B.resume_pending(redis, kp, execute=True)
    h = redis.h[S.TREASURY_KEY]
    assert h["burned_total"] == "600"
    assert "burn_pending_sig" not in h


async def test_resume_failed_clears_and_bumps_streak(redis, kp, monkeypatch):
    await _set_pending(redis)
    _stub_rpc(monkeypatch, {"getSignatureStatuses": {"value": [{"err": {"e": 1}}]}})
    await B.resume_pending(redis, kp, execute=True)
    h = redis.h[S.TREASURY_KEY]
    assert "burn_pending_sig" not in h
    assert h["burn_fail_streak"] == "1"
    assert "burned_total" not in h


async def test_resume_unknown_expired_blockhash_clears(redis, kp, monkeypatch):
    await _set_pending(redis)
    _stub_rpc(monkeypatch, {
        "getSignatureStatuses": {"value": [None]},
        "isBlockhashValid": {"value": False},
    })
    await B.resume_pending(redis, kp, execute=True, session=object())
    h = redis.h[S.TREASURY_KEY]
    assert "burn_pending_sig" not in h
    assert h["burn_fail_streak"] == "1"


async def test_resume_unknown_valid_blockhash_rebroadcasts_same_bytes(redis, kp, monkeypatch):
    await _set_pending(redis, tx="deadbeef")
    sent = []

    async def fake_submit(raw, *, session=None):
        sent.append(raw)
        return "sigP"

    monkeypatch.setattr(B, "submit", fake_submit)
    _stub_rpc(monkeypatch, {
        "getSignatureStatuses": {"value": [None]},
        "isBlockhashValid": {"value": True},
    })
    await B.resume_pending(redis, kp, execute=True)
    assert sent == [bytes.fromhex("deadbeef")]
    # pending stays for the next tick to resolve
    assert redis.h[S.TREASURY_KEY]["burn_pending_sig"] == "sigP"


# ── maybe_burn ───────────────────────────────────────────────────────────

async def test_maybe_burn_below_floor_does_nothing(redis, kp, monkeypatch):
    await redis.hset(S.TREASURY_KEY, mapping={"burn_accrued": "500"})  # < 1000 floor
    monkeypatch.setattr(B, "build_and_sign", _boom("build_and_sign called"))
    await B.maybe_burn(redis, kp)
    assert "burn_pending_sig" not in redis.h.get(S.TREASURY_KEY, {})


async def test_maybe_burn_stashes_pending_before_submit_then_finalizes(redis, kp, monkeypatch):
    await redis.hset(S.TREASURY_KEY, mapping={
        "burn_accrued": "5000", "last_settlement_sig": "REVSIG",
    })
    order = []

    async def fake_bas(k, mint, amount, memo, *, session=None):
        order.append(("build", amount, memo))
        return b"\x01\x02", "SIGB", "BH"

    async def fake_submit(raw, *, session=None):
        # pending must already be recorded by the time we broadcast
        order.append(("submit", redis.h[S.TREASURY_KEY].get("burn_pending_sig")))
        return "SIGB"

    monkeypatch.setattr(B, "build_and_sign", fake_bas)
    monkeypatch.setattr(B, "submit", fake_submit)
    monkeypatch.setattr(B, "_sol_balance", _aval(1.0))
    _stub_rpc(monkeypatch, {
        "getSignatureStatuses": {"value": [{"err": None, "confirmationStatus": "confirmed"}]},
    })
    await B.maybe_burn(redis, kp)
    assert order[0][0] == "build" and order[0][1] == 5000
    assert "REVSIG"[:24] in order[0][2]
    assert order[1] == ("submit", "SIGB")
    h = redis.h[S.TREASURY_KEY]
    assert h["burned_total"] == "5000"
    assert "burn_pending_sig" not in h


async def test_maybe_burn_caps_at_max_per_tx(redis, kp, monkeypatch):
    await redis.hset(S.TREASURY_KEY, mapping={"burn_accrued": "999999"})
    seen = {}

    async def fake_bas(k, mint, amount, memo, *, session=None):
        seen["amount"] = amount
        return b"\x00", "S", "BH"

    monkeypatch.setattr(B, "build_and_sign", fake_bas)
    monkeypatch.setattr(B, "submit", _aval("S"))
    monkeypatch.setattr(B, "_sol_balance", _aval(1.0))
    _stub_rpc(monkeypatch, {
        "getSignatureStatuses": {"value": [{"err": None, "confirmationStatus": "confirmed"}]},
    })
    await B.maybe_burn(redis, kp)
    assert seen["amount"] == 10_000  # MAX_BURN_PER_TX
    assert S.owed_burn(redis.h[S.TREASURY_KEY]) == 999_999 - 10_000


async def test_maybe_burn_circuit_breaker_halts(redis, kp, monkeypatch):
    await redis.hset(S.TREASURY_KEY, mapping={
        "burn_accrued": "50000", "burn_fail_streak": "5",
    })
    monkeypatch.setattr(B, "build_and_sign", _boom("should not build while halted"))
    await B.maybe_burn(redis, kp)
    assert redis.h[S.TREASURY_KEY]["burn_halted"] == "1"


async def test_maybe_burn_submit_error_keeps_pending_for_resume(redis, kp, monkeypatch):
    await redis.hset(S.TREASURY_KEY, mapping={"burn_accrued": "5000"})

    async def fake_bas(k, mint, amount, memo, *, session=None):
        return b"\xaa\xbb", "SIGE", "BH"

    async def boom_submit(raw, *, session=None):
        raise B.RpcError("sendTransaction: blockhash not found")

    monkeypatch.setattr(B, "build_and_sign", fake_bas)
    monkeypatch.setattr(B, "submit", boom_submit)
    monkeypatch.setattr(B, "_sol_balance", _aval(1.0))
    await B.maybe_burn(redis, kp)
    h = redis.h[S.TREASURY_KEY]
    assert h["burn_pending_sig"] == "SIGE"   # crash-safety: recorded before submit
    assert "burned_total" not in h


async def test_maybe_burn_low_sol_defers(redis, kp, monkeypatch):
    await redis.hset(S.TREASURY_KEY, mapping={"burn_accrued": "5000"})
    monkeypatch.setattr(B, "build_and_sign", _boom("built despite low SOL"))
    monkeypatch.setattr(B, "_sol_balance", _aval(0.0001))
    await B.maybe_burn(redis, kp)
    assert "burn_pending_sig" not in redis.h.get(S.TREASURY_KEY, {})


async def test_end_to_end_record_then_burn(redis, kp, monkeypatch):
    """Three settlements accrue, one burn retires the lot (under the cap)."""
    for i in range(3):
        await S.record_settlement(redis, {
            "signature": f"{i:0>88}", "payer": "P", "amount_raw": 2_000,
            "endpoint": "refine", "block_time": 1_700_000_000 + i,
        })
    # 3 * (2000 * 50%) = 3000 owed, over the 1000 floor, under the 10000 cap
    assert S.owed_burn(redis.h[S.TREASURY_KEY]) == 3_000

    captured = {}

    async def fake_bas(k, mint, amount, memo, *, session=None):
        captured["amount"] = amount
        return b"\x01", "SIGE2E", "BH"

    monkeypatch.setattr(B, "build_and_sign", fake_bas)
    monkeypatch.setattr(B, "submit", _aval("SIGE2E"))
    monkeypatch.setattr(B, "_sol_balance", _aval(1.0))
    _stub_rpc(monkeypatch, {
        "getSignatureStatuses": {"value": [{"err": None, "confirmationStatus": "confirmed"}]},
    })
    await B.maybe_burn(redis, kp)
    assert captured["amount"] == 3_000
    assert redis.h[S.TREASURY_KEY]["burned_total"] == "3000"
    assert S.owed_burn(redis.h[S.TREASURY_KEY]) == 0


# ── helpers ──────────────────────────────────────────────────────────────

def _aval(v):
    async def f(*a, **kw):
        return v
    return f


def _boom(msg):
    async def f(*a, **kw):
        raise AssertionError(msg)
    return f
