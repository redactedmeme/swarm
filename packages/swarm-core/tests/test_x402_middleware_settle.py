"""The payment middleware must record every genuinely-paid call into the
ledger, inline, without ever failing the call when that record can't be written.
"""
from __future__ import annotations

from decimal import Decimal

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from swarm_core.x402 import middleware as M
from swarm_core.x402 import settle as S
from swarm_core.x402.verify import PaymentReceipt
from fakeredis import FakeRedis

RECEIPT = PaymentReceipt(
    signature="p" * 88, payer="Payer1111", amount=Decimal("1000"),
    amount_raw=1_000_000_000, mint="mint", endpoint="refine", block_time=1_700_000_000,
)


def _app(redis, **kw):
    app = web.Application()
    app["redis"] = redis

    @M.require_payment("refine", **kw)
    async def handler(request):
        return web.json_response({"ok": True})

    app.router.add_post("/q", handler)
    return app


async def _client(app):
    c = TestClient(TestServer(app))
    await c.start_server()
    return c


async def test_paid_call_records_settlement(monkeypatch):
    redis = FakeRedis()

    async def fake_vac(r, sig, **kw):
        return RECEIPT

    monkeypatch.setattr(M, "verify_and_claim", fake_vac)

    c = await _client(_app(redis))
    try:
        resp = await c.post("/q", headers={M.PAYMENT_HEADER: "p" * 88}, json={})
        assert resp.status == 200 and (await resp.json()) == {"ok": True}
    finally:
        await c.close()

    h = redis.h[S.TREASURY_KEY]
    assert h["revenue_total"] == "1000000000"
    assert h["burn_accrued"] == "500000000"
    assert h["settlements_total"] == "1"
    assert "p" * 88 in redis.s[S.SEEN_KEY]


async def test_bypassed_call_records_nothing(monkeypatch):
    redis = FakeRedis()
    monkeypatch.setattr(M, "verify_and_claim",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("verify hit")))

    c = await _client(_app(redis, bypass=lambda r: True))
    try:
        resp = await c.post("/q", json={})
        assert resp.status == 200
    finally:
        await c.close()

    assert S.TREASURY_KEY not in redis.h


async def test_settlement_failure_does_not_break_the_paid_call(monkeypatch):
    redis = FakeRedis()

    async def fake_vac(r, sig, **kw):
        return RECEIPT

    async def boom(*a, **k):
        raise RuntimeError("redis unavailable")

    monkeypatch.setattr(M, "verify_and_claim", fake_vac)
    monkeypatch.setattr("swarm_core.x402.settle.record_settlement", boom)

    c = await _client(_app(redis))
    try:
        resp = await c.post("/q", headers={M.PAYMENT_HEADER: "p" * 88}, json={})
        assert resp.status == 200 and (await resp.json()) == {"ok": True}
    finally:
        await c.close()


async def test_settle_false_skips_recording(monkeypatch):
    redis = FakeRedis()

    async def fake_vac(r, sig, **kw):
        return RECEIPT

    monkeypatch.setattr(M, "verify_and_claim", fake_vac)

    c = await _client(_app(redis, settle=False))
    try:
        resp = await c.post("/q", headers={M.PAYMENT_HEADER: "p" * 88}, json={})
        assert resp.status == 200
    finally:
        await c.close()

    assert S.TREASURY_KEY not in redis.h
