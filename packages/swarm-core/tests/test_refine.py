"""swarm_core.refine — the iterate loop and the humanizer."""
from __future__ import annotations

import importlib

import pytest

from swarm_core.refine import maybe_humanize, refine
from swarm_core.refine.humanize import humanize

humanize_mod = importlib.import_module("swarm_core.refine.humanize")


# ── refine ───────────────────────────────────────────────────────────────────

def test_refine_halts_at_max_rounds_when_stop_never_fires():
    seen = []
    res = refine(
        produce=lambda prev, i: (seen.append(i), i)[1],
        critique=lambda c: float(c),          # strictly improving every round
        max_rounds=3,
        stop_when=lambda c, s: False,
    )
    assert res.rounds == 3
    assert res.stopped_because == "max_rounds"
    assert res.best == 2
    assert seen == [0, 1, 2]


def test_refine_keeps_best_not_last():
    scores = [1.0, 5.0, 2.0]
    res = refine(
        produce=lambda prev, i: i,
        critique=lambda c: scores[c],
        max_rounds=3,
        stop_when=lambda c, s: False,
    )
    # round 2 (score 2.0) does not beat best 5.0 -> early "no_improvement" stop
    assert res.best == 1
    assert res.best_score == 5.0
    assert res.stopped_because == "no_improvement"


def test_refine_stop_when_wins():
    res = refine(
        produce=lambda prev, i: i,
        critique=lambda c: float(c),
        max_rounds=9,
        stop_when=lambda c, s: s >= 1.0,
    )
    assert res.stopped_because == "stop_when"
    assert res.rounds == 2


def test_refine_returns_best_on_producer_error():
    def produce(prev, i):
        if i == 2:
            raise RuntimeError("boom")
        return i

    res = refine(produce=produce, critique=lambda c: float(c),
                 max_rounds=5, stop_when=lambda c, s: False)
    assert res.stopped_because == "error"
    assert res.best == 1


def test_refine_clamps_max_rounds():
    res = refine(produce=lambda p, i: i, critique=lambda c: 0.0,
                 max_rounds=999, stop_when=lambda c, s: False)
    assert res.rounds <= 10


# ── humanize ─────────────────────────────────────────────────────────────────

def test_humanize_strips_tells_but_keeps_facts():
    src = (
        "It's not just fast, it's a game-changing tool.\n"
        "The Qdrant index holds 1,240 vectors at 99.5% recall.\n"
        "I hope this helps!"
    )
    out = humanize(src)
    assert "game-changing" not in out and "game changer" not in out
    assert "not just" not in out
    assert "I hope this helps" not in out
    # facts survive
    assert "1,240" in out
    assert "99.5%" in out
    assert "Qdrant" in out


def test_humanize_returns_original_if_a_number_would_be_lost(monkeypatch):
    monkeypatch.setattr(humanize_mod, "_apply", lambda t, v: "no digits here at all")
    src = "Balance is 4212 tokens."
    assert humanize(src) == src


def test_humanize_returns_original_on_exception(monkeypatch):
    def boom(*a, **k):
        raise ValueError("nope")

    monkeypatch.setattr(humanize_mod, "_apply", boom)
    src = "Plain sentence with Proper Nouns like Redis."
    assert humanize(src) == src


def test_humanize_preserves_proper_nouns():
    src = "We leverage Groq and OpenRouter via the redacted-proxy seamlessly."
    out = humanize(src)
    assert "Groq" in out and "OpenRouter" in out
    assert "leverage" not in out  # inflation word rewritten to "use"


# ── maybe_humanize (env gate + leakscan) ─────────────────────────────────────

def test_maybe_humanize_noop_when_disabled(monkeypatch):
    monkeypatch.delenv("SWARM_HUMANIZE", raising=False)
    src = "I hope this helps! very unique result."
    assert maybe_humanize(src) == src


def test_maybe_humanize_runs_when_enabled(monkeypatch):
    monkeypatch.setenv("SWARM_HUMANIZE", "true")
    out = maybe_humanize("The result is unique. I hope this helps!")
    assert "I hope this helps" not in out


def test_maybe_humanize_returns_original_if_leakscan_trips(monkeypatch):
    monkeypatch.setenv("SWARM_HUMANIZE", "true")
    import swarm_core.security.leakscan as ls
    monkeypatch.setattr(ls, "scan", lambda t: ["fake-hit"])
    src = "Some text. I hope this helps!"
    assert maybe_humanize(src) == src
