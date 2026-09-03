"""AgentRuntime loop behaviour, with swarm_core.security.inbox stubbed."""
from __future__ import annotations

import asyncio

import pytest

import swarm_agent_base.runtime as rt_mod
from swarm_agent_base import AgentRuntime


class FakeInbox:
    def __init__(self):
        self.pending: list[dict] = []
        self.claimed: set[str] = set()
        self.completed: dict[str, dict] = {}
        self.heartbeats: list[tuple[str, dict]] = []
        self.written: list[dict] = []
        self.pruned = 0

    def read_pending(self, agent):
        return list(self.pending)

    def claim_message(self, mid):
        if mid in self.claimed:
            return False
        self.claimed.add(mid)
        self.pending = [m for m in self.pending if m.get("id") != mid]
        return True

    def complete_message(self, mid, result=None, error=None):
        self.completed[mid] = {"result": result, "error": error}
        return True

    def heartbeat(self, agent, meta=None):
        self.heartbeats.append((agent, meta or {}))
        return "hb"

    def write_message(self, *, from_agent, to_agent, msg_type, payload, reply_to=None):
        d = {"id": f"w{len(self.written)}", "from": from_agent, "to": to_agent,
             "type": msg_type, "payload": payload, "reply_to": reply_to}
        self.written.append(d)
        return d["id"]

    def prune_old_messages(self, *a, **kw):
        self.pruned += 1
        return 0


@pytest.fixture()
def fake_inbox(monkeypatch):
    fake = FakeInbox()
    monkeypatch.setattr(rt_mod, "_inbox", fake)
    # thought.py imports its own reference to the inbox module
    import swarm_agent_base.thought as th
    monkeypatch.setattr(th, "_inbox", fake)
    return fake


class DummyLLM:
    async def acomplete(self, messages, **kw):
        return "a considered reply. and a question?"

    async def achat(self, system, user, **kw):
        return "seed thought"


def _runtime(fake, **kw):
    return AgentRuntime(name="degen", llm=DummyLLM(), capabilities=["pools"],
                        persona_line="You are Degen.", **kw)


def test_broadcast_observed_but_not_claimed(fake_inbox):
    seen = []
    rt = _runtime(fake_inbox)

    async def _cb(m):
        seen.append(m)

    rt.on_broadcast(_cb)
    fake_inbox.pending = [{"id": "b1", "type": "status_update", "to": "all", "from": "smolting"}]
    asyncio.run(rt._poll_inbox_once())
    # broadcast is observed but never claimed (so other agents still see it)
    assert "b1" not in fake_inbox.claimed
    assert seen and seen[0]["id"] == "b1"


def test_task_request_routed_to_handler(fake_inbox):
    rt = _runtime(fake_inbox)

    @rt.on_task("pools")
    async def _h(payload, msg):
        return {"result": f"pools for {payload.get('arg')}"}

    fake_inbox.pending = [{
        "id": "t1", "type": "task_request", "to": "degen", "from": "hermes",
        "payload": {"verb": "pools", "arg": "SOL"},
    }]
    asyncio.run(rt._poll_inbox_once())
    assert fake_inbox.completed["t1"]["result"] == {"result": "pools for SOL"}


def test_task_request_unknown_verb_errors(fake_inbox):
    rt = _runtime(fake_inbox)
    fake_inbox.pending = [{
        "id": "t2", "type": "task_request", "to": "degen", "from": "hermes",
        "payload": {"verb": "nope"},
    }]
    asyncio.run(rt._poll_inbox_once())
    assert "no handler" in fake_inbox.completed["t2"]["error"]


def test_thought_gets_llm_reply(fake_inbox):
    rt = _runtime(fake_inbox)
    fake_inbox.pending = [{
        "id": "th1", "type": "thought", "to": "degen", "from": "smolting",
        "payload": {"topic": "liquidity", "depth": 1},
    }]
    asyncio.run(rt._poll_inbox_once())
    assert fake_inbox.written and fake_inbox.written[0]["type"] == "thought"
    assert fake_inbox.written[0]["to"] == "smolting"
    assert fake_inbox.completed["th1"]["result"]["replied"] == "w0"


def test_message_for_other_agent_ignored(fake_inbox):
    rt = _runtime(fake_inbox)
    fake_inbox.pending = [{"id": "x1", "type": "task_request", "to": "hermes", "from": "a"}]
    asyncio.run(rt._poll_inbox_once())
    assert "x1" not in fake_inbox.completed and "x1" not in fake_inbox.claimed


def test_add_periodic_runs_and_stops(fake_inbox):
    rt = _runtime(fake_inbox)
    hits = []

    async def _tick():
        hits.append(1)
        if len(hits) >= 3:
            rt.stop()

    rt.add_periodic(_tick, 0.01, first_s=0, name="tick")

    async def _drive():
        await asyncio.wait_for(rt.run(), timeout=2)

    asyncio.run(_drive())
    assert len(hits) >= 3
    # boot heartbeat fired for the agent name
    assert any(a == "degen" for a, _ in fake_inbox.heartbeats)


def test_alias_names_receive_messages_and_heartbeats(fake_inbox):
    rt = _runtime(fake_inbox, alias_names=["redacteddegen"])

    @rt.on_task("ping")
    async def _h(payload, msg):
        return {"pong": True}

    fake_inbox.pending = [{
        "id": "a1", "type": "task_request", "to": "redacteddegen", "from": "hermes",
        "payload": {"verb": "ping"},
    }]
    asyncio.run(rt._poll_inbox_once())
    assert fake_inbox.completed["a1"]["result"] == {"pong": True}
