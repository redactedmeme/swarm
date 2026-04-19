# vault/ — Lore Wiki (Root Copy)

Markdown wiki seeding `lore_vault.db` (root-level) and consumed by gnosis ingest + local tooling.

## Dual-Location Reality

There are **two** vault directories in this repo:

| Path | Runtime | Consumer |
|------|---------|----------|
| `vault/` (this dir) | local + gnosis | `python/lore_vault.py` via `_ROOT / "vault"` |
| `smolting-telegram-bot/vault/` | Railway `smolting-telegram-bot` service | `smolting-telegram-bot/python/lore_vault.py` (self-rooted) |

As of 2026-04-18 they are **byte-identical** (`diff -rq` returns zero).

## Sync Rule

**Edit root `vault/` first, then copy to `smolting-telegram-bot/vault/`:**

```bash
# after editing root vault/
rsync -a --delete vault/ smolting-telegram-bot/vault/
git add vault/ smolting-telegram-bot/vault/
```

Root is the canonical authoring location. The service copy exists because the Railway Dockerfile in `smolting-telegram-bot/` only has access to files inside its own service directory — it cannot reach up to repo root.

## Future consolidation

Options if divergence ever becomes a maintenance problem:
1. Pre-build step: copy `vault/` into `smolting-telegram-bot/vault/` as part of deploy (CI hook)
2. Git submodule (overkill for a wiki)
3. Move vault content to the pattern-blue repo and fetch at boot (like `hermes-bot/persona/pattern_blue_loader.py`)

For now, manual rsync after edits is sufficient.
