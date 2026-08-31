"""Encrypted at-rest keypair store for per-agent Solana wallets.

Design (matches the IronClaw secrets posture the rest of the swarm moved to):

* One file, ``data_dir()/agent_wallets.enc``. It is runtime state, never the
  repo (CLAUDE.md rule); ``data_dir()`` resolves to a real mount in containers.
* Contents are a JSON document, Fernet-encrypted with a key derived from the
  ``SWARM_WALLET_KEK`` secret (resolved through ``swarm_core.security.secrets``,
  so tmpfs -> env -> Vaultwarden all work). Losing the KEK loses the wallets.
* Keypairs are independent (freshly generated), not derived from a shared seed.
* ``solders`` is lazy-imported - importing this module never requires the
  ``solana`` extra; only ``generate`` / ``get_keypair`` do.

The on-disk JSON shape (before encryption)::

    {"version": 1,
     "agents": {"<agent>": {"pubkey": "<base58>", "secret": [<64 ints>]}}}

``secret`` is the 64-byte solders keypair serialization as an int array - the
same shape ``swarm_core.x402.burn.load_keypair`` and the Solana CLI accept.
"""
from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import threading
from pathlib import Path
from typing import Optional

from swarm_core.paths import data_dir
from swarm_core.security.secrets import get_secret

log = logging.getLogger(__name__)

_VERSION = 1
_LOCK = threading.Lock()
_KEK_ENV = "SWARM_WALLET_KEK"


class KeystoreError(RuntimeError):
    pass


class KeystoreLocked(KeystoreError):
    """No ``SWARM_WALLET_KEK`` available - cannot decrypt or create the store."""


def keystore_path() -> Path:
    override = os.getenv("SWARM_WALLET_KEYSTORE", "").strip()
    return Path(override) if override else data_dir() / "agent_wallets.enc"


# ── crypto ────────────────────────────────────────────────────────────────────

def _fernet():
    from cryptography.fernet import Fernet  # core dep, always present

    kek = get_secret(_KEK_ENV)
    if not kek:
        raise KeystoreLocked(
            f"{_KEK_ENV} is not set - cannot open the agent wallet keystore"
        )
    # Accept an arbitrary-length secret: SHA-256 it to exactly 32 bytes, then
    # urlsafe-b64 as Fernet requires. A already-valid 32-byte urlsafe key also
    # round-trips through this unchanged in practice.
    digest = hashlib.sha256(kek.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def _load_raw() -> dict:
    path = keystore_path()
    if not path.is_file():
        return {"version": _VERSION, "agents": {}}
    token = path.read_bytes()
    try:
        plain = _fernet().decrypt(token)
    except KeystoreLocked:
        raise
    except Exception as exc:  # InvalidToken, corrupt file, wrong KEK
        raise KeystoreError(f"could not decrypt {path.name}: {exc}") from exc
    doc = json.loads(plain)
    if doc.get("version") != _VERSION:
        raise KeystoreError(f"unsupported keystore version {doc.get('version')!r}")
    return doc


def _save_raw(doc: dict) -> None:
    path = keystore_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    token = _fernet().encrypt(json.dumps(doc, separators=(",", ":")).encode("utf-8"))
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(token)
    try:
        os.chmod(tmp, 0o600)
    except OSError:
        pass
    tmp.replace(path)


# ── solders helpers ───────────────────────────────────────────────────────────

def _new_keypair():
    from solders.keypair import Keypair  # type: ignore

    return Keypair()


def _keypair_from_secret(secret: list[int]):
    from solders.keypair import Keypair  # type: ignore

    return Keypair.from_bytes(bytes(secret))


# ── public API ────────────────────────────────────────────────────────────────

def generate(agents, *, overwrite: bool = False) -> dict[str, str]:
    """Create a wallet for each name in ``agents`` that does not already have
    one (or all of them when ``overwrite``). Returns ``{agent: address}`` for
    every requested agent (existing + new)."""
    with _LOCK:
        doc = _load_raw()
        store = doc.setdefault("agents", {})
        for agent in agents:
            if agent in store and not overwrite:
                continue
            kp = _new_keypair()
            store[agent] = {
                "pubkey": str(kp.pubkey()),
                "secret": list(bytes(kp)),
            }
            log.info("[keystore] generated wallet for %s -> %s", agent, store[agent]["pubkey"])
        _save_raw(doc)
        return {a: store[a]["pubkey"] for a in agents if a in store}


def has_wallet(agent: str) -> bool:
    try:
        return agent in _load_raw().get("agents", {})
    except KeystoreLocked:
        return False


def get_address(agent: str) -> Optional[str]:
    entry = _load_raw().get("agents", {}).get(agent)
    return entry["pubkey"] if entry else None


def get_keypair(agent: str):
    """Return the ``solders.keypair.Keypair`` for ``agent`` (raises if absent)."""
    entry = _load_raw().get("agents", {}).get(agent)
    if not entry:
        raise KeystoreError(f"no wallet for agent {agent!r} - run keystore.generate")
    return _keypair_from_secret(entry["secret"])


def all_addresses() -> dict[str, str]:
    try:
        return {a: e["pubkey"] for a, e in _load_raw().get("agents", {}).items()}
    except KeystoreLocked:
        return {}
