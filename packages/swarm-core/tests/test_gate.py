"""The holder gate: a wallet must prove itself and clear a threshold. Every
test here is a way it could let the wrong wallet in or lock the right one out.
"""
from __future__ import annotations

import ast
import base64
import pathlib
from decimal import Decimal

import pytest

pytest.importorskip("cryptography")
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey  # noqa: E402
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat  # noqa: E402


def _pub_b58(kp) -> str:
    return _b58encode(kp.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw))

from swarm_core import gate as G  # noqa: E402
from swarm_core import tokens  # noqa: E402
from fakeredis import FakeRedis  # noqa: E402

_B58 = G._B58_ALPHABET


def _b58encode(b: bytes) -> str:
    n = int.from_bytes(b, "big")
    out = bytearray()
    while n:
        n, r = divmod(n, 58)
        out.append(_B58[r])
    out.extend(_B58[0:1] * (len(b) - len(b.lstrip(b"\x00"))))
    return out[::-1].decode()


@pytest.fixture
def kp():
    return Ed25519PrivateKey.generate()


@pytest.fixture
def wallet(kp):
    return _pub_b58(kp)


@pytest.fixture
def redis():
    return FakeRedis()


def _sign(kp, message: str) -> str:
    return base64.b64encode(kp.sign(message.encode("utf-8"))).decode()


# ── verify_signature ─────────────────────────────────────────────────────

def test_verify_roundtrip(kp, wallet):
    msg = "hello nonce line\nnonce: abc"
    assert G.verify_signature(wallet, msg, _sign(kp, msg)) is True


def test_verify_rejects_tampered_message(kp, wallet):
    sig = _sign(kp, "original")
    assert G.verify_signature(wallet, "tampered", sig) is False


def test_verify_rejects_tampered_signature(kp, wallet):
    sig = bytearray(base64.b64decode(_sign(kp, "m")))
    sig[0] ^= 0xFF
    assert G.verify_signature(wallet, "m", base64.b64encode(bytes(sig)).decode()) is False


def test_verify_rejects_wrong_pubkey(kp):
    other = _pub_b58(Ed25519PrivateKey.generate())
    assert G.verify_signature(other, "m", _sign(kp, "m")) is False


def test_verify_rejects_garbage_wallet(kp):
    assert G.verify_signature("not-base58-!!!", "m", _sign(kp, "m")) is False
    assert G.verify_signature("1111", "m", _sign(kp, "m")) is False  # too short


# ── issue_nonce ──────────────────────────────────────────────────────────

async def test_issue_nonce_stores_it(redis, wallet):
    out = await G.issue_nonce(redis, wallet)
    assert redis.kv[f"{G.NONCE_KEY}{wallet}"] == out["nonce"]
    assert f"nonce: {out['nonce']}" in out["message"]
    assert wallet in out["message"]


async def test_issue_nonce_rejects_bad_wallet(redis):
    with pytest.raises(G.GateError):
        await G.issue_nonce(redis, "xxx")


# ── authorize ────────────────────────────────────────────────────────────

async def _challenge(redis, kp, wallet):
    out = await G.issue_nonce(redis, wallet)
    return out["message"], _sign(kp, out["message"])


async def test_authorize_operator_tier(redis, kp, wallet, monkeypatch):
    async def bal(owner, **kw):
        return Decimal(1_500_000)
    monkeypatch.setattr(G, "token_balance", bal)

    msg, sig = await _challenge(redis, kp, wallet)
    res = await G.authorize(redis, wallet, msg, sig)
    assert res["ok"] is True
    assert res["tier"] == "operator"
    assert "terminal" in res["grants"]
    assert redis.h[f"{G.GRANTS_KEY}{wallet}"]["tier"] == "operator"
    # nonce consumed
    assert f"{G.NONCE_KEY}{wallet}" not in redis.kv
    with pytest.raises(G.GateError) as e:
        await G.authorize(redis, wallet, msg, sig)
    assert e.value.reason == "nonce"


async def test_authorize_below_threshold(redis, kp, wallet, monkeypatch):
    monkeypatch.setattr(G, "token_balance", lambda o, **k: _ret(Decimal(900_000)))
    msg, sig = await _challenge(redis, kp, wallet)
    res = await G.authorize(redis, wallet, msg, sig)
    assert res["ok"] is False
    assert res["tier"] is None
    assert res["min_required"] == tokens.TIERS[0].threshold
    assert f"{G.NONCE_KEY}{wallet}" not in redis.kv  # still consumed


async def test_authorize_rejects_wrong_nonce_in_message(redis, kp, wallet, monkeypatch):
    monkeypatch.setattr(G, "token_balance", lambda o, **k: _ret(Decimal(2_000_000)))
    await G.issue_nonce(redis, wallet)
    forged = G.challenge_message(wallet, "some-other-nonce", "2026-01-01T00:00:00+00:00")
    with pytest.raises(G.GateError) as e:
        await G.authorize(redis, wallet, forged, _sign(kp, forged))
    assert e.value.reason == "nonce"


