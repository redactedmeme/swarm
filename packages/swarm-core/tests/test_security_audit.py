"""audit: the chain detects insert / edit / delete."""
from __future__ import annotations

import importlib
import json

import pytest


@pytest.fixture()
def audit(tmp_path, monkeypatch):
    monkeypatch.setenv("SWARM_AUDIT_LOG", str(tmp_path / "a.jsonl"))
    monkeypatch.delenv("REDIS_URL", raising=False)
    from swarm_core.security import audit as _a

    importlib.reload(_a)
    return _a


def test_records_chain_and_verifies(audit):
    for i in range(5):
        audit.record("tool.exec", actor="hermes", decision="allow", detail={"i": i})
    ok, n, msg = audit.verify_chain()
    assert ok and n == 5, msg


def test_detects_edit(audit):
    audit.record("a", actor="hermes")
    audit.record("b", actor="hermes")
    audit.record("c", actor="hermes")
    path = audit._audit_path()
    lines = path.read_text().splitlines()
    rec = json.loads(lines[1])
    rec["detail"] = {"tampered": True}
    lines[1] = json.dumps(rec, sort_keys=True, separators=(",", ":"))
    path.write_text("\n".join(lines) + "\n")

    ok, n, msg = audit.verify_chain()
    assert not ok
    assert n == 2


def test_detects_delete(audit):
    audit.record("a", actor="hermes")
    audit.record("b", actor="hermes")
    audit.record("c", actor="hermes")
    path = audit._audit_path()
    lines = path.read_text().splitlines()
    path.write_text(lines[0] + "\n" + lines[2] + "\n")

    ok, n, _ = audit.verify_chain()
    assert not ok


def test_detail_is_stored_verbatim(audit):
    rec = audit.record("egress.block", actor="smolting", decision="block",
                       detail={"host": "evil.com", "rule": "not-allowlisted"})
    assert rec["detail"]["host"] == "evil.com"
    assert rec["prev_hash"] == audit.GENESIS
