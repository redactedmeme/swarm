"""inbox: completing a message that carries ``payload.reply_key`` mirrors the
result onto that Redis key — the chan->hermes delegation contract
(``apps/chan/hermes_dispatch.py::get_reply`` polls the key directly)."""
from __future__ import annotations

import importlib
import json

import pytest


class _FakeRedis:
    """Just enough of redis-py for swarm_core.security.inbox."""

    def __init__(self):
        self.kv: dict[str, str] = {}
        self.z: dict[str, dict[str, float]] = {}

    # strings
    def set(self, k, v, ex=None):
        self.kv[k] = v
        return True

    def get(self, k):
        return self.kv.get(k)

    # sorted sets
    def zadd(self, k, mapping):
        self.z.setdefault(k, {}).update(mapping)
        return len(mapping)

    def zrange(self, k, start, stop):
        items = sorted(self.z.get(k, {}).items(), key=lambda kv: kv[1])
        return [m for m, _ in items][start: (None if stop == -1 else stop + 1)]

    def zrevrange(self, k, start, stop):
        return list(reversed(self.zrange(k, 0, -1)))[start: stop + 1]

    def zrem(self, k, *members):
        d = self.z.get(k, {})
        for m in members:
            d.pop(m, None)
        return len(members)

    def ping(self):
        return True

    # pipeline: queue ops, replay on execute
    def pipeline(self):
        return _FakePipe(self)


class _FakePipe:
    def __init__(self, r):
        self._r = r
        self._ops = []

    def __getattr__(self, name):
        def queue(*a, **kw):
            self._ops.append((name, a, kw))
            return self
        return queue

    def execute(self):
        for name, a, kw in self._ops:
            getattr(self._r, name)(*a, **kw)
        self._ops.clear()


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


def test_reply_key_is_written_on_success(inbox):
    _i, fake = inbox
    mid = _i.write_message(
        "redacted-chan", "hermes", "task_request",
        {"instruction": "fetch", "reply_key": "swarm:reply:abc123"},
    )
    _i.complete_message(mid, result={"summary": "done: 42"})
    raw = fake.get("swarm:reply:abc123")
    assert raw and json.loads(raw)["content"] == "done: 42"


def test_reply_key_is_written_on_error(inbox):
    _i, fake = inbox
    mid = _i.write_message(
        "redacted-chan", "hermes", "task_request",
        {"instruction": "boom", "reply_key": "swarm:reply:err1"},
    )
    _i.complete_message(mid, error="upstream 500")
    body = json.loads(fake.get("swarm:reply:err1"))
    assert body["content"] == "upstream 500" and body["error"] is True


def test_no_reply_key_is_a_noop(inbox):
    _i, fake = inbox
    mid = _i.write_message("redacted-chan", "hermes", "task_request", {"instruction": "x"})
    _i.complete_message(mid, result={"content": "ok"})
    assert not any(k.startswith("swarm:reply:") for k in fake.kv)
