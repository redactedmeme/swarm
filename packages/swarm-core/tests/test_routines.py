"""swarm_core.routines — trace -> skill doc + routine spec + replay."""
from __future__ import annotations

import json

import pytest

import importlib

from swarm_core import routines

promote_mod = importlib.import_module("swarm_core.routines.promote")


@pytest.fixture(autouse=True)
def _data(tmp_path, monkeypatch):
    monkeypatch.setenv("SWARM_DATA_DIR", str(tmp_path))
    return tmp_path


_TRACE = [
    {"action": "workspace.browser_goto", "detail": {"url": "https://example.com", "session": "default"}},
    {"action": "workspace.shell", "detail": {"cmd": "grep -c foo out.txt", "cwd": ""}},
    {"action": "workspace.browser_type", "detail": {"selector": "#q", "chars": 5}},
    {"action": "workspace.fs_write", "detail": {"path": "r.txt", "bytes": 3}},
]


def test_distill_skill_doc_has_standard_sections():
    doc = routines.distill_skill_doc("My Routine", "does a thing", _TRACE)
    for section in ("## Description", "## When to Use", "## Steps", "## Example"):
        assert section in doc
    assert "grep -c foo out.txt" in doc
    assert "value not recorded" in doc  # the browser_type step


def test_promote_writes_skill_and_spec(_data):
    out = routines.promote(_TRACE, name="My Routine", interval_s=900, description="d")
    assert (_data / "skills" / "my_routine.md").is_file()
    spec = json.loads((_data / "routines" / "my_routine.json").read_text())
    assert spec["interval_s"] == 900
    assert spec["agent"] == "hermes"
    # goto + shell are replayable; type + fs_write are not (no recorded value)
    assert out["replayable_steps"] == 2
    assert [s["replayable"] for s in spec["steps"]] == [True, True, False, False]


def test_promote_rejects_short_interval():
    with pytest.raises(ValueError):
        routines.promote(_TRACE, name="x", interval_s=30)


def test_overrides_make_type_and_write_replayable(_data):
    out = routines.promote(_TRACE, name="ovr", interval_s=120,
                           overrides={3: {"text": "hello"}, 4: {"content": "abc"}})
    assert out["replayable_steps"] == 4


def test_load_routines_returns_scheduler_tasks(_data):
    routines.promote(_TRACE, name="R1", interval_s=600)
    tasks = routines.load_routines()
    assert len(tasks) == 1
    t = tasks[0]
    assert t.id == "routine_r1"
    assert t.interval_s == 600
    assert "routine" in t.tags


def test_run_routine_replays_in_order_and_stops_on_failure(monkeypatch):
    calls = []

    def fake_call(path, body, *, agent):
        calls.append((path, body))
        # fail the shell step
        return {"status": "error" if path == "/shell" else "ok"}

    monkeypatch.setattr(promote_mod, "_ws_call", fake_call)
    spec = routines.promote(_TRACE, name="rr", interval_s=60,
                            overrides={3: {"text": "x"}, 4: {"content": "y"}})
    spec_obj = json.loads(open(spec["spec_path"]).read())
    res = promote_mod.run_routine(spec_obj)
    assert res["ok"] is False
    assert [c[0] for c in calls] == ["/browser/goto", "/shell"]  # stopped at the failure
