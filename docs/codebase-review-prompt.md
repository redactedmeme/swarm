# Codebase Review Prompt — REDACTED AI Swarm

Paste this into Antigravity (Gemini 3.8 Flash) with repo access to `Z:\swarm-main`.

---

## Context

This is a monorepo for an autonomous AI agent swarm: `apps/` holds ~20 deployable
services (Python, mostly Docker-deployed to a home umbrel node, a few on
Railway/Vercel), `packages/` holds three shared libraries (`swarm-core`,
`swarm-tg`, `swarm-agent-base`) that the apps import. Full architecture is in
`CLAUDE.md` and `README.md` at the repo root — read both before reviewing
anything else.

## Known failure modes to check for specifically

1. **Build-context mismatches.** A service that imports `swarm_core`/`swarm_tg`
   must build with the repo root as Docker context (to `COPY packages/`).
   Self-contained services (`proxy`, `dashboard`, `webchat`, `website`,
   `fieldkit`, `exec-runner`, `dsh`) must keep their own directory as context.
   Cross-check every app's actual imports against
   `infra/umbrel/swarm-infra-docker-compose.yml` build contexts and any
   Railway `rootDirectory` settings. Flag any app that imports shared code but
   isn't listed as repo-root-context in CLAUDE.md's table, or vice versa.
2. **Duplicated code that should be shared.** This repo has a documented history
   of hand-synced duplicates (tg formatting, heartbeat loops) drifting apart.
   Grep for near-identical functions/classes across `apps/*` that aren't
   importing from `packages/`.
3. **Path computation via `__file__` parent-counting.** Should always go through
   `swarm_core.paths` (`repo_root()`, `data_dir()`, etc.). Flag any raw
   `Path(__file__).parent.parent...` chains.
4. **Feature flags that gate real functionality but default off.** List every
   env-var-gated feature (`EVOLVE_EXECUTE`, `RESERVE_EXECUTE`,
   `SETTLEMENT_EXECUTE`, `CREDITS_ENFORCE`, `SWARM_INBOX_ENFORCE`, etc.) found
   in `packages/swarm-core/src/swarm_core/**` and note which ones look
   finished-but-dormant vs. actually incomplete.
5. **Security surface.** Review `packages/swarm-core/src/swarm_core/security/`
   (leakscan, promptguard, audit, authz, identity, inbox, secrets) for gaps:
   places in `apps/*` that call `os.getenv` for secrets instead of
   `secrets.get_secret`, places that build LLM prompts from untrusted content
   without `promptguard.wrap_untrusted`, or privileged actions missing an
   `authz.require` check.
6. **Package data / packaging bugs.** This repo previously shipped with no
   `*.yaml` in `swarm-core`'s package data, which silently fell back to
   hardcoded security defaults in production. Check `packages/*/pyproject.toml`
   or `setup.cfg` for `package_data`/`include_package_data` completeness against
   what's actually read at runtime (yaml/json config files).
7. **Dead code / stub apps.** `apps/x402`, `apps/arb-keeper`, `apps/mcp` are
   marked dormant/stubs in CLAUDE.md — confirm they're genuinely inert (no
   compose entry, no imports elsewhere) or flag if something now depends on them.
8. **Test coverage vs. deployment state.** Distinguish "committed and tested"
   from "committed but never deployed/verified on the box" — this repo has had
   incidents where hundreds of lines sat merged but unverified for weeks. Look
   for recently added modules with no corresponding test file, and flag them
   separately from correctness bugs.

## What to produce

A single markdown report with these sections:

1. **Build/deploy correctness** — build-context or path mismatches found (be
   specific: file + line + what's wrong).
2. **Security findings** — ranked by severity, each with the vulnerable
   code path and a concrete fix.
3. **Duplication / drift** — code that exists in more than one place and
   should be consolidated into `packages/`.
4. **Dead or dormant code** — things safe to delete vs. things that are
   intentionally gated (don't recommend deleting a feature flag without
   checking CLAUDE.md/docs for why it's off).
5. **Top 10 recommended changes**, ordered by (impact × ease), each as:
   - What
   - Where (file/module)
   - Why it matters
   - Rough effort (S/M/L)

## Rules

- Do not propose rewrites or new abstractions for code that already works —
  this project has an explicit "no speculative abstraction" convention.
- Do not recommend renaming or restructuring `apps/` vs `packages/` — that
  split was a deliberate, recent migration (see CLAUDE.md "Monorepo reorg").
- Never invent findings — if something needs a live box to verify (container
  state, deployed version), say so explicitly instead of guessing.
- Treat `/home/umbrel/*` and Railway dashboard settings as external state you
  cannot see from the repo alone; note where a finding depends on that state.
