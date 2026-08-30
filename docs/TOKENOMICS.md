# $REDACTED — Utility and Value Accrual

Canonical source for what the token is, what it costs to use the swarm, and
what holding it unlocks. Every value here has a machine-readable counterpart in
[`packages/swarm-core/src/swarm_core/tokens.py`](../packages/swarm-core/src/swarm_core/tokens.py);
that module is the implementation, this document is the explanation. If the two
disagree, the module is right and this file is stale — fix it.

## The thesis in one line

**The swarm sells its work. Every job is paid in $REDACTED. Half of what it
earns is burned, and the rest keeps the swarm running.**

Not a reflection of trading fees. The revenue comes from the swarm doing
things — semantic search over its own signal corpus, committee deliberation,
parallel reasoning, proxied inference — which means it grows with *usage*
rather than decaying with volume.

## Identity

| | |
|---|---|
| Mint | `9mtKd1o8Ht7F1daumKgs5D8EdVyopWBfYQwNmMojpump` |
| Chain | Solana |
| Decimals | 6 |
| DAO treasury (payments go here) | `9xLGQrf3uge7tncimyrKjFcDEDptQRS2QG6Zxv67z7r` — `redacteddao.sol` |
| Burn address | `1nc1nerator11111111111111111111111111111111` |
| Legacy mint (V1, superseded) | `9a21gb7fWGm9dD2UFdZAzgFn5K1NwfmYkjyLbpAcKgnM` |

The treasury address is configuration, not a constant: no wallet is hardcoded
anywhere in the source. `SWARM_TREASURY_ADDRESS` has no default, so a
misconfigured deployment refuses to verify payments instead of checking them
against an empty `payTo` — which would accept any transaction at all.

Services resolve the mint from `PROJECT_TOKEN_MINT`, never from a literal. The
legacy mint is referenced only by the dashboard, which charts both curves, and
by `apps/arb-keeper`, whose pool addresses are a matched V1 set that has to
migrate together with it.

Solana has no burn instruction for a plain transfer, so value is retired by
sending it to the system incinerator — an address no one holds the key to.
Every burn is a normal transaction, visible on any explorer.

## Price sheet

Prices are in whole $REDACTED and are deliberately small: the point is for the
endpoints to be used, not to extract from the handful of people who find them.
Each is overridable per-deployment via `PRICE_<ID>`.

| Offer | Service | Price | What you get |
|---|---|---|---|
| `refine` | refinery | 1,000 | Semantic search across the swarm's ingested signal corpus |
| `committee` | sevenfold-committee | 5,000 | Deterministic seven-voice weighted vote, 71% supermajority |
| `deliberate` | sevenfold-committee | 25,000 | Live LLM deliberation across all seven voices |
| `beam` | hermes | 25,000 | BEAM-SCoT parallel reasoning, beam width 4 |
| proxy inference | proxy | metered | 100 $REDACTED per 1k LLM tokens, drawn from credits |

