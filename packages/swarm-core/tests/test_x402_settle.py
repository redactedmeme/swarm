"""Settlement accounting must not lose or double-count a base unit.

Every payment the swarm accepts is split burn / compute / rewards and
accumulated in `swarm:treasury`. The failure modes that matter here are
arithmetic (a slice that doesn't sum back to the payment) and idempotency (a
re-delivered settlement counted twice) — both of which quietly corrupt a public
burn figure. The Redis layer is faked; these assert the logic.
"""
from __future__ import annotations

import ast
import json
import pathlib
import time

import pytest

from swarm_core import tokens
from swarm_core.x402 import settle as S
from fakeredis import FakeRedis

SIG = "5" * 88
PAYER = "PayerPubkey11111111111111111111111111111111"


def make_receipt(*, sig: str = SIG, amount_raw: int = 1_000_000_000,
                 payer: str = PAYER, endpoint: str = "refine",
                 block_time: int | None = None) -> dict:
    """Shaped like `PaymentReceipt.to_dict()` — the writer's input."""
    return {
        "signature": sig,
        "payer": payer,
        "amount": str(tokens.from_base_units(amount_raw)),
        "amount_raw": amount_raw,
        "mint": tokens.token_mint(),
        "endpoint": endpoint,
        "block_time": block_time if block_time is not None else int(time.time()),
    }


@pytest.fixture
def redis():
    return FakeRedis()


@pytest.fixture(autouse=True)
def _reset_runway_warn():
    S._runway_none_warned = False
    yield


# ── Split arithmetic ──────────────────────────────────────────────────────

def test_split_clean_divisor():
    assert S.compute_split(1_000_000_000) == (500_000_000, 300_000_000, 200_000_000)


def test_split_remainder_goes_to_burn():
    burn, compute, rewards = S.compute_split(1_000_001)
    assert (compute, rewards) == (300_000, 200_000)
    assert burn == 500_001
    assert burn + compute + rewards == 1_000_001


@pytest.mark.parametrize("amount", [0, 1, 2, 3, 7, 99, 101, 1_000_003, 999_999_937])
def test_split_always_sums_and_stays_in_range(amount):
    burn, compute, rewards = S.compute_split(amount)
    assert burn + compute + rewards == amount
    assert min(burn, compute, rewards) >= 0
    assert max(burn, compute, rewards) <= amount


def test_split_negative_rejected():
    with pytest.raises(ValueError):
        S.compute_split(-1)


def test_split_honours_env_override(monkeypatch):
    monkeypatch.setenv("SPLIT_BURN_PCT", "70")
    monkeypatch.setenv("SPLIT_COMPUTE_PCT", "20")
    monkeypatch.setenv("SPLIT_REWARDS_PCT", "10")
    burn, compute, rewards = S.compute_split(1_000_000)
    assert (burn, compute, rewards) == (700_000, 200_000, 100_000)


# ── Runway cap ────────────────────────────────────────────────────────────

def test_runway_cap_under_threshold_passes_through():
    assert S.apply_runway_cap(300, runway_days=10.0, cap_days=90) == (300, 0)


def test_runway_cap_over_threshold_rolls_into_burn():
    assert S.apply_runway_cap(300, runway_days=120.0, cap_days=90) == (0, 300)


def test_runway_cap_at_threshold_is_not_over():
    assert S.apply_runway_cap(300, runway_days=90.0, cap_days=90) == (300, 0)


def test_runway_cap_none_passes_through():
    assert S.apply_runway_cap(300, runway_days=None, cap_days=90) == (300, 0)


# ── record_settlement ─────────────────────────────────────────────────────

async def test_record_accumulates(redis):
    assert await S.record_settlement(redis, make_receipt()) is True
    h = redis.h[S.TREASURY_KEY]
    assert h["revenue_total"] == "1000000000"
    assert h["burn_accrued"] == "500000000"
    assert h["compute_accrued"] == "300000000"
    assert h["rewards_accrued"] == "200000000"
    assert h["settlements_total"] == "1"
    assert h["last_settlement_sig"] == SIG


async def test_record_two_distinct_sigs_add_up(redis):
    await S.record_settlement(redis, make_receipt(sig="a" * 88, amount_raw=1_000))
    await S.record_settlement(redis, make_receipt(sig="b" * 88, amount_raw=3_000))
    h = redis.h[S.TREASURY_KEY]
    assert h["revenue_total"] == "4000"
    assert h["settlements_total"] == "2"
    assert h["last_settlement_sig"] == "b" * 88


async def test_record_is_idempotent_on_signature(redis):
    assert await S.record_settlement(redis, make_receipt()) is True
    assert await S.record_settlement(redis, make_receipt()) is False
    assert redis.h[S.TREASURY_KEY]["settlements_total"] == "1"
    assert redis.h[S.TREASURY_KEY]["revenue_total"] == "1000000000"


