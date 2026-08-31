"""authz: static grants, the approval gate, and fail-closed admin."""
from __future__ import annotations

import importlib

import pytest


@pytest.fixture()
def authz(monkeypatch):
    monkeypatch.delenv("REDIS_URL", raising=False)
    from swarm_core.security import authz as _a

    importlib.reload(_a)
    return _a


def test_static_grant_allow_deny(authz):
    authz.require("smolting", "web.fetch")          # granted -> no raise
    with pytest.raises(authz.Denied):
        authz.require("smolting", "infra.deploy")   # not granted


def test_unknown_actor_denied(authz):
    with pytest.raises(authz.Denied):
        authz.require("totally-not-an-agent", "llm.call")


def test_code_exec_is_not_approval_gated(authz):
    # the sandbox (apps/exec-runner) is the control; a static grant is enough
    authz.require("hermes", "code.exec")


def test_high_risk_needs_approval_even_with_grant(authz):
    # hermes HAS the infra.deploy grant, but it's in requires_approval
    with pytest.raises(authz.Denied) as ei:
        authz.require("hermes", "infra.deploy")
    assert "approval required" in str(ei.value)


def test_approval_round_trip(authz):
    tok = authz.request_approval("hermes", "infra.deploy", detail={"reason": "test"})
    with pytest.raises(authz.Denied):
        authz.require("hermes", "infra.deploy", approval=tok)  # not granted yet
    assert authz.grant_approval(tok, approver="operator")
    authz.require("hermes", "infra.deploy", approval=tok)      # now passes


def test_approval_is_bound_to_actor_and_cap(authz):
    tok = authz.request_approval("hermes", "infra.deploy")
    authz.grant_approval(tok)
    with pytest.raises(authz.Denied):
        authz.require("redactedintern", "infra.deploy", approval=tok)  # wrong actor
    with pytest.raises(authz.Denied):
        authz.require("hermes", "secret.read", approval=tok)           # wrong cap


def test_is_admin_fail_closed(authz, monkeypatch):
    monkeypatch.delenv("ADMIN_IDS", raising=False)
    assert authz.is_admin("12345") is False          # nobody configured -> deny
    monkeypatch.setenv("ADMIN_IDS", "111, 222")
    assert authz.is_admin("222") is True
    assert authz.is_admin("333") is False
