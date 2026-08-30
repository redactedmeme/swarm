"""Payment verification must fail closed on every axis that matters.

Each test here corresponds to a way the swarm could be served for free:
wrong mint, wrong recipient, short payment, stale signature, replay. The
replay test is the important one — without the claim guard a single valid
payment buys unlimited calls, and every other check still passes.

The RPC is stubbed rather than hit: these assert our verification logic, and a
test that depends on mainnet is a test that fails when mainnet is slow.
"""
from __future__ import annotations

import time

import pytest

from swarm_core import tokens
from swarm_core.x402 import verify as V

TREASURY = "TreasuryPubkey1111111111111111111111111111"
PAYER = "PayerPubkey11111111111111111111111111111111"
MINT = tokens.token_mint()
OTHER_MINT = "SomeOtherMint111111111111111111111111111111"
SIG = "5" * 88


def make_tx(
    *,
    mint: str = MINT,
    owner: str = TREASURY,
    pre: int | None = 0,
    post: int = 1_000_000_000,  # 1000 tokens at 6 decimals
    age_s: int = 5,
    err=None,
) -> dict:
    """A getTransaction result shaped like Solana's jsonParsed output."""
    balances_pre = []
    if pre is not None:
        balances_pre = [
            {
                "accountIndex": 3,
                "mint": mint,
                "owner": owner,
                "uiTokenAmount": {"amount": str(pre)},
            }
        ]
    return {
        "blockTime": int(time.time()) - age_s,
        "meta": {
            "err": err,
            "preTokenBalances": balances_pre,
            "postTokenBalances": [
                {
                    "accountIndex": 3,
                    "mint": mint,
                    "owner": owner,
                    "uiTokenAmount": {"amount": str(post)},
                }
            ],
        },
        "transaction": {"message": {"accountKeys": [{"pubkey": PAYER}]}},
    }


@pytest.fixture(autouse=True)
def treasury_env(monkeypatch):
    monkeypatch.setenv("SWARM_TREASURY_ADDRESS", TREASURY)


@pytest.fixture
def stub_rpc(monkeypatch):
    """Swap the RPC for a canned response."""

    def _install(result):
        async def fake_rpc(method, params, **kw):
            return result

        monkeypatch.setattr(V, "rpc", fake_rpc)

    return _install


class FakeRedis:
    """Just enough of redis.asyncio for the replay guard: SET NX."""

    def __init__(self):
        self.store: dict[str, object] = {}

    async def set(self, key, value, nx=False, ex=None):
        if nx and key in self.store:
            return None
        self.store[key] = value
        return True


# ── The happy path ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_valid_payment_returns_receipt(stub_rpc):
    stub_rpc(make_tx())
    receipt = await V.verify_payment(SIG, endpoint="refine", min_amount=1000)
    assert receipt.payer == PAYER
    assert receipt.amount == 1000
    assert receipt.amount_raw == 1_000_000_000
    assert receipt.mint == MINT
    assert receipt.endpoint == "refine"


@pytest.mark.asyncio
async def test_overpayment_is_accepted(stub_rpc):
    """Paying more than the price must not be rejected as a mismatch."""
    stub_rpc(make_tx(post=5_000_000_000))
    receipt = await V.verify_payment(SIG, endpoint="refine", min_amount=1000)
    assert receipt.amount == 5000


@pytest.mark.asyncio
async def test_fresh_ata_with_no_pre_balance(stub_rpc):
    """First-ever payment: the treasury ATA has no pre-balance entry at all."""
    stub_rpc(make_tx(pre=None))
    receipt = await V.verify_payment(SIG, endpoint="refine", min_amount=1000)
    assert receipt.amount == 1000


# ── Every way it must fail ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_wrong_mint_rejected(stub_rpc):
    stub_rpc(make_tx(mint=OTHER_MINT))
    with pytest.raises(V.PaymentError) as exc:
        await V.verify_payment(SIG, endpoint="refine", min_amount=1000)
    assert exc.value.reason == "wrong_recipient"


@pytest.mark.asyncio
async def test_wrong_recipient_rejected(stub_rpc):
    """Right mint, right amount, someone else's wallet."""
    stub_rpc(make_tx(owner="NotOurTreasury11111111111111111111111111111"))
    with pytest.raises(V.PaymentError) as exc:
        await V.verify_payment(SIG, endpoint="refine", min_amount=1000)
    assert exc.value.reason == "wrong_recipient"


