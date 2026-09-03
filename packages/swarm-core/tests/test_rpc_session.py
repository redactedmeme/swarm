"""rpc(): a session the call opened is a session the call must close.

`owned` was computed and never used, so every caller that didn't pass a session
leaked a connector — settler's boot reconcile logged ~40 "Unclosed client
session" errors in 17 seconds.
"""
from __future__ import annotations

import asyncio

import pytest

# The x402 package re-exports `rpc` as a *function*, shadowing the module
# attribute — so reach for the module through sys.modules, not an import-as.
import importlib

rpc_mod = importlib.import_module("swarm_core.x402.rpc")


class _FakeResponse:
    status = 200

    async def json(self):
        return {"jsonrpc": "2.0", "id": 1, "result": {"ok": True}}

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class _FakeSession:
    def __init__(self):
        self.closed = False

    def post(self, *a, **kw):
        return _FakeResponse()

    async def close(self):
        self.closed = True


def _patch(monkeypatch, session):
    monkeypatch.setattr(rpc_mod.aiohttp, "ClientSession", lambda *a, **kw: session)
    monkeypatch.setattr(rpc_mod, "rpc_url", lambda: "http://rpc.invalid")


def test_owned_session_is_closed(monkeypatch):
    s = _FakeSession()
    _patch(monkeypatch, s)
    result = asyncio.run(rpc_mod.rpc("getHealth", []))
    assert result == {"ok": True}
    assert s.closed, "a session rpc() opened must be closed by rpc()"


def test_owned_session_is_closed_on_error(monkeypatch):
    s = _FakeSession()
    _patch(monkeypatch, s)

    class _Boom(_FakeResponse):
        status = 500

    monkeypatch.setattr(s, "post", lambda *a, **kw: _Boom())
    with pytest.raises(rpc_mod.RpcError):
        asyncio.run(rpc_mod.rpc("getHealth", []))
    assert s.closed, "the session must be closed even when the call raises"


def test_caller_supplied_session_is_left_open(monkeypatch):
    """A long-lived server passes its own session and owns its lifetime."""
    s = _FakeSession()
    _patch(monkeypatch, _FakeSession())  # a different one, so a leak is visible
    asyncio.run(rpc_mod.rpc("getHealth", [], session=s))
    assert not s.closed
