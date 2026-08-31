---
name: swarm
description: >
  Drive and observe the REDACTED AI swarm through the `swarm` CLI: list the agent
  roster, read Phi/kernel status, inspect per-agent Solana wallets and balances,
  check or trigger the SOL auto-refuel reserve, delegate a task to another agent
  over SwarmInbox and wait for the result, tail the mesh, or run a Sevenfold
  Committee deliberation. Use whenever the user wants swarm status, agent wallets,
  reserve refuels, task delegation between agents, mesh inspection, or committee
  votes - including the slash forms /roster, /wallets, /reserve, /delegate,
  /mesh, /committee.
compatibility: ">=0.2.0"
---

# swarm

The whole swarm from one entrypoint. Prefer the `swarm` binary if it is on
`PATH`; otherwise `python -m swarm_core.cli` (after
`pip install -e packages/swarm-core -e packages/swarm-tg`).

## Setup check

```bash
swarm --help  ||  python -m swarm_core.cli --help
```

If neither runs, install the packages first:

```bash
pip install -e packages/swarm-core -e packages/swarm-tg
```

## Commands

| Ask | Run |
|---|---|
| roster / "what agents exist" | `swarm roster` (add `--json` to parse) |
| status / phi / kernel | `swarm status` |
| list wallet addresses | `swarm wallets list` |
| one agent's address | `swarm wallets address <agent>` |
| balances (SOL + $REDACTED) | `swarm wallets balance [agent]` |
| create the wallet keystore | `swarm wallets generate` (needs `SWARM_WALLET_KEK`) |
| reserve settings | `swarm reserve status` |
| refuel low agents now | `swarm reserve refuel [agent]` (dry-run unless `RESERVE_EXECUTE=true`) |
| delegate a task | `swarm delegate --from <a> --to <b> --task <type> --inst "..." --wait 60` |
| tail the mesh | `swarm mesh tail -n 30` |
| hand-send a message | `swarm mesh send --from <a> --to <b> --type status_update --data '{...}'` |
| committee vote | `swarm committee "proposal text"` |

## Notes for the model

- `swarm reserve refuel` and `swarm mesh send` write to Redis / can move SOL when
  `RESERVE_EXECUTE=true`. Confirm with the user before running those with execute on.
- `swarm wallets generate` creates real keypairs in an encrypted keystore. It is
  safe (nothing funds them automatically) but is a one-time setup step - do not
  re-run with `--overwrite` unless the user asks.
- Everything else (`roster`, `status`, `wallets list/address/balance`,
  `mesh tail`, `reserve status`, `committee`) is read-only.
- `REDIS_URL` must be set for `delegate`, `mesh`, and `reserve refuel`.
- Commands that read repo data (`roster`, `committee`) need either a repo
  checkout as CWD or `SWARM_REPO_ROOT=/path/to/swarm-main`. The native binary
  bundles that data; the `.pyz` does not.