Payment is [x402](https://x402.org) over Solana. A call arrives without payment,
gets a `402` naming the price and the treasury address, pays, and retries with
the signature in `X-Payment-Signature`. Verification is in
[`swarm_core/x402/verify.py`](../packages/swarm-core/src/swarm_core/x402/verify.py):
the transaction must be confirmed, move at least the asking price of the right
mint into the treasury, be under five minutes old, and **not have been used
before** — signatures spend exactly once, guarded by an atomic Redis claim.

Agents on our own mesh bypass payment with an operator token. Charging the
swarm to talk to itself would only move tokens between our own wallets.

## Where the money goes

Every verified payment splits three ways:

| Slice | Share | Fate |
|---|---|---|
| **Burn** | 50% | Sent to the incinerator. Irreversible, verifiable, gone. |
| **Compute** | 30% | Buys the swarm's own LLM API credits. |
| **Rewards** | 20% | Reserved pool, claimable — see below. |

### The compute slice pays for the swarm's own inference

This is the part that makes the swarm self-funding rather than subsidised.
`apps/proxy` already meters real `cost_usd` per client per day, so we know to
the cent what the swarm costs to run. Treasury balance divided by trailing
30-day spend gives **`SWARM RUNWAY`** — published live on the site and in
`/api/swarm`.

It goes *up* when people use the swarm. That is the whole design.

This slice is **spent, not accrued**. It is an operating cost and is never
presented as value flowing to holders. It is capped at
`COMPUTE_RUNWAY_CAP_DAYS` (default 90): once the treasury holds more than that
much runway, the overflow rolls into the burn instead of accumulating. A
treasury that grows without limit is an unaccountable pile; a capped one is a
budget.

### The rewards slice

Reserved, and deliberately not yet distributing. When it activates it will be a
**claim** against the pool — holder-initiated, snapshot-based — rather than an
automatic push. Nothing in this repository promises a return, and the site copy
describes what the contracts do rather than what a holder will earn.

## What holding unlocks

Thresholds are token-denominated rather than dollar-denominated on purpose: a
USD-pegged gate needs a price oracle inside the authentication path, which is
one more thing that can fail open.

| Tier | Hold | Unlocks |
|---|---|---|
| **operator** | 1,000,000 | Terminal access |
| **architect** | 10,000,000 | Private agents, raised proxy rate limit |
| **monolith** | 100,000,000 | Committee and deliberation calls included rather than metered |

Access is proven by signing a server-issued nonce with the wallet, then reading
its balance on-chain. No transfer, no approval, no custody — the swarm never
touches held tokens.

Live today: the **operator** tier gates the NERV terminal
(`swarm_core.gate`, `apps/terminal` with `HOLDER_GATE=true`). Every successful
sign-in records the full grant set at `gate:grants:<wallet>` in Redis; the
`architect` / `monolith` grants (private agents, raised proxy RPM, included
committee calls) are recorded there but not yet read by any consumer.

## On-chain settlement

Every verified payment is split at settlement time — burn / compute / rewards —
and accumulated in the Redis hash `swarm:treasury`
([`swarm_core.x402.settle`](../packages/swarm-core/src/swarm_core/x402/settle.py),
run inline in the payment path). `apps/status` reads that hash into
`/api/swarm`.

The on-chain half is [`apps/settler`](../apps/settler/) — the only component
that holds `SWARM_TREASURY_PRIVATE_KEY`. When `SETTLEMENT_EXECUTE=true` it
drains the owed burn slice by sending a `TransferChecked` from the treasury's
token account to the incinerator's, **with an SPL Memo in the same transaction**
recording the settlement it retires. One Solscan-visible transaction per burn;
no deployed program. `SETTLEMENT_EXECUTE` defaults to off — the ledger still
accrues and `burned_total` stays `0` until it is turned on.

`programs/mandala_settler` — a real Anchor program with a vault PDA and
settlement events — exists in the tree but has a placeholder program ID and has
never been deployed. It is deferred until there is revenue worth custodying,
and it should be audited before it holds anything.

## Configuration

| Variable | Meaning |
|---|---|
| `PROJECT_TOKEN_MINT` | The mint every service transacts against |
| `SWARM_TREASURY_ADDRESS` | Where payments must land. **No default** — verification refuses to run without it, because an empty `payTo` would accept any transaction at all |
| `SWARM_BURN_ADDRESS` | Defaults to the system incinerator |
| `SPLIT_BURN_PCT` / `SPLIT_COMPUTE_PCT` / `SPLIT_REWARDS_PCT` | Revenue split; must sum to 100 |
| `COMPUTE_RUNWAY_CAP_DAYS` | Runway past which the compute slice rolls into the burn |
| `X402_FRESHNESS_WINDOW_S` | How old a payment signature may be (default 300) |
| `CREDITS_PER_1K_TOKENS` | Proxy inference price. Read by both `swarm_core.tokens` and `apps/proxy` |
| `CREDITS_ENFORCE` | When true the proxy 402s a client whose `credits:balance` is exhausted. Default off |
| `CREDITS_EXEMPT` | Client names the proxy never hard-blocks (the swarm's own bots) |
| `CREDITS_DEPOSIT_MEMO_PREFIX` | Memo prefix (`redacted-credits:`) the settler credits balances from |
| `REFINERY_OPERATOR_TOKEN` | On-mesh bypass, and the gate on private signal rows |

## What is not built yet

Stated plainly, because a tokenomics document that describes aspirations as
mechanisms is how projects lose people's trust:

- **Credits enforcement** (Phase 2) — the proxy debits `credits:balance:<client>`
  per request and `apps/settler` credits it from memo-tagged deposits
  (`redacted-credits:<client>`) and settles the spend through the burn split.
  But `CREDITS_ENFORCE=false` for now: balances move and would-be refusals are
  logged, no request is blocked yet.
- **Higher holder tiers** (Phase 3) — the `operator` tier gates the terminal
  today; `architect` / `monolith` grants are recorded in `gate:grants:<wallet>`
  but nothing reads them yet (no committee endpoint exists; the proxy can't map
  a wallet to a token).
- **On-chain burns** (Phase 4) — the settlement ledger and treasury split are
  live (`swarm_core.x402.settle`, `apps/settler`), but `apps/settler` runs with
  `SETTLEMENT_EXECUTE=false` until the treasury key is placed on the box, so no
  burn has been executed on chain yet.
- **Buyback** (Phase 5) — `apps/arb-keeper` has the execution engine, gated off
  behind `EXECUTE_TRADES=false`.
- **Rewards claims** (Phase 7) — reserved, not distributing.

Live today: the payment rail, the priced `refine` endpoint, the settlement
ledger (accruing; burns pending `SETTLEMENT_EXECUTE`), and the credits ledger
(debiting + depositing + settling; enforcement pending `CREDITS_ENFORCE`).
