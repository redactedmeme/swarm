"""inbox: a valid message round-trips; forged / unsigned / misrouted ones are
dropped (strict) and audited."""
from __future__ import annotations

import importlib

import pytest


@pytest.fixture()
def inbox(tmp_path, monkeypatch):
    monkeypatch.delenv("REDIS_URL", raising=False)          # force file store
    monkeypatch.setenv("MEMORY_PATH", str(tmp_path / "memory.md"))
    monkeypatch.setenv("SWARM_INBOX_HMAC_KEY", "unit-test-shared-key")
    monkeypatch.setenv("SWARM_INBOX_ENFORCE", "strict")
    monkeypatch.setenv("SWARM_AUDIT_LOG", str(tmp_path / "audit.jsonl"))
    from swarm_core.security import inbox as _i

    importlib.reload(_i)
    return _i


def test_valid_message_round_trips(inbox):
    mid = inbox.write_message("redactedintern", "redactedbuilder", "deploy_request", {"svc": "x"})
    pending = inbox.read_pending("redactedbuilder")
    assert [m["id"] for m in pending] == [mid]
    assert pending[0]["payload"] == {"svc": "x"}


def test_unsigned_message_is_dropped(inbox):
    # write straight to the file store, bypassing write_message / signing
    inbox._file_write_message({
        "id": "msg_forged01", "ts": inbox._now_iso(), "from": "redactedintern",
        "to": "redactedbuilder", "type": "deploy_request", "payload": {"svc": "evil"},
        "status": inbox.STATUS_PENDING,
    })
    assert inbox.read_pending("redactedbuilder") == []


def test_tampered_payload_is_dropped(inbox):
    inbox.write_message("redactedintern", "redactedbuilder", "deploy_request", {"svc": "good"})
    # mutate the stored doc, keeping the now-stale signature
    d = inbox._inbox_dir()
    f = next(d.glob("*.json"))
    import json

    doc = json.loads(f.read_text())
    doc["payload"] = {"svc": "pwned"}
    f.write_text(json.dumps(doc))
    assert inbox.read_pending("redactedbuilder") == []


def test_wrong_sender_key_is_dropped(inbox, monkeypatch):
    mid = inbox.write_message("redactedintern", "redactedbuilder", "deploy_request", {"svc": "x"})
    assert mid
    # attacker who doesn't hold the shared key signs with their own
    monkeypatch.setenv("SWARM_INBOX_KEY_REDACTEDINTERN", "attacker-key")
    importlib.reload(inbox)
    monkeypatch.setenv("SWARM_INBOX_HMAC_KEY", "unit-test-shared-key")
    assert inbox.read_pending("redactedbuilder") == []


def test_misrouted_type_is_dropped(inbox):
    # deploy_result is only allowed builder -> intern, not intern -> builder
    inbox.write_message("redactedintern", "redactedbuilder", "deploy_result", {})
    assert inbox.read_pending("redactedbuilder") == []


def test_unknown_agent_rejected_at_write(inbox):
    with pytest.raises(ValueError):
        inbox.write_message("mallory", "redactedbuilder", "task_request", {})


def test_warn_mode_passes_but_audits(inbox, monkeypatch):
    monkeypatch.setenv("SWARM_INBOX_ENFORCE", "warn")
    importlib.reload(inbox)
    inbox._file_write_message({
        "id": "msg_warn01", "ts": inbox._now_iso(), "from": "redactedintern",
        "to": "redactedbuilder", "type": "deploy_request", "payload": {},
        "status": inbox.STATUS_PENDING,
    })
    assert len(inbox.read_pending("redactedbuilder")) == 1  # passed through
    from swarm_core.security import audit

    events = [r["event"] for r in audit.read_all()]
    assert "inbox.reject" in events


def test_alias_senders_round_trip(inbox):
    """Every name a live runtime heartbeats under must validate as a sender.

    Regression for the deploy-blocking bug shape: `builder` writes under
    "builder" while the roster only knew "redactedbuilder", so the first
    heartbeat after a rebuild raised ValueError instead of sending.
    """
    for name in ("builder", "redactedbuilder", "degen", "redacteddegen",
                 "govimprover", "redactedgovimprover", "redacted-proxy"):
        mid = inbox.write_message(name, "all", "heartbeat", {"ok": True})
        assert mid, name


def test_warn_mode_reject_is_not_logged_at_warning(inbox, monkeypatch, caplog):
    """In warn mode the message is delivered, so a per-message WARNING is noise.

    The audit record still has to be written — staged enforcement must not
    thin out the audit trail.
    """
    import logging

    monkeypatch.setenv("SWARM_INBOX_ENFORCE", "warn")
    importlib.reload(inbox)
    inbox._file_write_message({
        "id": "msg_lvl01", "ts": inbox._now_iso(), "from": "redactedintern",
        "to": "redactedbuilder", "type": "deploy_request", "payload": {},
        "status": inbox.STATUS_PENDING,
    })
    with caplog.at_level(logging.INFO, logger="swarm_core.security.inbox"):
        assert len(inbox.read_pending("redactedbuilder")) == 1

    rejects = [r for r in caplog.records if "REJECT" in r.getMessage()]
    assert rejects, "the rejection should still be logged"
    assert all(r.levelno == logging.INFO for r in rejects)

    from swarm_core.security import audit

    assert "inbox.reject" in [r["event"] for r in audit.read_all()]


def test_missing_key_warns_once_per_sender(tmp_path, monkeypatch, caplog):
    """The unsigned-message log describes a config state, not a per-message
    failure; at one ERROR per heartbeat it drowns the real errors."""
    import logging

    monkeypatch.delenv("REDIS_URL", raising=False)
    monkeypatch.delenv("SWARM_INBOX_HMAC_KEY", raising=False)
    monkeypatch.setenv("MEMORY_PATH", str(tmp_path / "memory.md"))
    monkeypatch.setenv("SWARM_INBOX_ENFORCE", "warn")
    monkeypatch.setenv("SWARM_AUDIT_LOG", str(tmp_path / "audit.jsonl"))
    from swarm_core.security import inbox as _i

    importlib.reload(_i)

    with caplog.at_level(logging.DEBUG, logger="swarm_core.security.inbox"):
        for _ in range(5):
            _i.write_message("degen", "all", "heartbeat", {})
        _i.write_message("hermes", "all", "heartbeat", {})

    nokey = [r for r in caplog.records if "no signing key" in r.getMessage()]
    assert len(nokey) == 2, "once per sender, not once per message"
    assert {r.levelno for r in nokey} == {logging.WARNING}
