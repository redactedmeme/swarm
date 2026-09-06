# Swarm capability upgrade — Grok Bot parity, built natively

**Status:** plan / handoff. Nothing here is implemented yet.
**Audience:** a coding agent working in `Z:\swarm-main` with no prior session context.
**Read first:** `CLAUDE.md` at the repo root — it is the authority on layout, build contexts,
and the security module. This document assumes it.

---

## 1. Context

Two inputs produced this plan.

**(a) An article** listing "19 skills I'd reinstall" on a fresh agent. Its star counts are
fabricated (~224k for a personal skills repo, ~89k, ~73k) and several named repos are
unverifiable. **Install nothing from it.** It is useful only as a taxonomy of agent
capabilities, and against that taxonomy this swarm already has better versions of most entries:

| Article idea | Already in this repo |
|---|---|
| claude-mem (memory across sessions) | mem0/Qdrant (`plugins/mem0-memory/mem0_wrapper.py`), `SoulStore`, `ActivityLog` |
| oh-my-hermes (plan → consensus → verify) | `swarm_core/engine/{moe_committee,sevenfold_consensus,negotiation_engine}.py`, BEAM-SCoT |
| SkillClaw (self-improving skills) | `apps/chan/learning_loop.py` + `apps/chan/skills_manager.py` (`improve_skill`, `should_improve`) |
| Composio (safe app integration) | `swarm_core.security` — `authz`, `egress.yaml`, signed `inbox` |
| Minions (task board) | task lifecycle exists in `swarm_core/security/inbox.py`; nothing renders it |

**(b) Grok Bot**, whose capability set we want to **re-create natively — not integrate**. No
dependency on xAI's product, no data leaving the swarm's own boxes. The properties worth
reproducing, and where each stands here:

| Grok Bot property | Status in this swarm |
|---|---|
| A persistent computer per bot — browser, filesystem, terminal | **Missing.** `apps/exec-runner` is a *deliberately powerless* ephemeral sandbox: no network, no secrets, unix socket only |
| Real browser / computer use on sites without an API | **Missing.** Web access is `requests` plus a regex tag-stripper |
| Bots message each other and hand off ownership | **Half.** `swarm_core/security/inbox.py` has signed messaging and a full task lifecycle, but no ownership-transfer verb |
| Durable named identity, memory, preferences | **Done.** SoulStore + mem0 + ActivityLog + character JSON |
| Learns a workflow from demonstration, re-runs it as a routine | **Half.** `skills_manager` + `learning_loop` distil skills; `swarm_scheduler` + `AgentRuntime.add_periodic` run them; the demonstration→routine path does not exist |
| Comes back only when approval is needed | **Half.** `security/caps.yaml` already has `requires_approval` + `approval_ttl: 900`; nothing surfaces a pending approval to a human |
| One shared computer across all bots | **Deliberately rejected.** See §11 |

The gap is narrower than it looks. Most of the intelligence exists; what is missing is a
**place for an agent to do durable work** and a **surface for a human to watch and approve it**.
That is what this plan builds.

---

## 2. Ground truth — verified facts you can rely on

These were confirmed by reading the code. Do not re-derive them, but do re-check anything you
are about to change.

- **Hermes plugin loader** — `apps/hermes/plugins/swarm-manager/__init__.py:20-34`. `register(ctx)`
  wires only `inbox_tools`, `railway_tools`, `audit_tools`, `health_tools`, `soul_tools`.
  Tool registration API is `ctx.register_tool(name=, toolset=, schema=, handler=)`.
- **Four tool modules exist but are never registered**, in that same directory: `web_tools.py`
  (`web_fetch`, `web_search`), `x_tools.py` (`x_post`, `x_reply`, `x_like`, `x_search`,
  `x_get_bookmarks`, `x_get_timeline`, `x_get_user`), `skill_tools.py` (`skill_recall`),
  `exec_tools.py` (`python_exec`). **Hermes today cannot browse or execute code**, despite
  `CLAUDE.md` describing it as the agent that does both.
- **`web_tools._handle_web_fetch`** strips HTML with `re.sub(r"<[^>]+>", ...)` and truncates at
  3000 chars. It does have a working SSRF guard (`_is_ssrf_blocked` — blocks
  localhost/RFC1918/`.internal`/metadata plus a `172.(1[6-9]|2\d|3[01])\.` regex). **Keep that guard.**
