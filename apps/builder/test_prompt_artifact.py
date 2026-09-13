"""Tests for builder.prompt evolvable artifact."""
from __future__ import annotations

import importlib
import pytest

import prompt_artifact as pa


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
    pa._registered = False
    return artifacts


def test_generation_zero_seed(store):
    assert pa.prompt_block() == pa.SEED


def test_evolved_body_loaded(store):
    from swarm_core.evolve import write
    pa.register()
    write(pa.ARTIFACT, "- builder evolved rules")
    assert pa.prompt_block() == "- builder evolved rules"


def test_no_bureaucracy_grader():
    assert pa.no_bureaucracy("just fixed the slippage on jup, we're cooking", None) == 1.0
    assert pa.no_bureaucracy("ANALYSIS: Slippage occurred due to high volatility.", None) == 0.0


def test_dev_credibility_grader():
    assert pa.dev_credibility("jupiter routed through clmm and hit slippage limits", None) == 1.0
    assert pa.dev_credibility("hello there", None) == 0.3


def test_suite_evaluates_correctly(store):
    good_reply = "ngl jupiter slippage failed on raydium clmm curve, we're updating priority fees"
    suite = pa.build_suite(run_fn=lambda b, inp: good_reply)
    result = suite.evaluate(pa.SEED)
    assert result.score > 0.8
