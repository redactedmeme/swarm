"""solana.reserve: threshold / cooldown / daily-cap / dry-run vs execute.

All RPC and signing is stubbed - these tests exercise the decision logic, not
the chain.
"""
from __future__ import annotations

import time

import pytest

pytest.importorskip("solders")

from swarm_core.solana import reserve as R  # noqa: E402


class _AsyncFakeRedis:
    def __init__(self):
        self.kv: dict[str, str] = {}
        self.h: dict[str, dict] = {}

    async def get(self, k):
        return self.kv.get(k)

    async def set(self, k, v):
        self.kv[k] = str(v)

    async def incrbyfloat(self, k, amt):
        self.kv[k] = str(float(self.kv.get(k, 0)) + amt)
        return float(self.kv[k])

    async def expire(self, *a):
        return True

    async def hset(self, k, mapping=None, **kw):
        self.h.setdefault(k, {}).update(mapping or kw)

    async def hdel(self, k, *fields):
        for f in fields:
            self.h.get(k, {}).pop(f, None)

    def pipeline(self, transaction=True):
        return _Pipe(self)


class _Pipe:
    def __init__(self, r):
        self.r = r
        self.ops = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    def __getattr__(self, name):
        def q(*a, **kw):
            self.ops.append((name, a, kw))
            return self
        return q

    async def execute(self):
        for name, a, kw in self.ops:
            await getattr(self.r, name)(*a, **kw)
        self.ops.clear()


class _Ctl:
    balance = 0.0
    confirm_state = "confirmed"


@pytest.fixture()
def wired(monkeypatch):
    """address book + stubbed chain; returns (redis, calls, ctl)."""
    addr = "So1address1111111111111111111111111111111111"
    ctl = _Ctl()
    monkeypatch.setattr(R.keystore, "get_address", lambda a: addr if a == "hermes" else None)
    monkeypatch.setattr(R.keystore, "all_addresses", lambda: {"hermes": addr})

    calls = {"sent": 0}

    async def _bal(_a, *, session=None):
        return ctl.balance

    async def _bas(kp, to, lamports, *, session=None):
        return (b"raw", "sig123", "bh123")

    async def _submit(raw, *, session=None):
        calls["sent"] += 1

    async def _confirm(sig, *, session=None):
        return ctl.confirm_state

    monkeypatch.setattr(R._burn, "_sol_balance", _bal)
    monkeypatch.setattr(R, "build_and_sign_transfer", _bas)
    monkeypatch.setattr(R._burn, "submit", _submit)
    monkeypatch.setattr(R._burn, "confirm", _confirm)
    monkeypatch.setattr(R, "_authorized", lambda: True)
    monkeypatch.setattr(R, "reserve_keypair", lambda: object())

    return _AsyncFakeRedis(), calls, ctl


def _cfg(**over):
    base = dict(execute=True, min_sol=0.02, refuel_sol=0.05,
                daily_cap_sol=0.2, cooldown_s=900, every_s=300)
    base.update(over)
    return base


@pytest.mark.asyncio
async def test_above_threshold_is_noop(wired):
    redis, calls, ctl = wired
    ctl.balance = 1.0
    res = await R.check_and_refuel_agent(redis, "hermes", cfg=_cfg())
    assert res["status"] == "ok" and calls["sent"] == 0


@pytest.mark.asyncio
async def test_dry_run_sends_nothing(wired):
    redis, calls, ctl = wired
    ctl.balance = 0.001
    res = await R.check_and_refuel_agent(redis, "hermes", cfg=_cfg(execute=False))
    assert res["status"] == "dryrun" and calls["sent"] == 0


@pytest.mark.asyncio
async def test_execute_refuels_and_records(wired):
    redis, calls, ctl = wired
    ctl.balance = 0.001
    res = await R.check_and_refuel_agent(redis, "hermes", cfg=_cfg())
    assert res["status"] == "refuelled" and calls["sent"] == 1
    day_key = next(k for k in redis.kv if k.startswith("swarm:reserve:spent:hermes:"))
    assert float(redis.kv[day_key]) == pytest.approx(0.05)
    assert f"swarm:reserve:last:hermes" in redis.kv


@pytest.mark.asyncio
async def test_cooldown_blocks_second_send(wired):
    redis, calls, ctl = wired
    ctl.balance = 0.001
    await redis.set("swarm:reserve:last:hermes", time.time())
    res = await R.check_and_refuel_agent(redis, "hermes", cfg=_cfg())
    assert res["status"] == "cooldown" and calls["sent"] == 0


@pytest.mark.asyncio
async def test_daily_cap_blocks_send(wired):
    redis, calls, ctl = wired
    ctl.balance = 0.001
    from datetime import datetime, timezone
    day = datetime.now(timezone.utc).strftime("%Y%m%d")
    await redis.set(f"swarm:reserve:spent:hermes:{day}", 0.18)
    res = await R.check_and_refuel_agent(redis, "hermes", cfg=_cfg())
    assert res["status"] == "capped" and calls["sent"] == 0


@pytest.mark.asyncio
async def test_no_wallet(wired):
    redis, _, ctl = wired
    res = await R.check_and_refuel_agent(redis, "smolting", cfg=_cfg())
    assert res["status"] == "no_wallet"
