"""inbox.reassign_message — ownership handoff with a signed, capped chain."""
from __future__ import annotations

import importlib

import pytest

from test_inbox_reply_key import _FakeRedis  # reuse the fake


@pytest.fixture()
def inbox(monkeypatch):
    monkeypatch.setenv("SWARM_INBOX_HMAC_KEY", "unit-test-shared-key")
    monkeypatch.setenv("SWARM_INBOX_ENFORCE", "strict")
    monkeypatch.setenv("REDIS_URL", "redis://fake")
    from swarm_core.security import inbox as _i

    importlib.reload(_i)
    fake = _FakeRedis()
    monkeypatch.setattr(_i, "_get_redis", lambda: fake)
    return _i, fake


def _mk(inbox):
    _i, _ = inbox
    mid = _i.write_message("hermes", "smolting", "task_request", {"do": "thing"})
    assert _i.claim_message(mid)
    return _i, mid


def test_reassign_moves_ownership_and_records_chain(inbox):
    _i, mid = _mk(inbox)
    assert _i.reassign_message(mid, "degen", reason="smolting busy")

    doc = _i.get_message(mid)
    assert doc["to"] == "degen"
    assert doc["status"] == _i.STATUS_PENDING
    assert doc["claimed_at"] is None
    assert len(doc["handoff_chain"]) == 1
    assert doc["handoff_chain"][0]["from"] == "smolting"
    assert doc["handoff_chain"][0]["to"] == "degen"
    # signature still verifies after the re-sign
    assert _i.verify_doc(doc)
    # and it now shows up in the new owner's pending queue
    assert any(m["id"] == mid for m in _i.read_pending("degen"))
    assert not any(m["id"] == mid for m in _i.read_pending("smolting"))


def test_reassign_refused_when_not_processing(inbox):
    _i, _ = inbox
    mid = _i.write_message("hermes", "smolting", "task_request", {"x": 1})
    # still pending, never claimed
    assert _i.reassign_message(mid, "degen") is False


def test_handoff_chain_depth_is_capped(inbox):
    _i, mid = _mk(inbox)
    targets = ["degen", "refinery", "builder", "runtime", "arb-keeper", "hermes"]
    results = []
    for t in targets:
        results.append(_i.reassign_message(mid, t))
        _i.claim_message(mid)  # next hop needs it processing again
    assert results[:5] == [True, True, True, True, True]
    assert results[5] is False  # 6th hop blocked by _MAX_HANDOFF_DEPTH
    assert len(_i.get_message(mid)["handoff_chain"]) == 5


def test_reassign_rejects_disallowed_route(inbox):
    _i, _ = inbox
    mid = _i.write_message("redactedintern", "redactedbuilder", "deploy_request", {})
    assert _i.claim_message(mid)
    # deploy_request is only routable to redactedbuilder
    assert _i.reassign_message(mid, "degen") is False