@pytest.mark.asyncio
async def test_short_payment_rejected(stub_rpc):
    stub_rpc(make_tx(post=999_000_000))  # 999 tokens against a 1000 price
    with pytest.raises(V.PaymentError) as exc:
        await V.verify_payment(SIG, endpoint="refine", min_amount=1000)
    assert exc.value.reason == "insufficient"


@pytest.mark.asyncio
async def test_stale_payment_rejected(stub_rpc):
    stub_rpc(make_tx(age_s=V.FRESHNESS_WINDOW_S + 60))
    with pytest.raises(V.PaymentError) as exc:
        await V.verify_payment(SIG, endpoint="refine", min_amount=1000)
    assert exc.value.reason == "stale"


@pytest.mark.asyncio
async def test_failed_transaction_rejected(stub_rpc):
    """A reverted transaction moves nothing, however it looks in the log."""
    stub_rpc(make_tx(err={"InstructionError": [0, "Custom"]}))
    with pytest.raises(V.PaymentError) as exc:
        await V.verify_payment(SIG, endpoint="refine", min_amount=1000)
    assert exc.value.reason == "failed_transaction"


@pytest.mark.asyncio
async def test_unknown_signature_rejected(stub_rpc):
    stub_rpc(None)
    with pytest.raises(V.PaymentError) as exc:
        await V.verify_payment(SIG, endpoint="refine", min_amount=1000)
    assert exc.value.reason == "not_found"


@pytest.mark.asyncio
async def test_malformed_signature_rejected(stub_rpc):
    stub_rpc(make_tx())
    with pytest.raises(V.PaymentError) as exc:
        await V.verify_payment("nope", endpoint="refine", min_amount=1000)
    assert exc.value.reason == "malformed_signature"


@pytest.mark.asyncio
async def test_balance_decrease_is_not_a_payment(stub_rpc):
    """A withdrawal from the treasury must never read as an incoming payment."""
    stub_rpc(make_tx(pre=5_000_000_000, post=1_000_000_000))
    with pytest.raises(V.PaymentError) as exc:
        await V.verify_payment(SIG, endpoint="refine", min_amount=1000)
    assert exc.value.reason == "wrong_recipient"


# ── Replay: the one that matters most ───────────────────────────────────────


@pytest.mark.asyncio
async def test_signature_spends_exactly_once(stub_rpc):
    stub_rpc(make_tx())
    redis = FakeRedis()

    first = await V.verify_and_claim(redis, SIG, endpoint="refine", min_amount=1000)
    assert first.amount == 1000

    with pytest.raises(V.PaymentError) as exc:
        await V.verify_and_claim(redis, SIG, endpoint="refine", min_amount=1000)
    assert exc.value.reason == "replayed"


@pytest.mark.asyncio
async def test_rejected_payment_does_not_burn_its_signature(stub_rpc):
    """Underpaying then topping up must work.

    If a failed verification claimed the signature, a caller who paid too
    little could never retry, and an attacker could grief someone else's
    pending payment by presenting it against the wrong offer first.
    """
    redis = FakeRedis()
    stub_rpc(make_tx(post=999_000_000))
    with pytest.raises(V.PaymentError):
        await V.verify_and_claim(redis, SIG, endpoint="refine", min_amount=1000)

    assert redis.store == {}, "a rejected payment consumed its signature"

    stub_rpc(make_tx(post=1_000_000_000))
    receipt = await V.verify_and_claim(redis, SIG, endpoint="refine", min_amount=1000)
    assert receipt.amount == 1000


@pytest.mark.asyncio
async def test_rpc_failure_is_not_a_payment_failure(stub_rpc, monkeypatch):
    """An outage must not tell a paying caller their payment was bad."""

    async def boom(method, params, **kw):
        raise V.RpcError("connection reset")

    monkeypatch.setattr(V, "rpc", boom)
    with pytest.raises(V.RpcError):
        await V.verify_payment(SIG, endpoint="refine", min_amount=1000)


# ── Treasury must be configured ─────────────────────────────────────────────


def test_unset_treasury_raises(monkeypatch):
    """An empty payTo would verify any transaction at all."""
    monkeypatch.delenv("SWARM_TREASURY_ADDRESS", raising=False)
    with pytest.raises(RuntimeError, match="SWARM_TREASURY_ADDRESS"):
        tokens.treasury_address()
