"""secrets-init: manifest parsing, file output perms, strict-mode exit code."""
from __future__ import annotations

import importlib
import os
import stat

import pytest

import fetch


@pytest.fixture()
def cfg(tmp_path, monkeypatch):
    out = tmp_path / "swarm.env"
    monkeypatch.setenv("SWARM_SECRETS_FILE", str(out))
    monkeypatch.setenv("SECRETS_BACKEND", "env")
    importlib.reload(fetch)
    return out


def test_writes_resolved_secrets(cfg, monkeypatch):
    monkeypatch.setenv("SECRETS_MANIFEST", "FOO_KEY, BAR_TOKEN")
    monkeypatch.setenv("FOO_KEY", "aaa")
    monkeypatch.setenv("BAR_TOKEN", "bbb")
    assert fetch.main() == 0
    body = cfg.read_text()
    assert "FOO_KEY=aaa" in body and "BAR_TOKEN=bbb" in body
    if os.name == "posix":
        assert stat.S_IMODE(cfg.stat().st_mode) == 0o600


def test_missing_secret_is_tolerated_by_default(cfg, monkeypatch):
    monkeypatch.setenv("SECRETS_MANIFEST", "PRESENT,ABSENT")
    monkeypatch.setenv("PRESENT", "x")
    monkeypatch.delenv("ABSENT", raising=False)
    assert fetch.main() == 0
    assert "PRESENT=x" in cfg.read_text()
    assert "ABSENT" not in cfg.read_text()


def test_strict_mode_fails_on_missing(cfg, monkeypatch):
    monkeypatch.setenv("SECRETS_MANIFEST", "ABSENT")
    monkeypatch.setenv("SECRETS_STRICT", "1")
    monkeypatch.delenv("ABSENT", raising=False)
    importlib.reload(fetch)
    assert fetch.main() == 1


def test_manifest_file(cfg, tmp_path, monkeypatch):
    mf = tmp_path / "manifest.txt"
    mf.write_text("# comment\nALPHA\nBETA\n")
    monkeypatch.setenv("SECRETS_MANIFEST_FILE", str(mf))
    monkeypatch.delenv("SECRETS_MANIFEST", raising=False)
    monkeypatch.setenv("ALPHA", "1")
    monkeypatch.setenv("BETA", "2")
    importlib.reload(fetch)
    assert fetch.main() == 0
    body = cfg.read_text()
    assert "ALPHA=1" in body and "BETA=2" in body


def test_roundtrip_with_get_secret(cfg, monkeypatch):
    monkeypatch.setenv("SECRETS_MANIFEST", "ROUNDTRIP_KEY")
    monkeypatch.setenv("ROUNDTRIP_KEY", "secret-value")
    fetch.main()

    monkeypatch.delenv("ROUNDTRIP_KEY")  # only the file has it now
    from swarm_core.security import secrets as _s

    importlib.reload(_s)
    assert _s.get_secret("ROUNDTRIP_KEY") == "secret-value"
