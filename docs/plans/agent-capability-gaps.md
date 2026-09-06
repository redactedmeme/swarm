# Swarm capability upgrade — the four real gaps

## Context

An article ("19 skills I'd reinstall") proposes a shopping list of agent skills. Its star
counts are fabricated (~224k for a personal skills repo, ~89k, ~73k) and several repos are
unverifiable, so **nothing from it gets installed**. It is useful only as a taxonomy of agent
capabilities, and measured against that taxonomy this swarm already has better versions of
most of it:

| Article idea | Already here |
|---|---|
| claude-mem (session memory) | mem0/Qdrant + `SoulStore` + `ActivityLog` |
| oh-my-hermes (plan → verify) | `swarm_core/engine/{moe_committee,sevenfold_consensus}.py`, BEAM-SCoT |
| SkillClaw (self-improving skills) | `apps/chan/learning_loop.py` + `skills_manager.improve_skill` |
| Minions (task tracking) | task lifecycle exists in `swarm_core/security/inbox.py` |
| Composio (safe app integration) | `swarm_core.security` — authz, egress allowlist, signed inbox |

Four things it names are genuinely missing. This plan builds those four, in dependency order.
Scope excludes new content sources (YouTube/Reddit) by decision.

---

## 1. Hermes cannot browse — dead tool registrations

**Problem.** `apps/hermes/plugins/swarm-manager/__init__.py:20-34` registers only
`inbox_tools`, `railway_tools`, `audit_tools`, `health_tools`, `soul_tools`. Four modules in
the same package define tools that are never wired in:

- `web_tools.py` → `web_fetch`, `web_search`
- `x_tools.py` → `x_post`, `x_reply`, `x_like`, `x_search`, `x_get_bookmarks`, `x_get_timeline`, `x_get_user`
- `skill_tools.py` → `skill_recall`
- `exec_tools.py` → `python_exec`

Hermes is documented in `CLAUDE.md` as the browsing/code-exec agent and currently is neither.

**Change.** Add the four imports and `register(ctx)` calls, but **gate the dangerous two**:

- `web_tools` and `skill_tools` — register unconditionally.
- `x_tools` — register only when the X credentials resolve (`swarm_core.security.secrets.get_secret`,
  not `os.getenv`); posting tools are outward-facing, so gate `x_post`/`x_reply`/`x_like` behind
  `swarm_core.security.authz.require` the way `node_summon` is gated at
  `apps/terminal/tool_dispatch.py:793`.
- `exec_tools` — route through `apps/exec-runner` (the no-secrets/no-network sandbox) rather
  than in-process, and gate on an env flag defaulting off, matching `TOOL_DISPATCH_ALLOW_SPAWN`.

Update `.env.example` and the plugin docstring. Verify against the **running container**, not
the repo — the builder build-context incident showed repo state and container state diverge.

## 2. Readable web extraction (`Defuddle` equivalent)

**Problem.** `web_tools._handle_web_fetch` strips HTML with `re.sub(r"<[^>]+>", ...)` and
truncates at 3000 chars, so nav, cookie banners and script bodies consume most of the budget.
`apps/runtime/tasks/{web_research,deep_research,summarize_url}.py` have the same weakness.

**Change.** Add one shared extractor in swarm-core rather than four copies:

- New `packages/swarm-core/src/swarm_core/web/extract.py` exposing
  `extract(html, url) -> {title, markdown, text, word_count}`.
- Implementation: `trafilatura` (single dep, no browser, handles boilerplate removal and
  markdown output) with a graceful fallback to the current regex path when it returns nothing
  or the dep is absent — the fallback matters because umbrel images should not hard-fail on a
  new wheel.
- Keep the existing `_is_ssrf_blocked` guard in `web_tools.py` and keep piping results through
  `promptguard.wrap_untrusted(source="web:...")` exactly as `apps/runtime/tasks/web_research.py`
  already does. Extraction happens *before* promptguard, never instead of it.
- Repoint `web_tools.py`, the three `apps/runtime/tasks/` modules, and
  `apps/chan/internet_tools.py` result curation at the shared helper. Raise the truncation cap
  once content is clean (3000 → ~8000 chars), but respect the Groq TPM ceiling — full-context
  calls are already unreachable at TPM 8000, so make the cap an argument, not a constant.

Add `trafilatura` to `packages/swarm-core/pyproject.toml` as an optional extra so
self-contained builds (`proxy`, `dashboard`, `webchat`, `website`, `fieldkit`) stay small.

## 3. Critique-and-revise loop + humanizer pass

**Problem.** Nothing post-processes a finished LLM response. `packages/swarm-tg/src/swarm_tg/tg_fmt.py`
only escapes Telegram markup; `apps/smolting/sanitizer.py` only redacts secrets. All style
control is prompt-side (`persona.py`, `apps/chan/dynamic_mode.py`) and therefore drifts.
Separately there is no generic retry-with-quality-threshold — iteration exists only at the
committee timescale and the skill-evolution timescale.

**Change.** One new module, two entry points, both opt-in:

New `packages/swarm-core/src/swarm_core/refine/` containing:

