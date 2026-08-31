"""Secret resolution (IronClaw control 2, library half).

IronClaw keeps secrets "encrypted at rest" and injects them "at the host boundary
only for approved endpoints" — tool/agent code never holds raw keys. The swarm's
starting point is the opposite: flat ``.env`` files, ``os.getenv`` at every call
site, a plaintext ``secrets/`` mirror.

This module is the seam to migrate onto. Call ``get_secret("OPENAI_API_KEY")``
instead of ``os.getenv``; the resolution order is:

    1. process cache (populated by ``prime()`` at startup)
    2. ``SWARM_SECRETS_FILE`` — a tmpfs file the ``secrets-init`` sidecar writes
       (``KEY=VALUE`` lines); never committed, never on a persistent volume
    3. environment variable (legacy; logged as a deprecation once per key)
    4. Vaultwarden via the repo's ``scripts/vault.py`` / ``bw`` CLI, if
       ``SWARM_SECRETS_BACKEND=vaultwarden`` and a session is available

The Vaultwarden path shells out and caches the result for the process lifetime.
Nothing here writes secrets to disk or logs their values.
"""
from __future__ import annotations

import logging
import os
import subprocess
import threading
from pathlib import Path

log = logging.getLogger(__name__)

_cache: dict[str, str] = {}
_warned: set[str] = set()
_lock = threading.Lock()


class SecretNotFound(KeyError):
    pass


def _load_secrets_file() -> None:
    path = os.getenv("SWARM_SECRETS_FILE", "")
    if not path or not Path(path).is_file():
        return
    try:
        for line in Path(path).read_text("utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            _cache.setdefault(k.strip(), v.strip().strip('"').strip("'"))
    except Exception as exc:  # pragma: no cover - defensive
        log.warning("secrets: could not read SWARM_SECRETS_FILE (%s)", exc)


def _from_vaultwarden(name: str) -> str | None:
    if os.getenv("SWARM_SECRETS_BACKEND", "").lower() != "vaultwarden":
        return None
    repo = os.getenv("SWARM_REPO_ROOT") or str(Path(__file__).resolve().parents[5])
    vault_py = Path(repo) / "scripts" / "vault.py"
    try:
        if vault_py.is_file():
            out = subprocess.run(
                ["python", str(vault_py), "get", name],
                capture_output=True, text=True, timeout=20,
            )
        else:
            out = subprocess.run(
                ["bw", "get", "password", name],
                capture_output=True, text=True, timeout=20,
            )
        if out.returncode == 0 and out.stdout.strip():
            return out.stdout.strip()
        log.warning("secrets: vaultwarden lookup for %s failed rc=%s", name, out.returncode)
    except Exception as exc:  # pragma: no cover - env dependent
        log.warning("secrets: vaultwarden backend error for %s: %s", name, exc)
    return None


def prime(names: list[str] | None = None) -> None:
    """Populate the process cache from the tmpfs file (and, if configured,
    Vaultwarden for any ``names`` still missing). Call once at startup."""
    with _lock:
        _load_secrets_file()
        for n in names or []:
            if n not in _cache:
                v = _from_vaultwarden(n)
                if v is not None:
                    _cache[n] = v


def get_secret(name: str, default: str | None = None, *, required: bool = False) -> str | None:
    with _lock:
        if name in _cache:
            return _cache[name]
        if not _cache:
            _load_secrets_file()
            if name in _cache:
                return _cache[name]

        env = os.getenv(name)
        if env is not None:
            if name not in _warned:
                log.info("secrets: %s resolved from environment (migrate to SWARM_SECRETS_FILE)", name)
                _warned.add(name)
            _cache[name] = env
            return env

        v = _from_vaultwarden(name)
        if v is not None:
            _cache[name] = v
            return v

    if required:
        raise SecretNotFound(name)
    return default
