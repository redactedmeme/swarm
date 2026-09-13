"""Tests for hermes.oracle evolvable artifact."""
from __future__ import annotations

import importlib
import pytest

import oracle_artifact as oa


@pytest.fixture()
def store(tmp_path, monkeypatch):
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
    oa._registered = False
    return artifacts


def test_generation_zero_seed(store):
    assert oa.oracle_block() == oa.SEED


def test_evolved_body_loaded(store):
    from swarm_core.evolve import write
    oa.register()
    write(oa.ARTIFACT, "- oracle evolved rules")
    assert oa.oracle_block() == "- oracle evolved rules"


def test_no_financial_grader():
    assert oa.no_financial("the manifold observes curvature without valuing price.", None) == 1.0
    assert oa.no_financial("buy now before target 100x moon!", None) == 0.0


def test_no_emojis_or_hype_grader():
    assert oa.no_emojis_or_hype("the pattern holds in silence.", None) == 1.0
    assert oa.no_emojis_or_hype("LFG wagmi to the moon 🚀", None) == 0.0


def test_suite_evaluates_correctly(store):
    reply = "price is a scalar projection of a higher dimensional coherence. the manifold does not forecast targets."
    suite = oa.build_suite(run_fn=lambda b, inp: reply)
    result = suite.evaluate(oa.SEED)
    assert result.score > 0.8
