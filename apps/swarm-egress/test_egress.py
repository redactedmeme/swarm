"""egress policy: allowlist, SSRF block, per-caller tokens, deny-always."""
from __future__ import annotations

import importlib

import pytest

from swarm_core.security import egress


_PUBLIC = [(2, 1, 6, "", ("93.184.216.34", 0))]  # example.com; a real public IP


@pytest.fixture()
def pol(monkeypatch):
    monkeypatch.setenv("EGRESS_TOKEN_HERMES", "tok-hermes")
    monkeypatch.setenv("EGRESS_TOKEN_RUNTIME", "tok-runtime")
    # deterministic DNS: named hosts resolve public, *.local / *.internal don't
    def fake_getaddrinfo(host, *a, **k):
        if host in ("127.0.0.1", "10.1.2.3", "169.254.169.254"):
            return [(2, 1, 6, "", (host, 0))]
        if "internal" in host or host.endswith(".local"):
            raise OSError("name resolution failed")
        return _PUBLIC
    monkeypatch.setattr(egress.socket, "getaddrinfo", fake_getaddrinfo)
    importlib.reload(egress)
    monkeypatch.setattr(egress.socket, "getaddrinfo", fake_getaddrinfo)
    return egress.load(force=True)


def test_default_caller_is_tiny(pol):
    assert pol.decide("api.github.com", None).allow
    assert not pol.decide("api.telegram.org", None).allow


def test_hermes_allowlist(pol):
    assert pol.decide("api.telegram.org", "tok-hermes").allow
    assert pol.decide("sub.moltbook.com", "tok-hermes").allow          # wildcard
    d = pol.decide("evil.example.com", "tok-hermes")
    assert not d.allow and "allowlist" in d.reason


def test_runtime_open_web_but_still_ssrf_guarded(pol):
    assert pol.decide("some-random-blog.com", "tok-runtime").allow
    assert not pol.decide("127.0.0.1", "tok-runtime").allow
    assert not pol.decide("10.1.2.3", "tok-runtime").allow
    assert not pol.decide("169.254.169.254", "tok-runtime").allow


def test_deny_always_beats_allowlist(pol):
    assert not pol.decide("foo.onion", "tok-runtime").allow


def test_unresolvable_host_is_denied(pol):
    d = pol.decide("nothing.internal", "tok-runtime")
    assert not d.allow and "ssrf" in d.reason


def test_unknown_token_falls_back_to_default(pol):
    d = pol.decide("api.telegram.org", "not-a-real-token")
    assert d.caller == "default" and not d.allow


def test_injection_spec_surfaced(pol):
    d = pol.decide("api.telegram.org", "tok-hermes")
    assert d.allow and d.inject.get("secret") == "TELEGRAM_BOT_TOKEN"