- **The richest web layer is `apps/chan/internet_tools.py`** — Tavily → Brave → DuckDuckGo
  fallback, domain allow/deny (`WEBSEARCH_ALLOW_DOMAINS` / `WEBSEARCH_DENY_DOMAINS` /
  `WEBSEARCH_BLOCK_TERMS`), result curation and dedup. Reuse it; do not write a fourth search client.
- **`apps/runtime/tasks/{web_research,deep_research,summarize_url}.py`** already pipe fetched
  pages through `promptguard.wrap_untrusted(source="web:search-results")` and drop flagged
  pages. This is the correct pattern — copy it, never bypass it.
- **No HTML→markdown/readability library anywhere.** No trafilatura, readability, BeautifulSoup
  or html2text in the tree.
- **Task lifecycle** lives in `packages/swarm-core/src/swarm_core/security/inbox.py`:
  `STATUS_PENDING → STATUS_PROCESSING → STATUS_DONE|STATUS_ERROR`; functions `write_message:282`,
  `read_pending:382`, `read_results:401`, `claim_message:458`, `complete_message:481`. Ed25519
  signing (`_sign`, `verify_doc`), route table (`_route_ok`), Redis backend with file fallback.
  `apps/{hermes,chan,smolting,builder}/swarm_inbox.py` are re-export shims over it.
- **The public status pipeline already exists end to end** — this is why the board in §9 is small:
  `apps/status/app.py:api_swarm` → `_push_once:513` POSTs to → `apps/website/serve.py:232`
  `/api/swarm/publish` → served at `/api/swarm` → `apps/fieldkit/src/lib/swarm.ts` fetches it.
  The disclosure boundary is `apps/website/serve.py:_project:92`, a deliberate field whitelist
  with `_clean_offers` / `_clean_treasury` helpers alongside it.
- **`apps/status` is not deployed** (`CLAUDE.md` service table). The board renders nothing until
  it runs on umbrel with `STATUS_PUSH_URL` + `STATUS_PUSH_TOKEN`.
- **`apps/runtime/main.py` is the existing external HTTP door**: FastAPI, `verify_token` from
  `apps/runtime/auth.py`, guarding `/task`, `/task/async`, `/task/{id}`, `/scheduled/latest/{name}`.
  **But `/announce:354` is unauthenticated** (any reachable caller can forge a heartbeat), and
  `/messages/{node_id}:370` + `/message/{target}:376` are **stubs that return empty and discard**.
  Fixed in §8.
- **Approval primitives exist** — `packages/swarm-core/src/swarm_core/security/caps.yaml`:
  `approval_ttl: 900`, `requires_approval: [funds.transfer, infra.deploy, secret.read,
  docker.control, inbox.broadcast_admin]`, and a per-agent `grants` map. `code.exec` is
  deliberately *not* approval-gated because exec-runner is the containment.
- **`exec-runner` contract** — `apps/exec-runner/app.py`: `POST /run {"code","timeout"}` over a
  unix socket at `EXEC_RUNNER_SOCK`, bearer `EXEC_RUNNER_TOKEN` compared with
  `hmac.compare_digest`, `network_mode: none`, no `env_file`, 512KB body cap.
- **Output post-processing does not exist.** `packages/swarm-tg/src/swarm_tg/tg_fmt.py` only
  escapes Telegram markup (`from_llm`, `_llm_to_html`, `_llm_to_md2`); `apps/smolting/sanitizer.py`
  only redacts secrets. All style control is prompt-side (`swarm_agent_base/persona.py`,
  `apps/chan/dynamic_mode.py`) and therefore drifts.
- **No generic retry-with-quality loop.** Retry appears 16 times across 8 files in `packages/`,
  mostly `ollama_client.py`. No `tenacity` / `backoff` dependency.
- **Field Kit** is the only Node app — React + TanStack Router, deploys to Vercel with root
  `apps/fieldkit`. Routes: `index`, `agents`, `agents_.$id`, `chamber`, `field`, `pattern`,
  `ticker`. Data layer `src/lib/swarm.ts` + `src/lib/queries.ts` (`useSwarm`, `useToken`). It
  already tolerates two payload shapes (`MeshAgent` accepts `name` or `label`) — match that
  defensiveness. **`npm run dev` is flaky and the `Z:` share cannot build**; use
  `npm run build && npx vite preview`.

---

## 3. Workstream A — restore Hermes's dead tools

**Why first:** self-contained, and it restores a documented capability that is currently absent.
Every later workstream assumes Hermes can act.

