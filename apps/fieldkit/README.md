# fieldkit — REDACTED Field Kit

Mobile-first companion surface for the REDACTED AI swarm. A pocket terminal, not
a dashboard of record: live mesh liveness, token tape, the agent roster, and a
Sevenfold Chamber / Pattern Blue simulation.

Originally scaffolded by Grok Build; imported and rewired to repo conventions
(inference through `redacted-proxy`, roster from the live source of truth, Grok
sandbox scaffolding removed).

## Stack

TanStack Start (React 19, Vite, Nitro) · Tailwind v4 · deployed to **Vercel**.
Self-contained build context — imports no shared `packages/`. No auth, no database.

## Routes

| Path | What |
|---|---|
| `/` | Mesh stats + `{7,3}` mandala + token strip |
| `/ticker` | DexScreener token detail (price, flow, volume windows) |
| `/agents`, `/agents/$id` | Roster with filter/search; per-agent detail |
| `/chamber` | Sevenfold Committee deliberation (proxy inference, local fallback) |
| `/pattern` | Pattern Blue manifesto + DharmaNode koan |
| `/field` | Link hub + local-only field notes |

## Data sources (all public, read-only)

- `https://redacted.meme/data/agents.json` — roster source of truth (`apps/website`)
- `https://redacted.meme/api/swarm` — mesh liveness (`apps/status`, proxied by the website)
- `https://api.dexscreener.com` — token / price
- `src/data/roster.ts` — offline fallback stub only

## Env

See [`.env.example`](.env.example). All optional. Without `PROXY_URL` /
`PROXY_TOKEN` the Chamber and DharmaNode pages serve a deterministic local
lattice; everything else works unchanged.

## Dev

```bash
cd apps/fieldkit
npm install
npm run dev        # http://localhost:5173
npm run typecheck
npm run build      # Nitro Vercel output in .output/ (+ .vercel/)
```

## Deploy

Vercel project, root directory `apps/fieldkit`, framework preset **Vite** (Nitro
emits the Vercel build output automatically). Set `PROXY_URL` / `PROXY_TOKEN` in
the Vercel project env to enable live inference.
