"""solana.keystore: encrypted, independent per-agent keypairs; stable across
reload; no secret material leaks into repr/str."""
from __future__ import annotations

import json

import pytest

pytest.importorskip("solders")
pytest.importorskip("cryptography")


@pytest.fixture()
def ks(tmp_path, monkeypatch):
    monkeypatch.setenv("SWARM_WALLET_KEK", "unit-test-kek-do-not-use")
    monkeypatch.setenv("SWARM_WALLET_KEYSTORE", str(tmp_path / "agent_wallets.enc"))
    # get_secret caches for the process; clear so the env var is picked up fresh
    from swarm_core.security import secrets as _s
    _s._cache.clear()
    from swarm_core.solana import keystore as _k
    return _k


def test_generate_is_stable_and_independent(ks):
    a = ks.generate(["smolting", "hermes"])
    assert set(a) == {"smolting", "hermes"}
    assert a["smolting"] != a["hermes"]
    # re-generate without overwrite is a no-op: same addresses
    b = ks.generate(["smolting", "hermes"])
    assert b == a
    # a fresh module-level read still sees them (decrypts from disk)
    assert ks.all_addresses() == a


def test_keypair_round_trips_and_signs(ks):
    ks.generate(["hermes"])
    kp = ks.get_keypair("hermes")
    assert str(kp.pubkey()) == ks.get_address("hermes")
    msg = b"swarm refuel 0.05"
    sig = kp.sign_message(msg)
    from solders.pubkey import Pubkey  # noqa
    assert sig.verify(kp.pubkey(), msg)


def test_file_is_encrypted_not_plaintext(ks, tmp_path):
    ks.generate(["smolting"])
    blob = (tmp_path / "agent_wallets.enc").read_bytes()
    assert b"smolting" not in blob and b"pubkey" not in blob
    with pytest.raises(Exception):
        json.loads(blob)


def test_locked_without_kek(tmp_path, monkeypatch):
    monkeypatch.delenv("SWARM_WALLET_KEK", raising=False)
    monkeypatch.setenv("SWARM_WALLET_KEYSTORE", str(tmp_path / "ks.enc"))
    from swarm_core.security import secrets as _s
    _s._cache.clear()
    from swarm_core.solana import keystore as _k
    assert _k.all_addresses() == {}
    assert _k.has_wallet("smolting") is False
    with pytest.raises(_k.KeystoreLocked):
        _k.generate(["smolting"])


def test_unknown_agent_raises(ks):
    ks.generate(["hermes"])
    with pytest.raises(ks.KeystoreError):
        ks.get_keypair("smolting")  # never generated
