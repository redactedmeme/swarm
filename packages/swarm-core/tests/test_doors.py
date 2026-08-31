"""Doors: a named capability being asserted, read back for the status feed.

`apps/status` /api/swarm and `apps/runtime`'s /announce handler are the two
sides of this; neither has coverage of its own, so the round-trip lives here.
"""
import json

import pytest

from swarm_core.swarm_heartbeat import (
    DOOR_KEY_PREFIX,
    build_door_payload,
    door_redis_key,
    parse_door_value,
    read_doors_async,
    write_door_async,
)

from fakeredis import FakeRedis


async def test_write_then_read_round_trips_name_kind_and_open():
    r = FakeRedis()
    await write_door_async(r, "hermes", "moltbook-post", "oracle", True)
    await write_door_async(r, "hermes", "deliberation", "", False)

    doors = await read_doors_async(r, "hermes")

    assert [d["name"] for d in doors] == ["deliberation", "moltbook-post"]
    by_name = {d["name"]: d for d in doors}
    assert by_name["moltbook-post"]["kind"] == "oracle"
    assert by_name["moltbook-post"]["open"] is True
    assert by_name["deliberation"]["open"] is False
    assert by_name["deliberation"]["age_s"] is not None


async def test_read_resolves_every_alias_of_the_agent():
    r = FakeRedis()
    # smolting also answers to "redactedintern"
    await write_door_async(r, "redactedintern", "memory", "store", True)

    doors = await read_doors_async(r, "smolting")

    assert [d["name"] for d in doors] == ["memory"]


async def test_same_door_under_two_aliases_newest_assertion_wins():
    r = FakeRedis()
    stale = build_door_payload("telegram", "surface", True)
    stale["unix"] -= 300
    fresh = build_door_payload("telegram", "surface", False)
    await r.set(door_redis_key("smolting", "telegram"), json.dumps(stale))
    await r.set(door_redis_key("redactedintern", "telegram"), json.dumps(fresh))

    doors = await read_doors_async(r, "smolting")

    assert len(doors) == 1
    assert doors[0]["open"] is False  # the fresher assertion


async def test_unknown_agent_falls_back_to_its_own_id():
    r = FakeRedis()
    await write_door_async(r, "mystery-node", "ping")

    assert [d["name"] for d in await read_doors_async(r, "mystery-node")] == ["ping"]


@pytest.mark.parametrize("raw", [None, "", "not json", "[1, 2]", '"a string"', "{}"])
def test_parse_door_value_rejects_unusable_input(raw):
    out = parse_door_value(raw)
    # a bare {} parses but carries no name, which read_doors_async then drops
    assert out is None or out["name"] == ""


def test_parse_door_value_reports_age_from_unix():
    payload = json.dumps(build_door_payload("x", "", True))
    parsed = parse_door_value(payload, now=json.loads(payload)["unix"] + 42)
    assert parsed["age_s"] == 42


def test_door_key_uses_the_shared_prefix():
    assert door_redis_key("hermes", "oracle") == f"{DOOR_KEY_PREFIX}hermes:oracle"
