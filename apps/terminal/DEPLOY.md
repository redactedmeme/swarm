# Redeploying the terminal

The deployed `terminal.redacted.meme` is an older build. Verified 2026-09-04:
`/health`, `/api/wallet/status` and `/api/dht/peers` all answer, while every
`/api/gate/*` route returns 404. So the holder gate has never run in
production, and `docs/TOKENOMICS.md` claiming the operator tier gates the
terminal was wrong until it was corrected.

**A redeploy on its own is not enough.** The service currently carries three
non-Railway variables (`FLASK_ENV`, `GROQ_API_KEY`, `WEB_PORT`). Shipping the
new build without the rest leaves the gate importable but non-functional: every
`/api/gate/nonce` would 503, because there is no Redis for it to reach.

## Prerequisites

### 1. Redis — required, and currently absent

`REDIS_URL` is unset, so `swarm_core.gate` falls back to
`redis://localhost:6379`, which is nothing in a Railway container. The gate
stores its sign-in nonces there; without it the flow cannot start.

Add a Redis service in the Railway project and set `REDIS_URL` on
`redacted-terminal` to its connection string. It also becomes the store for the
published alpha report, which otherwise lives only in process memory and is
lost on every restart.

### 2. Variables

| Variable | Value | Why |
|---|---|---|
| `REDIS_URL` | from the Redis service | **Required.** Gate nonces + the alpha report. |
| `HOLDER_GATE` | `true` | **Required.** Turns the gate on; without it the routes exist but refuse with "holder gate not enabled". |
| `FLASK_SECRET_KEY` | a long random string | Sessions carry the grants that gate `/alpha`. Unset, the app generates a fresh key per process, so every restart silently signs everyone out. |
| `ALPHA_PUBLISH_TOKEN` | a long random string | Shared with smolting. Unset, `/api/alpha/publish` returns 404 and the feed is never populated. |
| `PROJECT_TOKEN_MINT` | `9mtKd1o8Ht7F1daumKgs5D8EdVyopWBfYQwNmMojpump` | Optional — `tokens.token_mint()` already defaults to this. Set it so the mint is visible in config rather than implied by a constant. |

`GATE_STRICT=true` is worth setting as a belt-and-braces measure: it makes the
app refuse to serve rather than start unauthenticated if `HOLDER_GATE` is ever
cleared by accident.

### 3. The matching smolting variables

On the node, in the smolting service environment:

```
ALPHA_PUBLISH_URL=https://terminal.redacted.meme/api/alpha/publish
ALPHA_PUBLISH_TOKEN=<the same value as above>
ALPHA_PAGE_URL=https://terminal.redacted.meme/
```

Until **both** `ALPHA_PUBLISH_URL` and `ALPHA_PUBLISH_TOKEN` are set, smolting
keeps posting the full report to the public group exactly as it does today. That
is deliberate: a half-configured migration should not silently go quiet.

## Deploying

The repo has no deploy workflow — `.github/workflows/` builds executables and
runs checks only. Deployment is either Railway's GitHub integration on the
connected branch, or `railway up` from `apps/terminal`. `railway.toml` already
pins the Dockerfile build with the repo root as context, which is required
because the image installs `packages/swarm-core`.

Note the `RAILWAY_API_TOKEN` in `secrets/homelab.env` returns **Unauthorized** —
it has been revoked. Deploying needs a fresh token or the dashboard.

## Verifying afterwards

```bash
# The gate routes must exist. This is the check that fails today.
curl -s -o /dev/null -w '%{http_code}\n' https://terminal.redacted.meme/api/gate/status   # expect 200

curl -s https://terminal.redacted.meme/api/gate/status
# expect: {"gate_required":true,"holder_gate":true,"authenticated":false,...}

# Publishing rejects a bad secret and accepts the real one.
curl -s -o /dev/null -w '%{http_code}\n' -X POST \
  https://terminal.redacted.meme/api/alpha/publish \
  -H 'X-Alpha-Token: wrong' -H 'Content-Type: application/json' \
  -d '{"report":"x"}'                                                                     # expect 401

# The feed is closed to anyone unverified.
curl -s https://terminal.redacted.meme/api/alpha
# expect 403 {"error":"locked","required_grant":"alpha-feed","min_required":10000000}
```

Then in a browser: connect a wallet holding at least 1,000,000 to sign in, run
`/alpha`, and confirm a wallet below 10,000,000 is refused with the 10,000,000
figure quoted rather than a generic denial.

A `min_required` of `1000000` on that 403 would mean an old `swarm_core` is
installed in the image — `tokens.threshold_for_grant()` is what makes the
number correct per grant.