Edit `apps/hermes/plugins/swarm-manager/__init__.py`. Import and register the four modules — but
not uniformly, since they carry very different blast radii:

- `web_tools`, `skill_tools` — register unconditionally.
- `x_tools` — register only when the X credentials actually resolve via
  `swarm_core.security.secrets.get_secret` (**not** `os.getenv` — see `CLAUDE.md`). The
  outward-facing three (`x_post`, `x_reply`, `x_like`) must call
  `swarm_core.security.authz.require(agent, ...)` in the handler before acting. The read-only
  ones (`x_search`, `x_get_timeline`, `x_get_user`, `x_get_bookmarks`) need no gate.
- `exec_tools` — do **not** execute in-process. Route `python_exec` at the `apps/exec-runner`
  unix socket using the contract in §2. Gate registration behind a new env flag defaulting off,
  in the style of `TOOL_DISPATCH_ALLOW_SPAWN` (see `apps/terminal/tool_dispatch.py:793` for the
  gate pattern and `.env.example:113` for the default).

Also: `caps.yaml` already grants hermes `[code.exec, infra.deploy, secret.read, web.fetch,
inbox.send, llm.call]`. Adding X posting means adding a capability — call it `social.post` — to
`requires_approval` and to hermes's grant list. Do not skip this. An unapproved posting tool on
an autonomous agent is how accounts get taken over.

Update the module docstring and `.env.example`. **Verify against the running container, not the
repo** — this repo has a documented history (`CLAUDE.md`, "Build contexts") of container state
and repo state diverging silently for days.

## 4. Workstream B — readable web extraction

**Problem.** Four call sites independently do naive HTML stripping, so nav chrome, cookie
banners and inline script bodies consume most of a small context budget.

**Build one shared extractor**, not a fourth copy:

`packages/swarm-core/src/swarm_core/web/extract.py`

```
extract(html: str, url: str) -> {"title", "markdown", "text", "word_count"}
```

- Implement with `trafilatura` — one dependency, no browser, handles boilerplate removal and
  emits markdown directly.
- **Fall back to the current regex path** when trafilatura is absent or returns nothing. This is
  not optional politeness: umbrel images must not hard-fail on a missing wheel.
- Add `trafilatura` as an **optional extra** in `packages/swarm-core/pyproject.toml` so the
  self-contained builds (`proxy`, `dashboard`, `webchat`, `website`, `fieldkit`) stay small.

Then repoint the call sites: `apps/hermes/plugins/swarm-manager/web_tools.py`, the three
`apps/runtime/tasks/*.py` modules, and the curation step in `apps/chan/internet_tools.py`.

Two invariants that must survive the refactor:

1. **Extraction happens before `promptguard.wrap_untrusted`, never instead of it.** Cleaner text
   is still untrusted text; a well-formatted injection is still an injection.
2. The SSRF guard stays in front of every fetch.

Raise the truncation cap now that content is clean (3000 → ~8000), but make it a **parameter, not
a constant** — the Groq TPM ceiling (8000 TPM against ~8900-token prompts) already makes
full-context calls unreachable on some routes, so callers must be able to ask for less.

## 5. Workstream C — the persistent agent workspace ("a computer of its own")

This is the core of Grok Bot parity and the largest piece of new work.

**What it is.** A long-lived per-agent container with a real filesystem, a real shell and a real
browser, that survives across tasks so context compounds instead of resetting.

**What it is not.** It is *not* an expansion of `apps/exec-runner`. That service's entire value
is that it is powerless — no network, no secrets, no persistence. Weakening it would destroy an
existing security control. Build a **second, separate** service with a different threat model and
leave exec-runner exactly as it is.

New app: `apps/workspace/`.

- **Build context:** repo root (it imports `swarm_core`) — see the `CLAUDE.md` build-context rule,
  and check `infra/umbrel/swarm-infra-docker-compose.yml` when wiring it. Getting this wrong is
  described in `CLAUDE.md` as the repo's classic outage.
- **One container per agent, not one shared.** See §11.
- **Persistent volume** at `/workspace`, resolved through `swarm_core.paths` (`data_dir()`) —
  never by counting `__file__` parents.
- **HTTP API over a unix socket**, mirroring exec-runner's shape so callers already know it:
  - `POST /fs/read`, `POST /fs/write`, `POST /fs/list` — scoped to `/workspace`, path traversal rejected.
  - `POST /shell` — run a command; return stdout, stderr and exit code; hard timeout; output cap.
  - `POST /browser/*` — see §6.
  - `GET /session` — what this workspace currently holds (open pages, recent commands, disk use).
