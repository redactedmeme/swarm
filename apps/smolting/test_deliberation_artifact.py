"""Tests for smolting.deliberation evolvable artifact."""
from __future__ import annotations

import importlib
import pytest

import deliberation_artifact as da


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
    da._registered = False
    return artifacts


def test_generation_zero_seed(store):
    assert da.deliberation_block() == da.SEED


def test_evolved_body_loaded(store):
    from swarm_core.evolve import write
    da.register()
    write(da.ARTIFACT, "- smolting evolved deliberation rules")
    assert da.deliberation_block() == "- smolting evolved deliberation rules"


def test_no_fluff_grader():
    assert da.no_fluff("The manifold curves where tokenomics meet entropy.", None) == 1.0
    assert da.no_fluff("Great point! In conclusion, I hope this helps.", None) == 0.0


def test_philosophical_depth_grader():
    assert da.philosophical_depth("Without recursive tension, the contract loses its coherence.", None) == 1.0
    assert da.philosophical_depth("yes totally agree", None) == 0.4


def test_suite_evaluates_correctly(store):
    thought = "Token burns without soul coherence are just empty heat on the manifold. Why compress supply if identity drifts?"
    suite = da.build_suite(run_fn=lambda b, inp: thought)
    result = suite.evaluate(da.SEED)
    assert result.score > 0.8
