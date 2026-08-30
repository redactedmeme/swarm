# swarm-settler

The on-chain half of the `$REDACTED` flywheel. It owns one job and one secret.

## What it does

1. **Recounts** `swarm:settlements:ts` into `swarm:treasury.settlements_24h`
   every tick.
2. **Refreshes metrics** (~every 5 min): `treasury_balance`,
   `compute_spend_30d_usd` (from the proxy's `GET /usage?days=30`), and
   `runway_days = treasury_value_usd / (spend_30d / 30)`.
3. **Reconciles** (~every 5 min): walks recent inbound treasury transfers and
   replays any `record_settlement` missed (e.g. a Redis blip during a paid
   call). Outbound burns net negative and are ignored.
3b. **Credits** (Phase 2, every tick / 5 min): drains `credits:spend:queue`
   (the proxy's per-request debits) into burn-split settlements, and credits
   `credits:balance:<client>` for treasury deposits whose SPL Memo starts with
   `CREDITS_DEPOSIT_MEMO_PREFIX` (`redacted-credits:<client>`). A deposit is
   marked so the reconcile pass won't also burn-split it. Runs regardless of
   `SETTLEMENT_EXECUTE`.
4. **Burns** (only when `SETTLEMENT_EXECUTE=true`): drains
   `burn_accrued − burned_total` by sending `TransferChecked` of the owed
   amount from the treasury's token account to the incinerator's, with an SPL
   Memo naming the settlement, in one transaction.

The ledger itself (`revenue_total`, `burn_accrued`, `compute_accrued`,
`rewards_accrued`, `settlements_total`, `last_settlement_sig`, the
`swarm:settlements:*` feed) is written by `swarm_core.x402.settle` inline in the
payment middleware — **not here**. This service only consumes it and executes
the burn.

## The `SETTLEMENT_EXECUTE` gate

Default **off**. Off: the worker runs, recounts, refreshes metrics, reconciles —
but signs nothing, and `SWARM_TREASURY_PRIVATE_KEY` is not read. The ledger
accrues and `burned_total` stays `0` — the honest "owed, not yet burned" state.

On: `SWARM_TREASURY_PRIVATE_KEY` is required, and the worker **refuses to start
unless its public key equals `SWARM_TREASURY_ADDRESS`** — a guard against
burning from the wrong wallet.

Mirrors `apps/arb-keeper`'s `EXECUTE_TRADES`: the code that signs real
transactions with real funds ships behind a switch and is turned on
deliberately.

## Crash safety

Before `sendTransaction` the signed bytes, signature and blockhash are stashed
in `swarm:treasury.burn_pending_*`. On restart the worker re-checks that
signature and, if it is still unlanded, **re-broadcasts the identical bytes** —
it never builds a fresh burn for a debt that might already be paid. The
owed→burned move (`burned_total += amount`, clear pending) is one `MULTI/EXEC`
guarded by `swarm:treasury:burned:seen`, so a double resume cannot double-count.

## Circuit breaker

`BURN_FAIL_STREAK_MAX` (default 5) consecutive burn failures sets
`swarm:treasury.burn_halted`. To resume: clear `burn_halted` and
`burn_fail_streak` on the hash.

## Deploy

Umbrel service, host networking, `REDIS_URL=redis://127.0.0.1:6379`. Config in
`infra/umbrel/.env.settler` (git-ignored) — **never** the shared `.env`. See
`.env.example`.
