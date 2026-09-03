"""SoulStore has to cover what all four soul_manager.py copies did, not just
the hermes/builder variant it was extracted from.

smolting and chan add four things on top: fact ids on a snapshot, a
context-specific prompt addendum, a sanitizer on the way into a prompt, and a
drift summary. Each is opt-in, so the plain agents are unaffected.
"""
from __future__ import annotations

import json

import pytest

from swarm_agent_base import SoulStore

SOUL = (
    "# Soul\n*Last updated: 2020-01-01 00:00 UTC*\n\n"
    "## Evolving Beliefs\n- the mesh rewards patience\n\n"
    "## Community Lore\n_Nothing yet._\n\n"
    "## Notable Events\n_Nothing yet._\n"
)


@pytest.fixture()
def store(tmp_path):
    repo = tmp_path / "SOUL.md"
    repo.write_text(SOUL, encoding="utf-8")
    return SoulStore("smolting", repo_soul=repo, data_dir=tmp_path / "d")


def _manifest(s):
    return json.loads((s._history_dir() / "manifest.json").read_text(encoding="utf-8"))


# -- snapshots ---------------------------------------------------------------

def test_snapshot_records_facts_when_given(store):
    store._snapshot(store.read(), facts_absorbed=[f"f{i}" for i in range(30)])
    entry = _manifest(store)["versions"][-1]
    assert entry["facts_absorbed"] == [f"f{i}" for i in range(20)]  # clamped


def test_snapshot_omits_the_key_when_not_given(store):
    """A plain agent's manifest must not grow a key it never sets."""
    store._snapshot(store.read())
    assert "facts_absorbed" not in _manifest(store)["versions"][-1]


# -- prompt hooks ------------------------------------------------------------

def test_context_provider_appends_its_lines(tmp_path):
    repo = tmp_path / "SOUL.md"
    repo.write_text(SOUL, encoding="utf-8")
    s = SoulStore(
        "smolting", repo_soul=repo, data_dir=tmp_path / "d",
        context_provider=lambda ctx: [f"- resonant fact for {ctx}"],
    )
    assert "resonant fact for existential" in s.for_prompt(context="existential")
    assert "resonance" not in s.for_prompt()  # not asked for, not injected


def test_context_provider_failure_does_not_break_the_prompt(tmp_path):
    def _boom(ctx):
        raise RuntimeError("memory backend down")

    repo = tmp_path / "SOUL.md"
    repo.write_text(SOUL, encoding="utf-8")
    s = SoulStore("smolting", repo_soul=repo, data_dir=tmp_path / "d", context_provider=_boom)
    block = s.for_prompt(context="research")
    assert "the mesh rewards patience" in block  # the soul itself still lands


def test_sanitize_hook_is_applied(tmp_path):
    repo = tmp_path / "SOUL.md"
    repo.write_text(SOUL, encoding="utf-8")
    s = SoulStore("chan", repo_soul=repo, data_dir=tmp_path / "d",
                  sanitize=lambda t: t.replace("patience", "REDACTED"))
    assert "REDACTED" in s.for_prompt()
    assert "patience" not in s.for_prompt()


def test_no_sanitizer_is_identity(store):
    assert "the mesh rewards patience" in store.for_prompt()


# -- notable events ----------------------------------------------------------

def test_record_notable_event_appends_and_stamps(store):
    assert store.record_notable_event("degen signalled an APR spike")
    txt = store.read()
    assert "degen signalled an APR spike" in txt
    assert "_Nothing yet._" not in txt.split("## Notable Events")[1]
    assert "2020-01-01" not in txt  # the stamp moved


def test_record_notable_event_on_empty_soul_is_false(tmp_path):
    s = SoulStore("hermes", repo_soul=tmp_path / "absent.md", data_dir=tmp_path / "d")
    assert s.record_notable_event("nothing to write onto") is False


# -- drift -------------------------------------------------------------------

def test_drift_summary_empty(store):
    assert "No soul history yet" in store.drift_summary()


def test_drift_summary_lists_versions(store):
    for _ in range(4):
        store._snapshot(store.read(), facts_absorbed=["a", "b"])
    out = store.drift_summary(versions=3)
    assert "last 3 version(s)" in out
    assert "v4 @" in out and "v1 @" not in out
    assert "2 facts absorbed" in out
    assert "Current: v4" in out


def test_drift_summary_without_facts_omits_that_clause(store):
    store._snapshot(store.read())
    out = store.drift_summary()
    assert "facts absorbed" not in out
    assert "v1 @" in out
