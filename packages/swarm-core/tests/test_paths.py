"""Tests for swarm_core.paths."""
import os
from pathlib import Path
import pytest

from swarm_core import paths


def test_default_paths():
    repo = paths.repo_root()
    assert repo.is_dir()
    assert (repo / "packages").is_dir()

    pkg = paths.package_root()
    assert pkg.name == "swarm_core"

    data = paths.data_dir()
    assert isinstance(data, Path)


def test_env_overrides(tmp_path, monkeypatch):
    fake_repo = tmp_path / "custom_repo"
    fake_repo.mkdir()
    fake_data = tmp_path / "custom_data"
    fake_data.mkdir()
    fake_vault = tmp_path / "custom_vault"
    fake_vault.mkdir()

    monkeypatch.setenv("SWARM_REPO_ROOT", str(fake_repo))
    monkeypatch.setenv("SWARM_DATA_DIR", str(fake_data))
    monkeypatch.setenv("SWARM_VAULT_DIR", str(fake_vault))

    assert paths.repo_root() == fake_repo.resolve()
    assert paths.data_dir() == fake_data
    assert paths.vault_dir() == fake_vault
