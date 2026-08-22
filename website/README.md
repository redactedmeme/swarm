# website — redacted.meme

The public landing page. Hand-written HTML/CSS/JS, no framework, no build step.
Served by `serve.py` (Flask) on Railway: project `distinguished-wonder`, service
**`redacted-website`**, deployed from `main`.

```bash
cd website && python serve.py     # http://localhost:8080
```

## Layout

| Path | What |
|---|---|
| `index.html` | The whole page. Sections: hero, contract, status, links, about, manifesto, philosophy, swarm, governance, prompt, skill, footer. |
| `style.css` | All styling. Tokens live in `:root`. |
| `script.js` | Reveal-on-scroll, nav, and the three live readouts. |
| `data/agents.json` | **Source of truth for the agent roster.** |
| `build.py` | Regenerates the roster in `index.html` and `llms.txt` from that JSON. |
| `fonts/`, `fonts.css` | Self-hosted Archivo + Inconsolata. No third-party font requests. |
| `llms.txt` | Machine-readable summary for crawlers and agents. |
| `skill.md` | The REDACTED Terminal Claude Code skill, served at `/skill.md`. |
| `og.png`, `favicon.svg`, `favicon.ico` | Share card and icons. |

## Editing the agent roster

Edit `data/agents.json`, then:

```bash
python build.py
```

`script.js` re-renders the same cards client-side from the JSON at runtime; the cards
`build.py` writes into `index.html` are the no-JS fallback. Never hand-edit the block
between `AGENTS:BEGIN` and `AGENTS:END`.

## Live data

Three readouts, each of which degrades to *absent* rather than to an error state:

- **Market strip** — client-side fetch of the Dexscreener public API. Hidden if the
  call fails or the token has no pairs.
- **Agent roster** — `data/agents.json`, with the server-rendered cards as fallback.
- **Mesh status** — `GET /api/swarm`, which `serve.py` proxies from the swarm's own
  status service and caches for 30s. Unset or unreachable ⇒ `{"agents": []}` ⇒ the
  whole `#status` section stays hidden.

### Environment

| Var | Default | Purpose |
|---|---|---|
| `PORT` | `8080` | Listen port. |
| `SWARM_STATUS_URL` | *(unset)* | Full URL of the swarm-status `/status` endpoint. Unset disables the mesh status section. |
| `SWARM_STATUS_TIMEOUT` | `4` | Upstream fetch timeout, seconds. |
| `SWARM_CACHE_TTL` | `30` | How long a status response is reused. |

The upstream service lives in [`../swarm-status/`](../swarm-status/) and runs on the
umbrel node next to the mesh Redis. `serve.py` re-projects its response onto exactly
the four fields the page renders, so anything the upstream adds later stays off the
public surface until it is deliberately allowed through.
