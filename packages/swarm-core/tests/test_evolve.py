"""swarm_core.evolve — artifact store, benchmark, arena gates, ledger recursion."""
from __future__ import annotations

import importlib
import json

import pytest


@pytest.fixture()
def evolve(tmp_path, monkeypatch):
    """A fresh evolve module rooted at a temp data dir with an empty registry."""
    monkeypatch.setenv("SWARM_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("SWARM_AUDIT_LOG", str(tmp_path / "audit.jsonl"))
    monkeypatch.delenv("EVOLVE_EXECUTE", raising=False)

    from swarm_core import paths

    importlib.reload(paths)
    import swarm_core.evolve.artifacts as artifacts

    importlib.reload(artifacts)
    # `swarm_core.evolve` re-exports the `propose` *function* over the submodule
    # of the same name, so reach the modules through sys.modules, not attributes.
    ledger = importlib.import_module("swarm_core.evolve.ledger")
    bench = importlib.import_module("swarm_core.evolve.bench")
    arena = importlib.import_module("swarm_core.evolve.arena")
    propose = importlib.import_module("swarm_core.evolve.propose")
    loop = importlib.import_module("swarm_core.evolve.loop")

    for m in (ledger, bench, arena, propose, loop):
        importlib.reload(m)
    artifacts._REGISTRY.clear()

    class NS:
        pass

    ns = NS()
    ns.artifacts, ns.ledger, ns.bench = artifacts, ledger, bench
    ns.arena, ns.propose, ns.loop = arena, propose, loop
    return ns


def _register(evolve, seed="be brief", owner="redacted-chan"):
    return evolve.artifacts.register(evolve.artifacts.Artifact(
        name="test.prompt", owner=owner, kind="system_prompt",
        seed=seed, description="a test prompt"))


def _suite(evolve, wanted="better"):
    """Scores a body by how many of the wanted tokens it contains."""
    def run(body, inp):
        return f"{body}|{inp}"

    def score(output, case):
        return 1.0 if case.expect in output else 0.0

    s = evolve.bench.Suite(name="tokens", run=run)
    s.add(evolve.bench.Case(id="has_token", input="x", score=score, expect=wanted))
    s.add(evolve.bench.Case(id="always", input="y", score=lambda o, c: 1.0))
    return s


# ── artifacts ────────────────────────────────────────────────────────────────

def test_seed_is_readable_and_generation_starts_at_zero(evolve):
    _register(evolve, seed="hello")
    assert evolve.artifacts.body("test.prompt") == "hello"
    assert evolve.artifacts.generation("test.prompt") == 0


def test_unregistered_artifact_is_refused(evolve):
    with pytest.raises(evolve.artifacts.ArtifactError):
        evolve.artifacts.body("nope.not.registered")


def test_write_bumps_generation_and_keeps_one_previous(evolve):
    _register(evolve, seed="v0")
    evolve.artifacts.write("test.prompt", "v1")
    assert evolve.artifacts.body("test.prompt") == "v1"
    assert evolve.artifacts.generation("test.prompt") == 1

    evolve.artifacts.rollback("test.prompt")
    assert evolve.artifacts.body("test.prompt") == "v0"

    # Only one step is retained, so a second rollback is an error, not a no-op.
    with pytest.raises(evolve.artifacts.ArtifactError):
        evolve.artifacts.rollback("test.prompt")


def test_write_rejects_empty_identical_and_oversized(evolve, monkeypatch):
    _register(evolve, seed="v0")
    with pytest.raises(evolve.artifacts.ArtifactError):
        evolve.artifacts.write("test.prompt", "   ")
    with pytest.raises(evolve.artifacts.ArtifactError):
        evolve.artifacts.write("test.prompt", "v0")

    monkeypatch.setattr(evolve.artifacts, "MAX_BODY_BYTES", 8)
    with pytest.raises(evolve.artifacts.ArtifactError):
        evolve.artifacts.write("test.prompt", "x" * 64)


def test_re_registering_never_clobbers_an_evolved_body(evolve):
    _register(evolve, seed="v0")
    evolve.artifacts.write("test.prompt", "evolved")
    _register(evolve, seed="v0")
    assert evolve.artifacts.body("test.prompt") == "evolved"


# ── bench ────────────────────────────────────────────────────────────────────

def test_suite_scores_are_weighted_and_bounded(evolve):
    s = evolve.bench.Suite(name="w", run=lambda b, i: b)
    s.add(evolve.bench.Case(id="a", input=None, score=lambda o, c: 1.0, weight=3.0))
    s.add(evolve.bench.Case(id="b", input=None, score=lambda o, c: 0.0, weight=1.0))
    assert s.evaluate("body").score == pytest.approx(0.75)

    # Scores outside [0, 1] are clamped rather than trusted.
    s2 = evolve.bench.Suite(name="c", run=lambda b, i: b)
    s2.add(evolve.bench.Case(id="hi", input=None, score=lambda o, c: 99.0))
    assert s2.evaluate("body").score == 1.0


def test_a_raising_case_scores_zero_without_voiding_the_suite(evolve):
    def boom(output, case):
        raise RuntimeError("grader exploded")

    s = evolve.bench.Suite(name="e", run=lambda b, i: b)
    s.add(evolve.bench.Case(id="bad", input=None, score=boom))
    s.add(evolve.bench.Case(id="good", input=None, score=lambda o, c: 1.0))

    res = s.evaluate("body")
    assert res.errors == 1
    assert res.score == pytest.approx(0.5)
    assert res.failures[0].case_id == "bad"


# ── arena ────────────────────────────────────────────────────────────────────

def test_a_winning_candidate_is_held_while_execute_is_off(evolve):
    _register(evolve, seed="plain")
    suite = _suite(evolve, wanted="better")

    v = evolve.arena.compete("test.prompt", "much better", suite)
    assert v.promoted is False
    assert "EVOLVE_EXECUTE is off" in v.reason
    assert evolve.artifacts.body("test.prompt") == "plain"
    # The attempt is still recorded — a held win is exactly what the ledger is for.
    assert evolve.ledger.stats("test.prompt")["attempts"] == 1


def test_a_winning_candidate_is_promoted_when_execute_is_on(evolve, monkeypatch):
    monkeypatch.setenv("EVOLVE_EXECUTE", "true")
    _register(evolve, seed="plain")

    v = evolve.arena.compete("test.prompt", "much better", _suite(evolve))
    assert v.promoted is True
    assert evolve.artifacts.body("test.prompt") == "much better"
    assert v.delta > 0


def test_a_candidate_below_the_gain_threshold_is_rejected(evolve, monkeypatch):
    monkeypatch.setenv("EVOLVE_EXECUTE", "true")
    _register(evolve, seed="better")           # champion already passes both cases

    v = evolve.arena.compete("test.prompt", "better still", _suite(evolve))
    assert v.promoted is False
    assert "below threshold" in v.reason
    assert evolve.artifacts.body("test.prompt") == "better"


def test_a_new_error_disqualifies_even_a_higher_score(evolve, monkeypatch):
    monkeypatch.setenv("EVOLVE_EXECUTE", "true")
    _register(evolve, seed="plain")

    def score(output, case):
        if "poison" in output:
            raise RuntimeError("challenger broke this case")
        return 1.0 if "better" in output else 0.0

    s = evolve.bench.Suite(name="reg", run=lambda b, i: b)
    s.add(evolve.bench.Case(id="fragile", input=None, score=score))
    s.add(evolve.bench.Case(id="easy", input=None, score=lambda o, c: 1.0))

    v = evolve.arena.compete("test.prompt", "better poison", s)
    assert v.promoted is False
    assert "new errors on fragile" in v.reason
    assert evolve.artifacts.body("test.prompt") == "plain"


def test_promotion_requires_the_evolve_promote_grant(evolve, monkeypatch):
    monkeypatch.setenv("EVOLVE_EXECUTE", "true")
    _register(evolve, seed="plain", owner="refinery")   # no evolve.promote grant

    v = evolve.arena.compete("test.prompt", "much better", _suite(evolve))
    assert v.promoted is False
    assert "denied" in v.reason
    assert evolve.artifacts.body("test.prompt") == "plain"


def test_a_supplied_champion_result_is_not_re_measured(evolve):
    """evolve_once already scored the live body to build the prompt; re-scoring it
    in the arena would make every generation a third more expensive."""
    calls = []

    def run(body, inp):
        calls.append(body)
        return body

    s = evolve.bench.Suite(name="count", run=run)
    s.add(evolve.bench.Case(id="only", input=None,
                            score=lambda o, c: 1.0 if "better" in o else 0.0))

    _register(evolve, seed="plain")
    baseline = s.evaluate_repeated("plain", 1)
    calls.clear()

    evolve.arena.compete("test.prompt", "much better", s, rounds=1,
                         champion_result=baseline)
    assert calls == ["much better"]      # the champion was never run again


# ── ledger (the recursive part) ──────────────────────────────────────────────

def test_lessons_feed_rejections_back_to_the_next_proposer(evolve):
    _register(evolve, seed="plain")
    suite = _suite(evolve)

    evolve.arena.compete("test.prompt", "worse", suite, diff_summary="removed the token")
    lessons = evolve.ledger.lessons("test.prompt")
    assert "REJECTED" in lessons
    assert "removed the token" in lessons


def test_stats_count_attempts_and_promotions(evolve, monkeypatch):
    monkeypatch.setenv("EVOLVE_EXECUTE", "true")
    _register(evolve, seed="plain")
    suite = _suite(evolve)

    evolve.arena.compete("test.prompt", "worse", suite)
    evolve.arena.compete("test.prompt", "much better", suite)

    st = evolve.ledger.stats("test.prompt")
    assert st["attempts"] == 2
    assert st["promoted"] == 1


def test_the_generation_lands_on_the_audit_chain(evolve, tmp_path):
    _register(evolve, seed="plain")
    evolve.arena.compete("test.prompt", "much better", _suite(evolve))

    lines = (tmp_path / "audit.jsonl").read_text("utf-8").splitlines()
    events = [json.loads(x) for x in lines if x.strip()]
    assert any(e.get("event") == "evolve.generation" for e in events)


# ── propose ──────────────────────────────────────────────────────────────────

def test_parse_splits_rationale_from_body_and_strips_fences(evolve):
    body, rationale = evolve.propose.parse(
        "RATIONALE: tightened the opening\n\nBODY:\n```text\nthe new body\n```")
    assert rationale == "tightened the opening"
    assert body == "the new body"


def test_parse_falls_back_to_the_whole_reply(evolve):
    body, rationale = evolve.propose.parse("just the body, no format", fallback_body="old")
    assert body == "just the body, no format"
    assert rationale == ""


def test_an_empty_reply_falls_back_to_the_current_body(evolve):
    body, _ = evolve.propose.parse("", fallback_body="old")
    assert body == "old"


def test_the_proposal_prompt_carries_failures_and_past_lessons(evolve):
    _register(evolve, seed="plain")
    suite = _suite(evolve)
    evolve.arena.compete("test.prompt", "worse", suite, diff_summary="dropped the token")

    seen = {}

    def fake(system, user):
        seen["user"] = user
        return "RATIONALE: add it back\n\nBODY:\nmuch better"

    body, rationale = evolve.propose.propose(
        "test.prompt", suite.evaluate("plain"), propose_fn=fake)

    assert body == "much better"
    assert rationale == "add it back"
    assert "has_token" in seen["user"]            # the failing case
    assert "dropped the token" in seen["user"]    # the ledger lesson
    assert "plain" in seen["user"]                # the current body


# ── loop ─────────────────────────────────────────────────────────────────────

def test_evolve_once_runs_a_generation_end_to_end(evolve, monkeypatch):
    monkeypatch.setenv("EVOLVE_EXECUTE", "true")
    monkeypatch.setenv("EVOLVE_COOLDOWN_S", "0")
    importlib.reload(evolve.loop)
    _register(evolve, seed="plain")

    out = evolve.loop.evolve_once(
        "test.prompt", _suite(evolve),
        propose_fn=lambda s, u: "RATIONALE: add the token\n\nBODY:\nmuch better",
        cooldown_s=0)

    assert out.ran and out.promoted
    assert evolve.artifacts.body("test.prompt") == "much better"


def test_a_proposer_outage_leaves_the_champion_in_place(evolve):
    _register(evolve, seed="plain")

    def dead(system, user):
        raise RuntimeError("provider down")

    out = evolve.loop.evolve_once("test.prompt", _suite(evolve),
                                  propose_fn=dead, cooldown_s=0)
    assert out.ran is False
    assert "proposer failed" in out.reason
    assert evolve.artifacts.body("test.prompt") == "plain"


def test_an_unchanged_proposal_does_not_burn_a_generation(evolve):
    _register(evolve, seed="plain")
    out = evolve.loop.evolve_once("test.prompt", _suite(evolve),
                                  propose_fn=lambda s, u: "BODY:\nplain", cooldown_s=0)
    assert out.ran is False
    assert "unchanged" in out.reason
    assert evolve.ledger.stats("test.prompt")["attempts"] == 0


def test_a_saturated_benchmark_stops_the_loop(evolve):
    _register(evolve, seed="better")   # passes every case already
    out = evolve.loop.evolve_once("test.prompt", _suite(evolve),
                                  propose_fn=lambda s, u: "BODY:\nanything", cooldown_s=0)
    assert out.ran is False
    assert "saturated" in out.reason


def test_the_cooldown_blocks_a_second_generation(evolve):
    _register(evolve, seed="plain")
    suite = _suite(evolve)
    evolve.arena.compete("test.prompt", "worse", suite)   # writes a ledger row

    out = evolve.loop.evolve_once("test.prompt", suite,
                                  propose_fn=lambda s, u: "BODY:\nmuch better",
                                  cooldown_s=3600)
    assert out.ran is False
    assert "cooldown" in out.reason


def test_scheduled_task_is_shed_before_serving_work(evolve):
    _register(evolve, seed="plain")
    task = evolve.loop.scheduled_task("test.prompt", _suite(evolve), interval_s=600)
    assert task.id == "evolve_test.prompt"
    assert "evolve" in task.tags
    assert task.priority >= 3      # standard: HEALTHY only
