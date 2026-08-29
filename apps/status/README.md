# swarm-status

> **Status: built, not yet deployed.** See *Deploy* below — it needs a container on the
> umbrel node and a Tailscale Funnel port before `redacted.meme` can show anything.

The swarm's only public read-only surface. Reads `swarm:heartbeat:{agent}` from the mesh
Redis and answers one question: which agents are alive?

`redacted.meme` proxies this (server-side, cached) and renders it as the MESH STATUS
section. Nothing else consumes it.

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
| `GET` | `/status` | The payload above. Cached `CACHE_TTL` seconds. Never 500s — a Redis failure returns an empty agent list. |
| `GET` | `/healthz` | `{"status": "ok", "redis": true\|false}` |

## Environment

| Var | Default | Purpose |
|---|---|---|
| `REDIS_URL` | `redis://swarm-redis:6379/0` | Mesh Redis. |
| `PORT` | `8098` | Listen port. |
| `ALLOW_ORIGIN` | `https://redacted.meme` | CORS origin. Only matters if a browser ever hits it directly; the website proxies server-side. |
| `CACHE_TTL` | `15` | Seconds a `/status` response is reused. |

## Deploy (umbrel node)

```bash
docker compose -f compose.status.yml up -d --build
curl -s localhost:8098/status
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