- **Auth:** bearer token via `secrets.get_secret`, compared with `hmac.compare_digest`, same as
  exec-runner.
- **Egress:** allowlisted through the existing `apps/swarm-egress` + `security/egress.yaml`. A
  workspace with a browser and unrestricted egress is an exfiltration path.
- **Audit:** every `/shell` and `/browser` action through `swarm_core.security.audit.record`, with
  the calling agent as actor. Every filesystem write too.
- **Capabilities:** add `workspace.shell` and `workspace.browse` to `caps.yaml`. `workspace.shell`
  is the dangerous one — it has network *and* persistence, which is exactly what `code.exec` was
  allowed to skip approval for. **Put `workspace.shell` under `requires_approval`.**

Expose it to agents as tools (`workspace_read`, `workspace_write`, `workspace_shell`) via the same
`ctx.register_tool` path used in §3.

## 6. Workstream D — real browser control

Inside the `apps/workspace` container, add Playwright (Chromium, headless) as the browser. Prefer
it over raw CDP: it ships its own browser build, has stable selector and waiting semantics, and
does not require attaching to a human's real browser — which the source article itself flags as a
genuine risk.

Endpoints on the workspace service:

- `POST /browser/goto {url}` — SSRF-guarded with the **same** `_is_ssrf_blocked` logic. Lift that
  function out of `web_tools.py` into `swarm_core/web/` so there is one copy.
- `POST /browser/read` — returns the page through the §4 extractor, then through
  `promptguard.wrap_untrusted(source="browser:<domain>")`.
- `POST /browser/click`, `/browser/type`, `/browser/screenshot`.
- `POST /browser/session` — named, persistent browser profiles on the volume, so a login done once
  survives. **One profile directory per agent.**

Hard rules, encoded in the handler and not merely documented:

- The browser profile directory is per-agent and never shared.
- Never auto-submit a form reached by following a link that came from fetched page content.
- Credentials come from `secrets.get_secret` at the moment of use and are never written into page
  content, logs, screenshots or audit records.
- Screenshots go to the volume and are referenced by id; they never travel back through an LLM
  prompt unless a caller explicitly asks.

## 7. Workstream E — routines from demonstration

Grok Bot learns a path once and re-runs it. The pieces are all here; the wiring is not.

- **Capture:** the workspace service (§5) already audits every shell and browser action with an
  actor and timestamp. Add a `trace_id` so one run is a single retrievable sequence.
- **Distil:** feed a completed trace to `apps/chan/learning_loop.py`, which already converts
  trajectories into skill documents via `skills_manager.create_skill`. Skills are markdown with
  `## Description / ## When to Use / ## Steps / ## Example` (see `skills/README.md`; runtime-
  generated skills live in `/data/skills/`, committed seeds in `skills/`).
- **Re-run:** register the distilled skill as a periodic task via
  `AgentRuntime.add_periodic(fn, interval, jitter, name)`
  (`packages/swarm-agent-base/src/swarm_agent_base/runtime.py`) or as a `SwarmTask` in
  `swarm_core/swarm_scheduler.py`, which already has health-gated execution via `read_kernel_health()`.
- **Improve:** `skills_manager.should_improve` / `improve_skill` already version and refine a skill
  from usage. Leave that path alone; just make sure traces reach it.

The new code here is thin — a trace recorder and a `routine_promote(trace_id, schedule)` verb.
Resist rebuilding the skill store.

## 8. Workstream F — bot-to-bot handoff and surfaced approvals

Grok Bot's "coordinate independently, come back only for approval" is two features. Both are
half-built here.

**(a) Handoff.** `inbox.py` can send a message and complete a task, but there is no way to transfer
*ownership* of an in-flight task. Add `reassign_message(msg_id, to_agent, reason)`: it moves a
`STATUS_PROCESSING` item back to `STATUS_PENDING` addressed to a new agent, appends to a
`handoff_chain` list on the message, re-signs and audits. The chain matters — without it, a task
that bounces between three agents is unattributable.

Enforce the existing route table (`_route_ok`) on the *new* destination, and cap chain depth
(suggest 5) so two agents cannot ping-pong a task forever.

