"""proxy: only /livez is unauthenticated now; /health and friends require the
bearer token (IronClaw control 7 — no info-disclosure endpoint left open)."""
from __future__ import annotations

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

import main as proxy


@pytest.fixture()
async def client(monkeypatch):
    monkeypatch.setattr(proxy, "PROXY_TOKEN", "secret-tok")
    monkeypatch.setattr(proxy, "_TOKEN_MAP", {})
    app = web.Application(middlewares=[proxy._auth_middleware])
    app.router.add_get("/livez", proxy.handle_livez)
    app.router.add_get("/health", proxy.handle_health)
    app.router.add_get("/config", proxy.handle_config_get)
    c = TestClient(TestServer(app))
    await c.start_server()
    yield c
    await c.close()


async def test_livez_is_open(client):
    r = await client.get("/livez")
    assert r.status == 200
    assert await r.json() == {"ok": True}


async def test_health_requires_auth(client):
    assert (await client.get("/health")).status == 401
    r = await client.get("/health", headers={"Authorization": "Bearer secret-tok"})
    assert r.status == 200


async def test_config_requires_auth(client):
    assert (await client.get("/config")).status == 401
    r = await client.get("/config", headers={"Authorization": "Bearer secret-tok"})
    assert r.status == 200


async def test_wrong_token_rejected(client):
    assert (await client.get("/health", headers={"Authorization": "Bearer nope"})).status == 401
