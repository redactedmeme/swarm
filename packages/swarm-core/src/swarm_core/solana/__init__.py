"""Per-agent Solana wallets, balances, and the auto-refuel reserve.

- ``swarm_core.solana.keystore`` - encrypted at-rest keypair store
- ``swarm_core.solana.wallets``  - read-only balances + manifest
- ``swarm_core.solana.reserve``  - threshold-driven SOL top-ups (settler-side)

``solders`` is an optional dependency (the ``solana`` extra); every module here
lazy-imports it so ``import swarm_core.solana`` stays cheap and CI-safe.
"""

# Live agent processes that get a self-custody wallet. Dormant/stub agents are
# left out until they actually run.
LIVE_WALLET_AGENTS: tuple[str, ...] = (
    "smolting",
    "redacted-chan",
    "hermes",
    "redactedbuilder",
    "runtime",
    "refinery",
    "settler",
)
