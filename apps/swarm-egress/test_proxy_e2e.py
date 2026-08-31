"""swarm-egress end-to-end: a real client through the proxy to a fake upstream.

Covers the plaintext-HTTP path: allowlist enforcement and the outbound-secret
block. CONNECT/TLS tunnelling is exercised on staging (needs a real TLS peer).
"""
from __future__ import annotations

import asyncio

import aiohttp
import pytest
from aiohttp import web

import proxy as egress_proxy
from swarm_core.security import egress


@pytest.fixture()
async def upstream():
    async def ok(request):
        return web.Response(text="UPSTREAM-OK")

    app = web.Application()
    app.router.add_route("*", "/{tail:.*}", ok)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    port = runner.addresses[0][1]
    yield port
    await runner.cleanup()


@pytest.fixture(autouse=True)
def _audit_to_tmp(tmp_path, monkeypatch):
    monkeypatch.setenv("SWARM_AUDIT_LOG", str(tmp_path / "audit.jsonl"))
    monkeypatch.delenv("REDIS_URL", raising=False)


@pytest.fixture()
async def proxy_server(monkeypatch):
    # test policy: allow 127.0.0.1 for tok-test, no SSRF block, leak rules still on
    doc = {
        "ssrf_block": False,
        "deny_always": ["*.onion"],
        "default": {"allow": []},
        "callers": {"tester": {"token_env": "EGRESS_TOKEN_TESTER", "allow": ["127.0.0.1", "localhost"]}},
    }
    monkeypatch.setenv("EGRESS_TOKEN_TESTER", "tok-test")
    monkeypatch.setattr(egress, "_policy", egress.Policy(doc))
    monkeypatch.setattr(egress, "load", lambda force=False: egress._policy)

    server = await asyncio.start_server(egress_proxy.handle, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    task = asyncio.create_task(server.serve_forever())
    yield port
    server.close()
    task.cancel()


async def test_allowlisted_http_passes(proxy_server, upstream):
    async with aiohttp.ClientSession() as s:
        async with s.get(
            f"http://127.0.0.1:{upstream}/x",
            proxy=f"http://swarm:tok-test@127.0.0.1:{proxy_server}",
        ) as r:
            assert r.status == 200
            assert await r.text() == "UPSTREAM-OK"


async def test_unknown_token_is_denied(proxy_server, upstream):
    async with aiohttp.ClientSession() as s:
        async with s.get(
            f"http://127.0.0.1:{upstream}/x",
            proxy=f"http://swarm:WRONG@127.0.0.1:{proxy_server}",
        ) as r:
            assert r.status == 403


async def test_outbound_secret_is_blocked(proxy_server, upstream):
    async with aiohttp.ClientSession() as s:
        async with s.get(
            f"http://127.0.0.1:{upstream}/x",
            headers={"X-Leak": "sk-proj-abcd1234EFGH5678ijkl9012mnop"},
            proxy=f"http://swarm:tok-test@127.0.0.1:{proxy_server}",
        ) as r:
            assert r.status == 451