- `loop.py` — `refine(produce, critique, *, max_rounds=3, stop_when) -> result`. A generic
  iterate-measure-keep-if-better loop with an explicit stop rule and a hard round cap, so it
  cannot become an unbounded token sink. Model calls go through the proxy auto-router
  (`model="auto"`) like every other LLM call in the repo, never direct.
- `humanize.py` — `humanize(text, *, voice) -> text`. A rewrite pass that strips the known AI
  tells (uniform tricolons, "it's not just X, it's Y", inflated adjectives, sign-offs) while
  asserting facts are unchanged. Must return the original on any failure — a formatting pass
  must never be able to drop a message.

Wiring, minimal and reversible:
- Called from `tg_fmt.from_llm`'s callers, **not** from `tg_fmt` itself — formatting and
  rewriting are different concerns and `tg_fmt` is shared by four bots.
- Gate per-service behind an env flag (`SWARM_HUMANIZE=false` default) so it can be enabled on
  one bot and compared before rollout.
- Run `leakscan.scan` on the rewritten output before it leaves — a rewrite pass is a new place
  for a secret to survive redaction.

## 4. Task board in Field Kit

**Problem.** `swarm_core/security/inbox.py` already has the full lifecycle —
`STATUS_PENDING → STATUS_PROCESSING → STATUS_DONE|STATUS_ERROR`, with `write_message:282`,
`read_pending:382`, `read_results:401`, `claim_message:458`, `complete_message:481` — and
nothing renders it. Parallel jobs are invisible.

**The pipeline already exists end to end**, which is why this is small:
`apps/status/app.py:api_swarm` → `_push_once:513` POSTs to → `apps/website/serve.py:232`
`/api/swarm/publish` → served at `/api/swarm` → `apps/fieldkit/src/lib/swarm.ts` fetches it.

Four edits along that path:

1. **`apps/status/app.py`** — add a `_tasks(redis_client)` reader beside `_observe:256` /
   `_treasury:329` / `_settlements:385`, returning counts by status per agent plus the N most
   recent in-flight items (id, verb, from, to, status, age bucket). Add it to the `api_swarm`
   payload. Reuse `bucket()` for ages; never emit raw payload bodies — they contain task
   content.
2. **`apps/website/serve.py`** — extend `_project:92`. That function is the public disclosure
   boundary and is deliberately a whitelist, so add a `_clean_tasks(raw)` in the style of
   `_clean_offers` / `_clean_treasury`: coerce and clamp counts, cap the item list, truncate
   every string field. **No task payload bodies cross this line** — ids, verbs, agent names and
   statuses only.
3. **`apps/fieldkit/src/lib/swarm.ts`** — add a `TaskSnapshot` type and parse the new block,
   tolerating its absence exactly as `MeshAgent` already tolerates two payload shapes. Add
   `useTasks()` to `src/lib/queries.ts` next to `useSwarm`/`useToken`.
4. **`apps/fieldkit/src/routes/tasks.tsx`** — new route, columns pending / processing / done /
   error, matching the existing route style in `agents.tsx` and `field.tsx`.

**Prerequisite, and it is a real one:** `apps/status` is listed as *not deployed* in
`CLAUDE.md`. The board shows nothing until status runs on umbrel with `STATUS_PUSH_URL` and
`STATUS_PUSH_TOKEN` set against the website. That deploy is step 4.0, before any UI work, and
it is the step most likely to be where this stalls.

---

## Order of work

1. Gap 1 (Hermes registration) — self-contained, immediate capability restored.
2. Gap 2 (extractor) — improves gap 1 and three runtime tasks at once.
3. Gap 4.0 (deploy `apps/status`) — unblocks the board; do it early since it is the risky step.
4. Gap 4.1–4.4 (board).
5. Gap 3 (refine/humanize) — last, because it is the most subjective and easiest to defer.

## Verification

- **Gap 1:** `docker exec` into the running hermes container, confirm the tool list includes
  `web_fetch`/`web_search`; send a SwarmInbox task exercising `web_fetch` and read the result
  via `read_results`. Confirm `x_post` refuses without the authz capability.
- **Gap 2:** unit test in `packages/swarm-core/tests/` comparing extracted markdown against the
  regex fallback on a saved fixture page — assert word count rises and nav text is gone. Assert
  the fallback path returns non-empty when `trafilatura` is uninstalled.
- **Gap 3:** golden-file test that `humanize` preserves every number and proper noun in the
  input; test that an exception inside the rewrite returns the original string verbatim; test
  `refine` stops at `max_rounds` when `stop_when` never fires.
- **Gap 4:** curl `/api/swarm` on the umbrel box and on `redacted.meme`, diff the two — the
  public one must contain strictly fewer fields. Then `npm run build && vite preview` in
  `apps/fieldkit` (per prior findings `npm run dev` is flaky and the Z: share cannot build) and
  load `/tasks`.
- **Repo-wide:** `python scripts/secret_scan.py --staged` passes before commit; the pre-commit
  hook covers this where `hooksPath` is configured.

## Explicitly out of scope

YouTube transcripts, Reddit ingestion, real-browser automation (`Browser Harness`), video
production (`OpenMontage`), and the offensive-security skill library. The browser and security
items in particular would need their own threat review against the existing egress allowlist
before they are worth planning.
