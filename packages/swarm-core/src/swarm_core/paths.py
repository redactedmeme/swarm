"""Filesystem anchors for the swarm.

Before this module, ~40 sites across the repo each recomputed the repo root with
their own `Path(__file__).parent.parent` chain and inserted directories onto
`sys.path`. Every one of them encoded that file's depth, so moving a file broke
paths in ways that only showed up at runtime.

Everything that needs a directory outside its own package asks here instead.
Each anchor honours an environment variable first, so a container can point at
a real mount without the layout having to match a developer's checkout.
"""
from __future__ import annotations

import os
from pathlib import Path

# .../packages/swarm-core/src/swarm_core/paths.py → repo root is 4 levels up.
_PKG_ROOT = Path(__file__).resolve().parent
_REPO_ROOT = _PKG_ROOT.parent.parent.parent.parent


def repo_root() -> Path:
    """Root of the checkout. `SWARM_REPO_ROOT` wins when set."""
    env = os.getenv("SWARM_REPO_ROOT")
    return Path(env).resolve() if env else _REPO_ROOT


def package_root() -> Path:
    """The installed `swarm_core` package directory itself."""
    return _PKG_ROOT


def data_dir() -> Path:
    """Runtime state (formerly the repo-root `fs/` directory).

    Containers mount a real volume and set `SWARM_DATA_DIR`; a bare checkout
    falls back to `fs/` so local runs keep working.
    """
    env = os.getenv("SWARM_DATA_DIR")
    if env:
        return Path(env)
    for candidate in (repo_root() / "data", repo_root() / "fs"):
        if candidate.exists():
            return candidate
    return repo_root() / "fs"


def plugins_dir() -> Path:
    """Repo `plugins/` tree — holds the mem0-memory wrapper several modules import."""
    env = os.getenv("SWARM_PLUGINS_DIR")
    return Path(env) if env else repo_root() / "plugins"


def mem0_dir() -> Path:
    """The mem0-memory plugin directory."""
    return plugins_dir() / "mem0-memory"


def vault_dir() -> Path:
    """Markdown knowledge vault.

    `VAULT_PATH` is accepted as well as `SWARM_VAULT_DIR`: services that bundle
    their own copy of the vault (smolting ships one in its image) already set it.
    """
    env = os.getenv("SWARM_VAULT_DIR") or os.getenv("VAULT_PATH")
    return Path(env) if env else repo_root() / "vault"


def agents_dir() -> Path:
    """`*.character.json` definitions."""
    env = os.getenv("SWARM_AGENTS_DIR")
    return Path(env) if env else repo_root() / "agents"