**(b) Fix the mesh stubs.** `apps/runtime/main.py:370,376` — `/messages/{node_id}` returns
`{"messages": []}` and `/message/{target}` logs and discards. Back both with the real
`swarm_core.security.inbox`. And **add `verify_token` to `/announce:354`**, which is currently
unauthenticated and lets any reachable caller forge an agent heartbeat into Redis — which
`apps/status` then republishes to the public site.

**(c) Surface approvals.** `caps.yaml` has `requires_approval` and a 900s `approval_ttl`, but
nothing tells a human an approval is waiting. Add a pending-approval queue in Redis — **not
in-process**; note `_pending_tweets` at `apps/terminal/tool_dispatch.py:28` is a dict that dies on
restart, and do not repeat that. Each entry: requesting agent, capability, a redacted summary of
the action, expiry. Surface it in two places — a Telegram admin DM, and the board in §9. Approving
is an explicit human action; **expiry denies**.

## 9. Workstream G — the task board ("keep you updated")

Autonomous agents that hand off work are useless if you cannot see what they are doing. The
pipeline exists (§2), so this is four small edits along it.

1. **`apps/status/app.py`** — add `_tasks(redis_client)` beside the existing `_observe:256` /
   `_treasury:329` / `_settlements:385` readers. Return per-agent counts by status, plus the N most
   recent in-flight items: id, verb, from, to, status, age bucket (reuse the existing `bucket()`
   helper), and any pending approvals from §8c. **Never emit message payload bodies** — they
   contain task content and user data. Add the block to the `api_swarm` payload.
2. **`apps/website/serve.py`** — extend `_project:92`. This function is the public disclosure
   boundary and is intentionally a whitelist. Add `_clean_tasks(raw)` in the style of
   `_clean_offers` / `_clean_treasury`: coerce and clamp every count, cap the item list length,
   truncate every string. Ids, verbs, agent names, statuses and ages cross; nothing else.
3. **`apps/fieldkit/src/lib/swarm.ts`** — add a `TaskSnapshot` type, parse the new block, tolerate
   its absence exactly as `MeshAgent` tolerates two shapes today. Add `useTasks()` to
   `src/lib/queries.ts` next to `useSwarm` / `useToken`.
4. **`apps/fieldkit/src/routes/tasks.tsx`** — new route. Columns pending / processing / done /
   error, plus a pending-approvals strip. Match the existing style in `agents.tsx` / `field.tsx`.

**Prerequisite, and the likeliest place to stall:** `apps/status` is not deployed. Deploy it on
umbrel with `STATUS_PUSH_URL` and `STATUS_PUSH_TOKEN` pointing at the website *before* starting
the UI work. Prior context: exposing the umbrel box directly was declined, so the push-to-website
path is the supported one — do not replace it with a public tunnel.

## 10. Workstream H — refine loop and humanizer

Nothing post-processes a finished response, and there is no iterate-until-better primitive.

New `packages/swarm-core/src/swarm_core/refine/`:

- `loop.py` — `refine(produce, critique, *, max_rounds=3, stop_when) -> result`. Generic
  iterate → measure → keep-if-better, with an explicit stop rule and a hard round cap so it cannot
  become an unbounded token sink. All model calls go through the redacted-proxy auto-router
  (`model="auto"`), never a provider directly — that is the repo-wide convention.
- `humanize.py` — `humanize(text, *, voice) -> text`. Strips the known AI tells (uniform tricolons,
  "it's not just X, it's Y", inflated adjectives, trailing sign-offs) while asserting facts are
  unchanged. **Must return the original on any failure** — a cosmetic pass must never be able to
  drop or mangle a message.

Wiring, minimal and reversible:

- Call from `tg_fmt.from_llm`'s *callers*, not from `tg_fmt` itself. Formatting and rewriting are
  different concerns and `tg_fmt` is shared by four bots.
- Gate per-service behind `SWARM_HUMANIZE` (default `false`) so one bot can be enabled and compared
  before rollout.
- Run `leakscan.scan` on the rewritten output before it leaves. A rewrite pass is a new place for a
  secret to reappear after redaction.

---

## 11. Security — the deliberate divergences from Grok Bot

Three of Grok Bot's design choices are wrong for this swarm. Implement the alternative, and do not
"simplify" toward the original later.

