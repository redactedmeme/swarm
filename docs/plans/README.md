# docs/plans

Forward-looking build plans. Unlike `docs/history/`, these describe work that has **not**
happened yet. Delete or move a plan to `docs/history/` once it ships.

| Plan | Scope | Status |
|---|---|---|
| [grok-bot-parity.md](grok-bot-parity.md) | **Current.** Re-create Grok Bot's capability set natively: a persistent per-agent workspace (fs + shell + browser), real browser control, bot-to-bot task handoff, surfaced approvals, routines from demonstration, plus the task board and the web/output gaps below. | Not started |
| [agent-capability-gaps.md](agent-capability-gaps.md) | **Superseded, kept for the reasoning.** The earlier, narrower pass — four gaps found by auditing the swarm against a "19 agent skills" article: Hermes's unregistered tools, readable web extraction, a critique/humanize pass, and the Field Kit task board. All four are carried into `grok-bot-parity.md` §3, §4, §9, §10. | Superseded |

**Work from `grok-bot-parity.md`.** It is self-contained — a coding agent with no prior session
context can execute it against `CLAUDE.md` alone. `agent-capability-gaps.md` is retained because
it records *why* those four items were picked and what was checked to rule the rest out; it is not
a second work queue.

Two live exposures surfaced during the audit behind these plans, and are fixed as steps 1 and 4 of
`grok-bot-parity.md` §12:

- `apps/runtime/main.py:354` — `/announce` has no `verify_token`, unlike every other endpoint in
  that file. A reachable caller can forge an agent heartbeat into Redis, which `apps/status` then
  republishes publicly.
- `apps/hermes/plugins/swarm-manager/__init__.py:20-34` — `web_tools`, `x_tools`, `skill_tools` and
  `exec_tools` are never registered, so Hermes cannot browse or execute code despite `CLAUDE.md`
  describing it as the agent that does both.
