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

Four readouts, each of which degrades to *absent* rather than to an error state:

- **Market strip** — client-side fetch of the Dexscreener public API. Hidden if the
  call fails or the token has no pairs.
- **Agent roster** — `data/agents.json`, with the server-rendered cards as fallback.
- **Mesh status** — `GET /api/swarm`, which `serve.py` proxies from the swarm's own
  status service and caches for 30s. Unset or unreachable ⇒ `{"agents": []}` ⇒ the
  whole `#status` section stays hidden. Queue depth is projected as `pending` when the
  upstream supplies it, and simply omitted when it doesn't.
- **Live ticker** (`#live-ticker`) — the marquee under the hero. Carries real telemetry
  from the two polls above, never hardcoded copy. Each cell stays hidden until its value
  resolves (`.is-live`), and the whole strip stays hidden until at least one does, so it
  scrolls readings rather than a row of em-dashes.

### Motion

The two marquees are pure CSS: the track holds the item sequence twice and translates
-50%, so the second copy lands where the first began. Nothing animates per-item, and
hovering pauses the strip.

`prefers-reduced-motion` needs an explicit rule here. The global `animation-duration:
0.01ms !important` clamp would *finish* the marquee rather than stop it — snapping the
track to its end position. The reduced-motion block instead sets `animation: none`,
drops the duplicate sequence, and makes the strip hand-scrollable.

The live values count up on change. The final value is written **before** the animation
starts, because `requestAnimationFrame` is throttled to a standstill in a backgrounded
tab — a loop that only assigns the real number in its last frame leaves a stale one on
screen. The count-up is decoration over an already-correct value.

### Structured data

`index.html` carries a JSON-LD `@graph` (`WebSite` + `Organization` + `SoftwareApplication`)
stating what the site is, who publishes it, and which machine-readable artifacts exist —
facts a crawler or model would otherwise have to infer from prose.

It deliberately carries **no agent counts**. Those live in `data/agents.json`, and
duplicating them here would drift. If you add or remove a published artifact, update the
`hasPart` list — every URL in it must resolve, and each `encodingFormat` must match the
content type `serve.py` actually sends.

### Colour

The palette is a near-black ramp plus a grey text ramp. Only two chromatic tokens exist
and both are strictly reserved:

- `--blue` — **liveness only**: the heartbeat dot, the ONLINE state, and the per-agent
  live marker. Nothing else. A number being fresh, a filename, a focus ring or a hover
  state are not liveness; colouring those made the blue read as decoration rather than
  signal, which is exactly what a reserved colour must not do.
- `--red` — warnings and negative values only.

If you reach for either outside those roles, use `--text`/`--muted`/`--dim` instead.

### Caching

`style.css` and `script.js` are served `max-age=60, must-revalidate`. Their filenames
never change but their contents change on nearly every deploy, so a long cache means
visitors run new HTML against old CSS. Fonts and images stay `immutable` for a year —
their content genuinely doesn't change.

### Environment

| Var | Default | Purpose |
|---|---|---|
| `PORT` | `8080` | Listen port. |
| `SWARM_STATUS_URL` | *(unset)* | Full URL of the swarm-status `/status` endpoint. Unset disables the mesh status section. |
| `SWARM_STATUS_TIMEOUT` | `4` | Upstream fetch timeout, seconds. |
| `SWARM_CACHE_TTL` | `30` | How long a status response is reused. |

The upstream service lives in [`../apps/status/`](../apps/status/) and runs on the
umbrel node next to the mesh Redis. `serve.py` re-projects its response onto exactly
the four fields the page renders, so anything the upstream adds later stays off the
public surface until it is deliberately allowed through.
