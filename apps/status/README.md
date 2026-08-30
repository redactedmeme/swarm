# swarm-status

> **Status: built, not yet deployed.** See *Deploy* below — it needs a container on the
> umbrel node and a Tailscale Funnel port before `redacted.meme` can show anything.

The swarm's only public read-only surface. Reads `swarm:heartbeat:{agent}` and
`swarm:door:{agent}:{name}` from the mesh Redis, joins them against a checked-in
registry, and answers: which agents exist, which are running, which are asleep on
purpose, and what they expose.

`redacted.meme` proxies this (server-side, cached) and renders it as the MESH STATUS
section. Nothing else consumes it.

## Declared vs observed

Every field is one of two kinds, and the distinction is the whole safety argument:

* **Declared** — from `../website/data/agents.json` and `offers.json`, both already
  rendered publicly on redacted.meme. Republishing them costs nothing.
* **Observed** — from mesh Redis, coarsened to buckets and booleans, never numbers,
  because cadence is fingerprintable.

An observed number must never leak into a declared field.

`state` is declared; `online` is observed. Keeping them separate is the point of the
whole endpoint — it makes `state: "active", online: false` expressible, which is
exactly the alarm condition, and it stops a deliberately dormant app from being
indistinguishable from a crashed one.

| `state` | Meaning |
|---|---|
| `active` | Declared live, and expected to be heartbeating. |
| `asleep` | Declared, deliberately not running (`degen`, `x402`, `arb-keeper`, `mcp`). Not a failure. |
| `retired` | Was live, will not return. Still listed so lineage edges do not dangle. |

## What it exposes

```json
{
  "agents": [
    {"id": "smolting", "label": "smolting", "online": true, "last_seen_bucket": "just now"}
  ],
  "ts": "2026-08-22T12:00:00Z"
}
```

That is the entire surface. It deliberately does **not** expose model or provider names,
prompt or response content, message counts, queue depths, token usage, or exact
timestamps — age is reported as a coarse bucket so the feed cannot be used to fingerprint
an agent's cadence. Agents are allow-listed in `AGENT_LABELS`; a key not in that map is
invisible even if it is writing heartbeats.

Heartbeat parsing is reused from `hermes-bot/swarm_heartbeat.py`, vendored into
`vendor/` at build time so the container stays standalone. If that module changes,
re-copy it:

```bash
cp ../hermes-bot/swarm_heartbeat.py vendor/swarm_heartbeat.py
```

## Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/swarm` | The full feed — declared roster plus coarse observed liveness. Cached `CACHE_TTL` seconds per distinct query. |
| `GET` | `/status` | The legacy payload above, byte-identical. Kept as an alias because redacted.meme's MESH STATUS section reads it. |
| `GET` | `/healthz` | `{"status": "ok", "redis": true\|false}` |

Neither read endpoint ever 500s. `/status` returns an empty agent list on a Redis
failure; `/api/swarm` returns the declared roster with every observed field degraded
(`online: false`, `"no signal"`, no doors), since declared data needs no Redis at all.

### `GET /api/swarm`

```jsonc
{
  "at": "2026-08-29T21:14:00Z",
  "nonprivileged": "Read from mesh heartbeat keys and a checked-in registry. …",
  "query":  { "q": null, "state": [], "tier": [], "sort": "tier", "order": "asc",
              "limit": 50, "total": 13, "shown": 4, "hidden": 9 },
  "counts": { "declared": 13, "active": 6, "asleep": 7, "retired": 0, "doors_open": 1 },
  "agents": [
    {
      "id": "smolting", "name": "@RedactedIntern / smolting", "tier": "CORE",
      "dimension": "Chaotic Self-Reference", "host": "umbrel mesh",
      "state": "active",
      "online": true, "last_seen_bucket": "just now",
      "doors": [ { "name": "telegram", "kind": "surface",
                   "open": true, "checked_bucket": "just now" } ],
      "lineage": { "parent": null, "children": [] }
    }
  ],
  "offers": [ { "id": "refine", "agent": "refinery", "kind": "x402",
                "title": "…", "endpoint": null, "open": false } ]
}
```

| Param | Default | Meaning |
|---|---|---|
| `q` | — | Substring over `id`, `name`, `dimension` |
| `state` | — | `active` \| `asleep` \| `retired` (repeatable or comma-separated) |
| `tier` | — | `CORE` \| `APEX` \| `SPECIALIZED` (repeatable or comma-separated) |
| `sort` | `tier` | `tier`, `id`, `last_seen` |
| `order` | `asc` | `asc`, `desc` |
| `limit` | `50` | clamped to 1–200 |

`hidden` counts entries that matched the filter but were withheld — by the
`AGENT_LABELS` allow-list, or by `limit`. A caller can always tell "nothing matched"
from "something matched and you are not being shown it"; silent truncation is how a
status feed starts lying.

**Doors** are named capabilities, not processes. A heartbeat says an announce loop
ran; a door says a named capability is being asserted. They are written by
`apps/runtime`'s `POST /announce` from each agent's declared `capabilities`, under
`swarm:door:{agent}:{name}` with the heartbeat TTL — so a door that stops being
asserted disappears rather than going stale. This is announce-driven on purpose: the
agent asserts its own doors, so nothing reading these keys needs an outbound-request
capability. Agents that do not announce (chan, builder) report `doors: []`, which is
accurate rather than an error. Doors are named but never addressed — no internal URL
appears in the feed.

## Environment

| Var | Default | Purpose |
|---|---|---|
| `REDIS_URL` | `redis://swarm-redis:6379/0` | Mesh Redis. |
| `PORT` | `8098` | Listen port. |
| `ALLOW_ORIGIN` | `https://redacted.meme` | CORS origin. Only matters if a browser ever hits it directly; the website proxies server-side. |
| `CACHE_TTL` | `15` | Seconds a response is reused (`/api/swarm` caches per query). |
| `AGENTS_JSON` | `../website/data/agents.json` | Declared agent registry. |
| `OFFERS_JSON` | `./offers.json` | Declared offers registry. |

## Deploy (umbrel node)

```bash
docker compose -f compose.status.yml up -d --build
curl -s localhost:8098/api/swarm
```

It binds to `127.0.0.1:8098` only. To publish it, use Tailscale Funnel — no DNS change
and no domain move:

```bash
tailscale funnel --bg --https=8443 http://127.0.0.1:8098
tailscale funnel status
```

Then point the website at it (Railway → `redacted-website`):

```
SWARM_STATUS_URL=https://<node>.taila13a94.ts.net:8443/status
```

Until that variable is set, `redacted.meme` simply does not render the status section.
