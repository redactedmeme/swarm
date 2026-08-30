# Swarm Project Consolidation — Summary

**Date:** 2026-07-29
**Location:** `\\${ZK_NODE_HOST}\shared\swarm-main\` (zk-node, SSD-backed — `/propagated-mount/umbrel-backup/shared`)
**Why this exists:** the swarm project's real source was scattered across an untracked local working directory, a stale 2-month-old git branch, and several live Railway containers, with no single place holding a complete, verified, current copy. This doc explains what's here now, where it came from, and what still needs a human decision.

---

## 1. What's in this folder

A consolidated snapshot of the **REDACTED swarm** project — the AI agent ecosystem (RedactedBuilder, redacted-chan, smolting, Hermes, the dashboard, x402, etc.). It does **not** include the guthix/sgxUSD financial-keeper codebase (`manifest-keeper`, `peg-keeper`, `price-oracle`, `strategies`, `nav-keeper`) — that's a separate business tracked only in the private `guthix-pkm` repo and deliberately excluded here. `arb-keeper` (live-trading bot) was also excluded — see §4.

**Source of truth used:** the live `redacted-website` Railway service turned out to be deploying the **entire current monorepo**, not just the marketing site. That made it the most authoritative source available — more current than any git branch, and reachable for services (`smolting-telegram-bot`, `hermes-bot`, `redacted-chan-bot`, `redacteddegen-service`) that aren't directly SSH-reachable on their own.

**Verification:** every file here was diffed by MD5 hash against that live container. Result: 788 files in common, only 1 difference (`.claude/launch.json`, local tooling config — not project code), zero real project files missing. This is as close to "what's actually running in production" as a static snapshot can be.

---

## 2. Known drift that got fixed during consolidation

The first pass at this backup was sourced from the `refactor/consolidate` git branch (last touched 2026-05-28) and turned out to be significantly stale in places once checked against the live container:

| Directory | Files that had drifted |
|---|---|
| `redacted-chan-bot` | 59 of ~110 |
| `x402.redacted.ai` | 20 of 22 |
| `smolting-telegram-bot` | 17 of 112 |
| `hermes-bot` | 9 of 43 |
| `redactedbuilder-telegram-bot` | 3 of 10 |

All of these were re-synced from the live container and are now current as of this consolidation.

---

## 3. `services/` vs the old top-level directories — which is canonical

`services/telegram`, `services/x402`, `services/web`, and `services/mcp` looked like a newer parallel restructuring at first glance. They're not — they're a mix of git-recovery debris and one real migration. Resolved as follows:

| Old path | `services/` equivalent | Canonical | Why |
|---|---|---|---|
| `smolting-telegram-bot` (112 files, 151KB `main.py`) | `services/telegram` (16 files, 17KB `main.py`) | **old dir** | `services/telegram` was reintroduced by a commit literally titled *"restore: recover all files lost from remote main"* and never touched again. Much less developed, static since that recovery. |
| `x402.redacted.ai` (22 files) | `services/x402` (20 files) | **old dir** | Same recovery-commit origin; `x402.redacted.ai` kept getting real feature work afterward. |
| `web_ui` (426-line `app.py`) | `services/web` (851-line `app.py`) | **`services/web`** (opposite direction!) | `services/web`'s own commit message says *"Merge web_ui features into services/web hardened terminal"* — it's the successor, not a fork. `web_ui` only reappeared via the same recovery commit. |
| — | `services/mcp` (just a lone `package.json`) | n/a | No duplicate exists anywhere to compare against — it's an unstarted stub, not a stale fork. Left in place. |

**Action taken:** `services/telegram`, `services/x402`, and `web_ui` were moved to `_archive/` (not deleted — still there if anyone needs to check them) and removed from the active tree so nobody builds on the dead branch by mistake. `smolting-telegram-bot`, `x402.redacted.ai`, and `services/web` are the ones to build on going forward.

---

## 4. Security incidents handled this session (context, not action items)

Two live credential leaks were found and fixed on the **public** `redactedmeme/swarm` GitHub repo during this work — noted here so the team knows the history, not because anything further is needed on the shared-drive side:

- A live Railway API token was committed in `arb-keeper/UPGRADE_NOTES.md`. `arb-keeper` was extracted to its own private repo (`redactedmeme/arb-keeper`) and removed from the public repo. **The exposed token itself still needs to be rotated in the Railway dashboard if that hasn't happened yet** — removing it from git does not invalidate it.
- A live Moltbook API key + account-claim URL was committed in `hermes-bot/moltbook_reg.json` and echoed into `docs/BUILD_PLAN_v2.8.md`. Scrubbed from the public repo's entire history (all branches + tags, force-pushed, verified via fresh clone). The Moltbook agent (`patternbluelabs`) was confirmed still unclaimed and not hijacked — worth completing the claim process to lock in ownership.
- 5 stale/dead branches were deleted from the public repo (3 already merged, 2 abandoned with no open PR); 1 branch with a genuinely open PR was kept and cleaned.

`arb-keeper` is **not** included in this shared-drive backup — it lives in its own private repo now, separate from this consolidated swarm snapshot.

---

## 5. Open items / needs a human decision

**Resolved during the 2026-07-29 consolidation-cleanup pass:**

- ✅ **`redactedbuilder/` extracted** — moved out to its own repo seed at `Z:\redactedbuilder\` (git-initialized, local commit made) and **removed from this snapshot**, matching the `arb-keeper` isolation. The 5 files were hash-verified identical before removal. See that folder's `README.md` for the `gh repo create` runbook.
- ✅ **git initialized** in `swarm-main` with an initial commit of the consolidated snapshot. No remote is configured and nothing was pushed.
- ✅ **`fs/` caveat documented** — added `fs/README.md` marking it as a 2026-07-29 historical snapshot, not live state.

**Still needs a human (external systems — cannot be done from the shared drive):**

- [ ] **Rotate the exposed Railway API token** that was committed in `arb-keeper/UPGRADE_NOTES.md` — do this in the Railway dashboard. Removing it from git does **not** invalidate it (§4).
- [ ] **Complete the Moltbook account claim** for `patternbluelabs` to lock in ownership (§4). Confirmed still unclaimed/not hijacked at consolidation time.
- [ ] **Create + push the private `redactedbuilder` repo** from the `Z:\redactedbuilder\` seed (`gh repo create redactedmeme/redactedbuilder --private --source=. --push`).

**Prior notes (unchanged):**

- **`fs/`** in this backup (106 files) is runtime state (memories, logs, swarm message history) from the git branch snapshot, not from the live container — it's historical data, not current live state. Don't treat it as authoritative for anything time-sensitive.
- **`dashboard-next`** — confirmed to be the live app behind the "DASHBOARD" link on redacted.meme (a Solana token volume tracker). Source is complete and verified against the deployed Railway container.
- This snapshot reflects a point-in-time pull (2026-07-29). It will drift from production again as soon as anyone deploys a change without updating this copy — there's no automated sync in place.

---

## 6. Where things actually run (for reference)

- Railway project `1afabeef-fb14-47ec-974f-26b92158fc28`: `redactedbuilder-bot`, `redacted-proxy`, `redactedbuilder`, `redacted-website`, `redacted-webchat`, `redacted-terminal`, `redacted-dashboard`, `guthix-web`, `REDACTED-AI`.
- A separate Railway project (referenced in older notes as "distinguished-wonder") runs `smolting-telegram-bot`, `hermes-bot`, `redacted-chan-bot`, `redacteddegen-service` — not directly reachable from the CLI token used this session, which is why the `redacted-website` monorepo pull was needed to verify those services at all.
- `redacted-proxy` now routes OpenRouter (`deepseek/deepseek-v4-flash` or any `provider/model`-style name) alongside its existing xAI/Groq/Anthropic/OpenAI/Venice routing.