async def test_record_writes_ts_zset_and_log(redis):
    await S.record_settlement(redis, make_receipt(block_time=1_700_000_000))
    assert redis.z[S.SETTLEMENTS_TS_KEY][SIG] == 1_700_000_000
    entry = json.loads(redis.l[S.SETTLEMENTS_LOG_KEY][0])
    assert entry["sig"] == SIG
    assert entry["burn"] == 500_000_000
    assert entry["ts"] == 1_700_000_000


async def test_log_is_capped(redis, monkeypatch):
    monkeypatch.setattr(S, "LOG_MAX", 3)
    for i in range(6):
        await S.record_settlement(redis, make_receipt(sig=f"{i:0>88}", amount_raw=10))
    assert await redis.llen(S.SETTLEMENTS_LOG_KEY) == 3
    newest = json.loads(redis.l[S.SETTLEMENTS_LOG_KEY][0])
    assert newest["sig"] == f"{5:0>88}"


async def test_record_applies_runway_cap_from_cached_field(redis, monkeypatch):
    monkeypatch.setattr(tokens, "COMPUTE_RUNWAY_CAP_DAYS", 90)
    await redis.hset(S.TREASURY_KEY, "runway_days", "150")
    await S.record_settlement(redis, make_receipt(amount_raw=1_000_000_000))
    h = redis.h[S.TREASURY_KEY]
    # compute slice (300M) rolled into burn: burn 500M + 300M, compute 0
    assert h["compute_accrued"] == "0"
    assert h["burn_accrued"] == "800000000"
    assert h["rewards_accrued"] == "200000000"


async def test_record_without_runway_field_is_uncapped(redis):
    await S.record_settlement(redis, make_receipt(amount_raw=1_000_000_000))
    h = redis.h[S.TREASURY_KEY]
    assert h["compute_accrued"] == "300000000"
    assert h["burn_accrued"] == "500000000"


async def test_malformed_receipt_writes_nothing(redis):
    with pytest.raises(ValueError):
        await S.record_settlement(redis, {"payer": PAYER})  # no signature/amount_raw
    assert S.TREASURY_KEY not in redis.h
    assert not redis.s.get(S.SEEN_KEY)


async def test_failed_transaction_rolls_back_and_stays_unseen(redis, monkeypatch):
    """If the MULTI/EXEC fails, nothing commits and the sig can be retried."""
    boom = {"n": 0}
    real_zadd = redis.zadd

    async def flaky_zadd(*a, **kw):
        boom["n"] += 1
        raise RuntimeError("redis went away mid-transaction")

    monkeypatch.setattr(redis, "zadd", flaky_zadd)
    with pytest.raises(RuntimeError):
        await S.record_settlement(redis, make_receipt())
    assert S.TREASURY_KEY not in redis.h
    assert not await redis.sismember(S.SEEN_KEY, SIG)

    # recovers once redis is healthy again
    monkeypatch.setattr(redis, "zadd", real_zadd)
    assert await S.record_settlement(redis, make_receipt()) is True


# ── recount_24h ───────────────────────────────────────────────────────────

async def test_recount_drops_old_and_publishes_count(redis):
    now = 2_000_000_000
    await redis.zadd(S.SETTLEMENTS_TS_KEY, {"old": now - 90_000})   # >24h
    await redis.zadd(S.SETTLEMENTS_TS_KEY, {"recent1": now - 100})
    await redis.zadd(S.SETTLEMENTS_TS_KEY, {"recent2": now - 200})
    count = await S.recount_24h(redis, now=now)
    assert count == 2
    assert redis.h[S.TREASURY_KEY]["settlements_24h"] == "2"
    assert "old" not in redis.z[S.SETTLEMENTS_TS_KEY]


# ── owed_burn ─────────────────────────────────────────────────────────────

def test_owed_burn_derivation():
    assert S.owed_burn({"burn_accrued": "1000", "burned_total": "400"}) == 600
    assert S.owed_burn(
        {"burn_accrued": "1000", "burned_total": "400", "burn_pending_amount": "200"}
    ) == 400
    assert S.owed_burn({"burn_accrued": "100", "burned_total": "300"}) == 0
    assert S.owed_burn({}) == 0


# ── The import invariant ──────────────────────────────────────────────────

def test_settle_has_no_toplevel_solana_import():
    """`settle.py` runs inline in the refinery, which builds without the
    `solana` extra. A stray top-level `import solders` would break that import
    path and turn CI red."""
    src = pathlib.Path(S.__file__).read_text(encoding="utf-8")
    tree = ast.parse(src)
    banned = {"solders", "solana", "anchorpy"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name.split(".")[0] not in banned, alias.name
        elif isinstance(node, ast.ImportFrom):
            root = (node.module or "").split(".")[0]
            assert root not in banned, node.module
