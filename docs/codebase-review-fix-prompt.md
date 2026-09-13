# Follow-up Prompt — Apply Reviewed Fixes

Paste this into Antigravity (Gemini 3.8 Flash) after the initial review report.
It's scoped to items already spot-checked against the repo — don't re-open
items 2/3/4/6/7/8/9 from the report without verifying them the same way first
(grep the actual file/line before trusting the report's claim).

---

## Context

You previously produced a review report for this repo (`Z:\swarm-main`). Two
of its "High" findings and one "dead code" claim have been spot-checked and
confirmed correct:

- `apps/hermes/railway.toml` really does use `builder = "nixpacks"` with no
  monorepo-aware install step, while hermes imports `swarm_core`/`swarm_tg`.
- `apps/runtime/railway.toml` really does set `dockerfilePath = "runtime/Dockerfile"`,
  which is wrong under either a repo-root or an `apps/runtime`-scoped context.
- `apps/mcp` genuinely does not exist on disk — CLAUDE.md and README.md
  references to it are stale.

Everything else in your prior report (promptguard gaps, authz gaps, secrets
migration, shim consolidation, test coverage gaps) has **not** been
independently verified yet. Treat your own prior line numbers and file
contents as unconfirmed until you re-read the current file — don't act on
memory of what you wrote before.

## Task — do these in order, one at a time, re-reading each file fresh before editing

### 1. Fix `apps/hermes/railway.toml`
Read `apps/hermes/railway.toml` and `apps/terminal/railway.toml` (a known-good
Docker-based config for a repo-root-context service). Change hermes to match
that pattern: `builder = "DOCKERFILE"`, `dockerfilePath` pointing at
`apps/hermes/Dockerfile`, keeping any working `startCommand`/`deploy` settings.
Confirm `apps/hermes/Dockerfile` exists and actually `COPY`s `packages/` before
declaring this fixed.

### 2. Fix `apps/runtime/railway.toml`
Read `apps/runtime/railway.toml` and `infra/umbrel/swarm-infra-docker-compose.yml`'s
entry for `runtime` to see what build context is actually used there. Match
`dockerfilePath` to the real Dockerfile location relative to whatever
`rootDirectory` this service uses — confirm with the Railway dashboard setting
if you can't determine it from repo files alone (state clearly if you can't).

### 3. Clean up stale `apps/mcp` references
Grep `CLAUDE.md` and `README.md` for `apps/mcp` and either remove the
reference or update it to point at where that functionality actually lives
now (you previously identified `apps/smolting/swarm_mcp_stdio.py` and
`packages/swarm-core/src/swarm_core/tools/clawnch_mcp_tools.py` — verify those
paths exist before citing them again).

### Stop after these three.

Do not touch security code (`promptguard`, `authz`, `secrets`), feature flags,
or the duplication/shim cleanup in this pass — those need a human decision
(especially the `SWARM_INBOX_ENFORCE` default and anything touching treasury
keys) and should go through a separate reviewed PR, not be auto-applied.

## Output

For each of the 3 items: show the diff, state how you verified the fix is
correct (what you read, what you'd still need the live box/Railway dashboard
to confirm), and flag anything that turned out different from your original
report once you re-read the file.
