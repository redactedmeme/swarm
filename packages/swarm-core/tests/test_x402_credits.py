"""Credits: deposits must credit exactly one balance and never double-count,
and proxied-inference spend must flow through the same burn split as any job.
"""
from __future__ import annotations

import ast
import json
import pathlib

import pytest

from swarm_core import tokens
from swarm_core.x402 import credits as C
from swarm_core.x402 import settle as S
from fakeredis import FakeRedis

TREASURY = "9xLGQrf3uge7tncimyrKjFcDEDptQRS2QG6Zxv67z7r"
MINT = tokens.token_mint()


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("SWARM_TREASURY_ADDRESS", TREASURY)


@pytest.fixture
def redis():
    return FakeRedis()


def _tx(*, memo=None, delta_base_units=0, err=None, program_form="parsed"):
    """A jsonParsed getTransaction result: an inbound `delta` of MINT to the
    treasury, optionally carrying a memo."""
    instrs = []
    if memo is not None:
        if program_form == "parsed":
            instrs.append({"programId": C.MEMO_PROGRAM_ID, "parsed": memo})
        else:  # log-only form
            pass
    logs = []
    if memo is not None and program_form == "logs":
        logs.append(f'Program log: Memo (len {len(memo)}): "{memo}"')
    post = [{"accountIndex": 1, "mint": MINT, "owner": TREASURY,
             "uiTokenAmount": {"amount": str(delta_base_units)}}]
    pre = [{"accountIndex": 1, "mint": MINT, "owner": TREASURY,
            "uiTokenAmount": {"amount": "0"}}]
    return {
        "blockTime": 1_700_000_000,
        "meta": {"err": err, "preTokenBalances": pre, "postTokenBalances": post,
                 "logMessages": logs},
        "transaction": {"message": {"instructions": instrs,
                                    "accountKeys": [{"pubkey": "PayerXYZ"}]}},
    }


def _stub_rpc(monkeypatch, *, sigs, txs):
    """sigs: list of {signature,err}; txs: {sig: tx-dict}."""
    async def fake_rpc(method, params, *, session=None, timeout=15.0):
        if method == "getSignaturesForAddress":
            return sigs
        if method == "getTransaction":
            return txs.get(params[0])
        raise AssertionError(f"unexpected rpc {method}")
    monkeypatch.setattr(C, "rpc", fake_rpc)


# ── _memo_of ──────────────────────────────────────────────────────────────

def test_memo_of_parsed_instruction():
    assert C._memo_of(_tx(memo="redacted-credits:acme")) == "redacted-credits:acme"


def test_memo_of_log_fallback():
    tx = _tx(memo="redacted-credits:beta", program_form="logs")
    assert C._memo_of(tx) == "redacted-credits:beta"


def test_memo_of_absent():
    assert C._memo_of(_tx()) is None


# ── credit_deposits ──────────────────────────────────────────────────────

async def test_credit_deposit_credits_balance_and_double_marks(redis, monkeypatch):
    amt = tokens.to_base_units(50_000)
    _stub_rpc(monkeypatch,
              sigs=[{"signature": "DEP1", "err": None}],
              txs={"DEP1": _tx(memo="redacted-credits:acme", delta_base_units=amt)})
    n = await C.credit_deposits(redis)
    assert n == 1
    assert float(redis.kv[f"{C.BALANCE_PREFIX}acme"]) == 50_000
    assert await redis.sismember(C.DEPOSITS_SEEN_KEY, "DEP1")
    assert await redis.sismember(S.SEEN_KEY, "DEP1")  # reconcile_chain will skip it
    assert len(redis.l[C.DEPOSITS_LOG_KEY]) == 1


async def test_non_memo_inbound_is_ignored(redis, monkeypatch):
    _stub_rpc(monkeypatch,
              sigs=[{"signature": "X1", "err": None}],
              txs={"X1": _tx(delta_base_units=tokens.to_base_units(1000))})
    assert await C.credit_deposits(redis) == 0
    assert not redis.kv


