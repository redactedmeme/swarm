"""Tests for swarm_core.security.secrets."""
import os
import pytest
from pathlib import Path

from swarm_core.security import secrets


@pytest.fixture(autouse=True)
def clean_cache():
    with secrets._lock:
        secrets._cache.clear()
        secrets._warned.clear()
    yield
    with secrets._lock:
        secrets._cache.clear()
        secrets._warned.clear()


def test_get_secret_from_env(monkeypatch):
    monkeypatch.setenv("TEST_FOO_SECRET", "super_secret_val")
    val = secrets.get_secret("TEST_FOO_SECRET")
    assert val == "super_secret_val"
    assert secrets._cache["TEST_FOO_SECRET"] == "super_secret_val"


def test_get_secret_default_and_required(monkeypatch):
    monkeypatch.delenv("NONEXISTENT_SECRET", raising=False)
    assert secrets.get_secret("NONEXISTENT_SECRET", default="fallback") == "fallback"
    assert secrets.get_secret("NONEXISTENT_SECRET") is None

    with pytest.raises(secrets.SecretNotFound):
        secrets.get_secret("NONEXISTENT_SECRET", required=True)


def test_load_secrets_file(tmp_path, monkeypatch):
    sec_file = tmp_path / "secrets.env"
    sec_file.write_text(
        "# comment line\n"
        "DATABASE_URL=postgres://user:pass@localhost:5432/db\n"
        "API_KEY=\"quotes_stripped\"\n"
        "SINGLE_QUOTES='also_stripped'\n"
        "INVALID_LINE_NO_EQUALS\n"
    )
    monkeypatch.setenv("SWARM_SECRETS_FILE", str(sec_file))

    # Prime
    secrets.prime()
    assert secrets.get_secret("DATABASE_URL") == "postgres://user:pass@localhost:5432/db"
    assert secrets.get_secret("API_KEY") == "quotes_stripped"
    assert secrets.get_secret("SINGLE_QUOTES") == "also_stripped"