**One computer per agent, not one shared computer.** Grok Bot shares a single VM across all of a
user's bots: shared files, shared browser sessions, shared logins, explicitly no security boundary
between bots. That is defensible when every bot is driven by one attentive human. It is not
defensible here, where agents run unattended, some hold treasury capability (`settler` and
`mandalaasettler` hold `funds.transfer`), and this swarm has already had a bot token compromised
via a public repo. A shared workspace would mean a prompt injection landing in the lowest-privilege
agent's browser gets the highest-privilege agent's session cookies. **Per-agent volume, per-agent
browser profile, per-agent token.** Sharing, if ever needed, goes through an explicit
`/workspace/shared` mount that is opt-in per agent and audited.

**Approval expiry denies.** `approval_ttl: 900` already exists. Make the timeout path a denial,
never a default-allow, and never let an agent re-request in a loop to wear down a human.

**Untrusted content stays fenced end to end.** Everything a browser or fetch returns goes through
`promptguard.wrap_untrusted` before it reaches a prompt — including content the agent itself chose
to navigate to, including content that claims to be an instruction from an operator. Instructions
come from the operator channel only. This is the control that makes an autonomous browser survivable.

Carry forward the standing rules too: never commit real credentials (a bot token in a test fixture
on the public repo is exactly how the builder bot was taken over); never `git pull` on the umbrel
box (`/home/umbrel/swarm` is a separate history — deploy by syncing files); `redacted-chan` runs
from a non-git standalone copy at `/home/umbrel/redacted-chan`; Railway `rootDirectory` /
`startCommand` live in the dashboard and override `railway.toml` where they disagree.

---

## 12. Order of work

Dependency-ordered. A, B and G.0 can run in parallel; nothing else should.

1. **A** — Hermes registrations. Self-contained, restores a documented capability.
2. **B** — shared extractor. Improves A and three runtime tasks at once.
3. **G.0** — deploy `apps/status` + push env. Do it early: it is the riskiest step and it blocks
   the only surface that makes the rest observable.
4. **F.b** — fix the `/announce` auth hole and the two mesh stubs. Small, and a live exposure.
5. **C** — the workspace service. The big one. Ship fs + shell first, browser separately.
6. **D** — browser control inside the workspace.
7. **F.a + F.c** — handoff verb and approval queue.
8. **G.1–G.4** — the board, now with real task and approval data to show.
9. **E** — routines from traces.
10. **H** — refine / humanize. Last: most subjective, easiest to defer, zero dependencies.

---

## 13. Verification

Do not report a step done without the corresponding check.

- **A:** `docker exec` into the *running* hermes container and confirm `web_fetch` / `web_search`
  appear in its tool list. Send a SwarmInbox task exercising `web_fetch`; read the result via
  `read_results`. Confirm `x_post` refuses without an approval token, and that the refusal is audited.
- **B:** unit test in `packages/swarm-core/tests/` against a saved fixture page: assert the extracted
  word count rises versus the regex path and that known nav strings are gone. Separately assert the
  fallback returns non-empty when `trafilatura` is not importable.
- **C / D:** write a file, read it back from a *new* request, confirm persistence across a container
  restart. Confirm `/shell` cannot reach a host outside `egress.yaml`. Confirm a path-traversal write
  outside `/workspace` is rejected. Confirm `workspace.shell` without approval is denied. Confirm
  agent A cannot read agent B's browser profile.
- **E:** run a two-step browser task, promote the trace to a routine, confirm the scheduler fires it
  and the skill document contains the real steps.
- **F:** reassign a task and assert the `handoff_chain` records both hops and the signature still
  verifies. Assert an unsigned `/announce` is now rejected. Assert an approval expires to *denied*
  after `approval_ttl`.
- **G:** `curl /api/swarm` on the umbrel box and on `redacted.meme`, then diff them — the public one
  must contain **strictly fewer** fields, and no message bodies. Then in `apps/fieldkit`:
  `npm run build && npx vite preview`, and load `/tasks`. (`npm run dev` is flaky; the `Z:` share
  cannot build.)
- **H:** golden-file test that `humanize` preserves every number and proper noun; test that an
  exception inside the rewrite returns the input verbatim; test `refine` halts at `max_rounds` when
  `stop_when` never fires.
- **Repo-wide, before every commit:** `python scripts/secret_scan.py --staged`. The pre-commit hook
  covers this where `core.hooksPath` is configured, but it is opt-in per clone — run it explicitly.

---

## 14. Out of scope

YouTube transcripts, Reddit ingestion, video production, and the offensive-security skill library
from the source article. Note that once §5 and §6 land, YouTube and Reddit become small additions
on top of the workspace browser rather than separate integrations — which is itself the argument
for building the workspace instead of a pile of per-site tools.