async def test_wrong_prefix_ignored(redis, monkeypatch):
    _stub_rpc(monkeypatch,
              sigs=[{"signature": "X2", "err": None}],
              txs={"X2": _tx(memo="swarm-settle v1 burn=5", delta_base_units=999)})
    assert await C.credit_deposits(redis) == 0


async def test_already_seen_deposit_skipped(redis, monkeypatch):
    await redis.sadd(C.DEPOSITS_SEEN_KEY, "DEP1")
    _stub_rpc(monkeypatch, sigs=[{"signature": "DEP1", "err": None}], txs={})
    assert await C.credit_deposits(redis) == 0


async def test_settled_sig_skipped(redis, monkeypatch):
    await redis.sadd(S.SEEN_KEY, "DEP1")
    _stub_rpc(monkeypatch, sigs=[{"signature": "DEP1", "err": None}], txs={})
    assert await C.credit_deposits(redis) == 0


async def test_zero_delta_skipped(redis, monkeypatch):
    _stub_rpc(monkeypatch,
              sigs=[{"signature": "Z", "err": None}],
              txs={"Z": _tx(memo="redacted-credits:acme", delta_base_units=0)})
    assert await C.credit_deposits(redis) == 0


async def test_failed_tx_signature_skipped(redis, monkeypatch):
    _stub_rpc(monkeypatch, sigs=[{"signature": "F", "err": {"x": 1}}], txs={})
    assert await C.credit_deposits(redis) == 0


# ── drain_spend_queue ────────────────────────────────────────────────────

def _spend(nonce, whole):
    return json.dumps({"client": "acme", "base_units": tokens.to_base_units(whole),
                       "nonce": nonce, "ts": 1_700_000_100})


async def test_drain_settles_each_entry(redis):
    for i in range(3):
        await redis.lpush(C.SPEND_QUEUE_KEY, _spend(f"n{i}", 1_000))
    n = await C.drain_spend_queue(redis)
    assert n == 3
    h = redis.h[S.TREASURY_KEY]
    assert h["revenue_total"] == str(tokens.to_base_units(3_000))
    assert h["burn_accrued"] == str(tokens.to_base_units(1_500))  # 50%
    assert h["settlements_total"] == "3"


async def test_drain_is_idempotent_on_replayed_nonce(redis):
    await redis.lpush(C.SPEND_QUEUE_KEY, _spend("dup", 1_000))
    await C.drain_spend_queue(redis)
    await redis.lpush(C.SPEND_QUEUE_KEY, _spend("dup", 1_000))  # same nonce again
    await C.drain_spend_queue(redis)
    assert redis.h[S.TREASURY_KEY]["settlements_total"] == "1"


async def test_drain_drops_malformed_entry(redis):
    await redis.lpush(C.SPEND_QUEUE_KEY, "{bad json")
    await redis.lpush(C.SPEND_QUEUE_KEY, _spend("ok", 500))
    n = await C.drain_spend_queue(redis)
    assert n == 1
    assert redis.h[S.TREASURY_KEY]["settlements_total"] == "1"


async def test_drain_requeues_on_settlement_error(redis, monkeypatch):
    await redis.lpush(C.SPEND_QUEUE_KEY, _spend("n", 500))

    async def boom(*a, **k):
        raise RuntimeError("redis down")

    monkeypatch.setattr(S, "record_settlement", boom)
    n = await C.drain_spend_queue(redis)
    assert n == 0
    assert len(redis.l[C.SPEND_QUEUE_KEY]) == 1  # put back


# ── import invariant ─────────────────────────────────────────────────────

def test_credits_has_no_toplevel_solana_import():
    tree = ast.parse(pathlib.Path(C.__file__).read_text(encoding="utf-8"))
    banned = {"solders", "solana", "anchorpy"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                assert a.name.split(".")[0] not in banned, a.name
        elif isinstance(node, ast.ImportFrom):
            assert (node.module or "").split(".")[0] not in banned, node.module
