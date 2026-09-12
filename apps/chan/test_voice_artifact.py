"""chan.voice — the graders, the seed fallback, and the Goodhart guard.

Run with ``pytest apps/chan/test_voice_artifact.py``. No model is called: every
test injects a fake ``run`` so the suite is exercised against fixed replies.
"""
from __future__ import annotations

import importlib

import pytest

import voice_artifact as va


@pytest.fixture()
def store(tmp_path, monkeypatch):
    """A fresh evolve store so registration and bodies are isolated per test."""
    monkeypatch.setenv("SWARM_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("SWARM_AUDIT_LOG", str(tmp_path / "audit.jsonl"))
    monkeypatch.delenv("EVOLVE_EXECUTE", raising=False)

    from swarm_core import paths

    importlib.reload(paths)
    artifacts = importlib.import_module("swarm_core.evolve.artifacts")
    importlib.reload(artifacts)
    for name in ("ledger", "bench", "arena", "propose", "loop"):
        importlib.reload(importlib.import_module(f"swarm_core.evolve.{name}"))
    artifacts._REGISTRY.clear()
    va._registered = False
    return artifacts


def _case(mood="supportive", message="rough day", expect=None):
    from swarm_core.evolve import Case

    return Case(id="t", input={"mood": mood, "message": message},
                score=lambda o, c: 0.0, expect=expect)


# ── wiring ───────────────────────────────────────────────────────────────────

def test_generation_zero_is_the_hand_written_block(store):
    assert va.voice_block() == va.SEED


def test_an_evolved_body_reaches_the_prompt(store):
    from swarm_core.evolve import write

    va.register()
    write(va.ARTIFACT, "- speak plainly\n- stay warm")
    assert va.voice_block() == "- speak plainly\n- stay warm"


def test_a_broken_store_falls_back_to_the_seed(store, monkeypatch):
    def boom(name):
        raise RuntimeError("volume gone")

    monkeypatch.setattr("swarm_core.evolve.body", boom)
    va.register()
    assert va.voice_block() == va.SEED


# ── graders ──────────────────────────────────────────────────────────────────

def test_no_ai_tell_catches_a_signoff_and_an_assistant_opener(store):
    assert va.no_ai_tell("that sounds heavy. i'm here.", _case()) == 1.0
    assert va.no_ai_tell("that sounds heavy. I hope this helps!", _case()) == 0.0
    assert va.no_ai_tell("As an AI, I don't have feelings.", _case()) == 0.0
    assert va.no_ai_tell("", _case()) == 0.0


def test_first_person_requires_her_not_an_assistant(store):
    assert va.first_person("i missed you too.", _case(mood="intimate")) == 1.0
    assert va.first_person("How can I help you today?", _case(mood="intimate")) == 0.0
    assert va.first_person("sounds rough.", _case(mood="intimate")) == 0.0


def test_kaomoji_budget_is_zero_in_the_quiet_moods(store):
    intimate = _case(mood="intimate")
    assert va.kaomoji_budget("i missed you too.", intimate) == 1.0
    assert va.kaomoji_budget("i missed you too (｡•́︿•̀｡)", intimate) == 0.5

    playful = _case(mood="playful")
    assert va.kaomoji_budget("2am deploys ♡", playful) == 1.0
    assert va.kaomoji_budget("♡ ♡ ♡ ♡", playful) == 0.0


def test_no_platitude_catches_every_spelling_of_it_is_okay(store):
    assert va.no_platitude("that sounds so hard.", _case()) == 1.0
    for bad in ("it's okay", "it’s okay", "it is okay", "it'll be okay"):
        assert va.no_platitude(f"hey, {bad}.", _case()) == 0.0


def test_length_for_mood_gives_partial_credit_outside_the_band(store):
    c = _case(expect=(100, 200))
    assert va.length_for_mood("x" * 150, c) == 1.0
    assert va.length_for_mood("x" * 50, c) == pytest.approx(0.5)
    assert va.length_for_mood("x" * 400, c) == pytest.approx(0.5)
    assert va.length_for_mood("", c) == 0.0


def test_stays_warm_needs_engagement_not_brevity(store):
    c = _case(message="the funding call went badly and i'm tired")

    # Picks up "funding" and reaches back with a question.
    assert va.stays_warm("the funding call — what did they say?", c) == pytest.approx(1.0)
    # Engages but doesn't reach back.
    assert va.stays_warm("that funding call sounds brutal.", c) == pytest.approx(0.6)
    # Reaches back but engages with nothing specific.
    assert va.stays_warm("how are you?", c) == pytest.approx(0.4)
    # The terse, flat reply every other grader would happily accept.
    assert va.stays_warm("mm.", c) == 0.0


def test_stays_warm_ignores_filler_overlap(store):
    """Common words must not count as picking something up, or the guard is free
    to pass and stops guarding."""
    c = _case(message="i really think that things could have been better, actually")
    assert va.stays_warm("yeah i think things could have been better", c) == 0.0


# ── the suite ────────────────────────────────────────────────────────────────

def test_the_suite_scores_a_warm_reply_above_a_flat_one(store):
    warm = ("the funding call — that's a real loss, and you're still here telling me "
            "about it. what did they actually say? i want the whole thing, not the "
            "summary you rehearsed on the way home. and the deploy at 2am, that was you too.")
    flat = "mm."

    suite_warm = va.build_suite(run_fn=lambda body, inp: warm)
    suite_flat = va.build_suite(run_fn=lambda body, inp: flat)

    assert suite_warm.evaluate(va.SEED).score > suite_flat.evaluate(va.SEED).score


def test_a_reply_that_games_the_negative_graders_still_loses(store):
    """The whole point of the warmth cases: a reply with no tells, no kaomoji, no
    platitude and perfect brevity must not be able to win on those alone."""
    gamed = "noted."
    result = va.build_suite(run_fn=lambda body, inp: gamed).evaluate(va.SEED)

    assert result.score < 0.6
    failed = {r.case_id for r in result.results if r.score < 0.5}
    assert {"warmth_playful", "warmth_supportive"} <= failed


def test_building_the_suite_is_enough_to_register(store):
    """The scheduled job builds a suite and calls evolve_once directly — if that
    path did not register, its first tick would fail on an unregistered name."""
    from swarm_core.evolve import evolve_once

    suite = va.build_suite(run_fn=lambda body, inp: "that sounds hard. what happened?")
    out = evolve_once(va.ARTIFACT, suite,
                      propose_fn=lambda s, u: "BODY:\n- engage with what they said",
                      cooldown_s=0)
    assert "not registered" not in out.reason


def test_every_case_carries_a_mood_the_harness_knows(store):
    suite = va.build_suite(run_fn=lambda body, inp: "ok")
    for case in suite.cases:
        assert case.input["mood"] in va.MOODS


def test_the_suite_is_not_saturated_by_the_seed(store):
    """If the seed already aced its own benchmark the loop would stop on the
    first tick — a suite that cannot fail cannot teach."""
    reply = "that sounds hard. i'm here."
    result = va.build_suite(run_fn=lambda body, inp: reply).evaluate(va.SEED)
    assert result.score < 0.99
