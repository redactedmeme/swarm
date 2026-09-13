"""Tests for swarm_core.solana.keystore."""
import os
import pytest

from swarm_core.solana import keystore


@pytest.fixture(autouse=True)
def clean_env(tmp_path, monkeypatch):
    enc_path = tmp_path / "test_wallets.enc"
    monkeypatch.setenv("SWARM_WALLET_KEYSTORE", str(enc_path))
    monkeypatch.setenv("SWARM_WALLET_KEK", "test-kek-super-secret-key-material")
    from swarm_core.security import secrets
    with secrets._lock:
        secrets._cache.pop("SWARM_WALLET_KEK", None)
    yield


def test_keystore_locked_without_kek(monkeypatch):
    monkeypatch.delenv("SWARM_WALLET_KEK", raising=False)
    from swarm_core.security import secrets
    with secrets._lock:
        secrets._cache.pop("SWARM_WALLET_KEK", None)

    assert not keystore.has_wallet("hermes")
    assert keystore.all_addresses() == {}
    with pytest.raises(keystore.KeystoreLocked):
        keystore.generate(["hermes"])


def test_generate_and_retrieve_wallets():
    pytest.importorskip("solders")

    addrs = keystore.generate(["hermes", "smolting"])
    assert "hermes" in addrs
    assert "smolting" in addrs
    assert keystore.has_wallet("hermes")
    assert keystore.has_wallet("smolting")
    assert not keystore.has_wallet("unknown_agent")

    assert keystore.get_address("hermes") == addrs["hermes"]
    assert keystore.get_address("smolting") == addrs["smolting"]
    assert keystore.get_address("unknown_agent") is None

    kp = keystore.get_keypair("hermes")
    assert str(kp.pubkey()) == addrs["hermes"]

    addrs_again = keystore.generate(["hermes"])
    assert addrs_again["hermes"] == addrs["hermes"]


def test_overwrite_wallet():
    pytest.importorskip("solders")

    addr1 = keystore.generate(["hermes"])["hermes"]
    addr2 = keystore.generate(["hermes"], overwrite=True)["hermes"]
    assert addr1 != addr2
    assert keystore.get_address("hermes") == addr2


def test_all_addresses():
    pytest.importorskip("solders")

    assert keystore.all_addresses() == {}
    keystore.generate(["agent_a", "agent_b"])
    all_addrs = keystore.all_addresses()
    assert set(all_addrs.keys()) == {"agent_a", "agent_b"}