async def test_authorize_replay_after_consumption(redis, kp, wallet, monkeypatch):
    monkeypatch.setattr(G, "token_balance", lambda o, **k: _ret(Decimal(2_000_000)))
    msg, sig = await _challenge(redis, kp, wallet)
    await G.authorize(redis, wallet, msg, sig)
    with pytest.raises(G.GateError) as e:
        await G.authorize(redis, wallet, msg, sig)
    assert e.value.reason == "nonce"


async def test_authorize_bad_signature_keeps_nonce(redis, kp, wallet, monkeypatch):
    monkeypatch.setattr(G, "token_balance", lambda o, **k: _ret(Decimal(2_000_000)))
    msg, _ = await _challenge(redis, kp, wallet)
    with pytest.raises(G.GateError) as e:
        await G.authorize(redis, wallet, msg, base64.b64encode(b"\x00" * 64).decode())
    assert e.value.reason == "bad_signature"
    assert f"{G.NONCE_KEY}{wallet}" in redis.kv  # retryable


async def test_authorize_rpc_down_keeps_nonce(redis, kp, wallet, monkeypatch):
    monkeypatch.setattr(G, "token_balance", lambda o, **k: _ret(None))
    msg, sig = await _challenge(redis, kp, wallet)
    with pytest.raises(G.GateError) as e:
        await G.authorize(redis, wallet, msg, sig)
    assert e.value.reason == "rpc_unavailable"
    assert f"{G.NONCE_KEY}{wallet}" in redis.kv  # retryable


# ── import invariant ─────────────────────────────────────────────────────

# ── required_grant ───────────────────────────────────────────────────────
#
# The gate used to hardcode `ok = "terminal" in grants`. Anything gated above
# the bottom rung — the alpha feed at the architect tier — needs the caller to
# say which grant it means, and needs `min_required` to quote that grant's real
# threshold rather than TIERS[0].


async def test_authorize_defaults_to_terminal_grant(redis, kp, wallet, monkeypatch):
    """The pre-existing caller (apps/terminal) passes no grant and must not change."""
    monkeypatch.setattr(G, "token_balance", lambda o, **k: _ret(Decimal(1_500_000)))
    msg, sig = await _challenge(redis, kp, wallet)
    res = await G.authorize(redis, wallet, msg, sig)
    assert res["ok"] is True
    assert res["required_grant"] == "terminal"
    assert res["min_required"] == 1_000_000


async def test_operator_balance_denied_alpha_feed(redis, kp, wallet, monkeypatch):
    """Clearing the terminal gate must not carry you into the alpha feed."""
    monkeypatch.setattr(G, "token_balance", lambda o, **k: _ret(Decimal(1_500_000)))
    msg, sig = await _challenge(redis, kp, wallet)
    res = await G.authorize(redis, wallet, msg, sig, required_grant="alpha-feed")
    assert res["ok"] is False
    assert res["tier"] == "operator"          # they are a holder, just not enough
    assert res["min_required"] == 10_000_000  # the number to quote them


async def test_architect_balance_allowed_alpha_feed(redis, kp, wallet, monkeypatch):
    monkeypatch.setattr(G, "token_balance", lambda o, **k: _ret(Decimal(10_000_000)))
    msg, sig = await _challenge(redis, kp, wallet)
    res = await G.authorize(redis, wallet, msg, sig, required_grant="alpha-feed")
    assert res["ok"] is True
    assert res["tier"] == "architect"
    assert "alpha-feed" in res["grants"]


async def test_alpha_feed_boundary_is_exact(redis, kp, wallet, monkeypatch):
    """One token short is out; exactly on the threshold is in."""
    monkeypatch.setattr(G, "token_balance", lambda o, **k: _ret(Decimal(9_999_999)))
    msg, sig = await _challenge(redis, kp, wallet)
    assert (await G.authorize(redis, wallet, msg, sig,
                              required_grant="alpha-feed"))["ok"] is False


async def test_unknown_grant_is_denied_not_crashed(redis, kp, wallet, monkeypatch):
    """A typo'd grant name must fail closed, with no threshold to quote."""
    monkeypatch.setattr(G, "token_balance", lambda o, **k: _ret(Decimal(100_000_000)))
    msg, sig = await _challenge(redis, kp, wallet)
    res = await G.authorize(redis, wallet, msg, sig, required_grant="nope")
    assert res["ok"] is False
    assert res["min_required"] is None


def test_alpha_feed_is_reachable_and_above_terminal():
    """Guards the tier table itself: the grant must exist and cost more."""
    assert tokens.threshold_for_grant("alpha-feed") == 10_000_000
    assert tokens.threshold_for_grant("alpha-feed") > tokens.threshold_for_grant("terminal")
    assert "alpha-feed" in tokens.grants_for(10_000_000)
    assert "alpha-feed" not in tokens.grants_for(1_000_000)
    assert tokens.threshold_for_grant("does-not-exist") is None


def test_gate_has_no_toplevel_solana_import():
    tree = ast.parse(pathlib.Path(G.__file__).read_text(encoding="utf-8"))
    banned = {"solders", "solana", "anchorpy"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                assert a.name.split(".")[0] not in banned, a.name
        elif isinstance(node, ast.ImportFrom):
            assert (node.module or "").split(".")[0] not in banned, node.module


async def _ret(v):
    return v
