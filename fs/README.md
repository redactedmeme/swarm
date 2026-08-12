# fs/ — historical runtime snapshot (NOT live state)

Everything under `fs/` is runtime state (agent memories, swarm message history,
lorenet inboxes/heartbeats, kernel/pattern-blue state, logs) captured from the
**git-branch snapshot**, not pulled from the live Railway containers.

**Treat this as historical data frozen at 2026-07-29.** Do not rely on it for
anything time-sensitive — the authoritative live state lives in the running
services and their `/data` volumes. See `docs/history/CONSOLIDATION_SUMMARY.md` §5.

Most of `fs/` is gitignored (see root `.gitignore`): `fs/memories/`,
`fs/sessions/`, `fs/swarm_messages/`, `fs/logs/`, and generated index files are
excluded. What remains tracked here is retained only as historical reference.
