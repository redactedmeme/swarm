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
| `build.py` | Regenerates everything derived: the prompt, the roster, `llms.txt`, `llms-full.txt`. |
| `system.prompt.md` | **Generated** from `../terminal/system.prompt.md`. Do not edit here. |
| `llms-full.txt` | **Generated.** `llms.txt` with the prompt and skill inlined. |
| `fonts/`, `fonts.css` | Self-hosted Archivo + Inconsolata. No third-party font requests. |
| `llms.txt` | Machine-readable summary for crawlers and agents. |
| `skill.md` | The REDACTED Terminal Claude Code skill, served at `/skill.md`. |
| `og.png`, `favicon.svg`, `favicon.ico` | Share card and icons. |

## Regenerating

Anything derived is rebuilt by one command:

```bash
python build.py
```

That copies `../terminal/system.prompt.md` to `system.prompt.md`, rewrites the roster
cards in `index.html` and the `## Agents` block in `llms.txt` from `data/agents.json`,
and bundles `llms-full.txt`. Run it after editing the roster or the canonical prompt.

`script.js` re-renders the same cards client-side from the JSON at runtime; the cards
`build.py` writes into `index.html` are the no-JS fallback. Never hand-edit the block
between `AGENTS:BEGIN` and `AGENTS:END`.

## What agents fetch

The prompt used to be pasted into `index.html` as a `<pre>` block. It drifted to a
truncated copy, and any agent that wanted it had to scrape HTML and unescape entities.
Nothing is inlined on the page any more — the page links, and these paths serve:

| Path | Type | What |
|---|---|---|
| `/llms.txt` | `text/plain` | Index of every artifact and live endpoint. Start here. |
| `/llms-full.txt` | `text/plain` | Same index with the prompt and skill inlined — one request gets everything. |
| `/system.prompt.md` | `text/markdown` | The terminal system prompt, generated from the canonical file. |
| `/skill.md` | `text/markdown` | The Claude Code skill. |
| `/data/agents.json` | `application/json` | Agent roster, structured. |
| `/api/swarm` | `application/json` | Live mesh heartbeats. |

All of them send `Access-Control-Allow-Origin: *` and a real content type, and all are
listed in `robots.txt` and `sitemap.xml`.

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
