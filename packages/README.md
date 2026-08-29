# packages/

Installable shared libraries. Services depend on these as ordinary Python
packages instead of reaching across the repo with `sys.path` inserts.

| Package | Was | Holds |
|---|---|---|
| `swarm-core` | `python/`, `kernel/`, `core/`, `llm/`, `vault/vault_io.py`, `lib/kernel/hyperbolic_scheduler.py` | Committee deliberation, BEAM-SCoT, the {7,3} hyperbolic kernel, lore vault, agent registry, session store, schedulers |
| `swarm-tg` | `shared/` | Telegram formatting (`TgFmt`, `from_llm`) and the swarm task client, shared by all four bots |

## Why

`python/` was the de-facto shared library but was not importable. Every consumer
reached it through a `sys.path.insert` whose path was computed from that file's
own depth, so moving any file broke imports at runtime rather than at import time.
The repo held ~40 such sites. Copies drifted: `lib/` shadowed `python/` with
diverged forks, `llm/` existed three times, `vault_io.py` three times.

## Installing

Plain setuptools distributions — `pip` is enough, and that is what the service
containers have:

```bash
pip install -e packages/swarm-core -e packages/swarm-tg
```

Optional extras on `swarm-core`: `llm` (groq/anthropic/ollama clients),
`solana` (settlement path), `memory` (mem0 integration), `dev`.

## Paths

`swarm_core.paths` is the single source of truth for every directory outside a
package — `repo_root()`, `data_dir()`, `plugins_dir()`, `mem0_dir()`,
`vault_dir()`, `agents_dir()`. Each honours an environment variable
(`SWARM_DATA_DIR`, `SWARM_REPO_ROOT`, …) so a container can point at a real
mount without its layout having to match a developer's checkout. Add anchors
here rather than recomputing `__file__`-relative parents at the call site.

## Known non-package imports

Two directories are hyphenated and therefore cannot be imported as packages:
`plugins/mem0-memory` and the bot directories. Modules that need them insert the
path from `swarm_core.paths` and degrade gracefully when absent. These are the
only `sys.path` inserts that should remain inside `packages/`.
