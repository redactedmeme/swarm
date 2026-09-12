# apps/dsh — DeepSeek Harness

[DeepSeek Harness](https://github.com/deepseek-ai/deepseek-harness) (`dsh`, MIT) is an agent
harness — a coding agent with a web UI, CLI/TUI, and SDK/ACP stdio servers, built on a Cordis
"everything is a plugin" architecture. This app packages it as a swarm service whose LLM is
**redacted-proxy** (`apps/proxy`), so every model call goes through the same audited,
rate-limited, Mullvad-routed path as the rest of the swarm — no direct DeepSeek key.

## What's here

| File | Purpose |
|---|---|
| `Dockerfile` | `node:22` + `npm i -g @deepseek-ai/dsh@<pinned>`. Self-contained build context (no `swarm_core` import — must **not** build from the repo root). |
| `settings.yaml` | Seeded into `$DSH_HOME` on first boot. Declares the `redacted-proxy` custom provider (`openai-completions`, `baseURL` → proxy `/v1`, `apiKeyEnv: PROXY_TOKEN`, `X-Client: dsh`). |
| `entrypoint.sh` | Seeds `$DSH_HOME/settings.yaml` if absent (volume edits win), then `exec dsh "$@"`. |
| `.env.example` | `PROXY_TOKEN` (required), `DSH_HOME`. |

## LLM routing

`settings.yaml` configures dsh's `llm-pi-ai` adapter with one hand-declared provider:

```yaml
llm-pi-ai:
  providers:
    redacted-proxy:
      api: openai-completions
      baseURL: http://127.0.0.1:7080/v1   # host networking on umbrel
      apiKeyEnv: PROXY_TOKEN
      headers: { X-Client: dsh }
      models:
        - id: auto                        # proxy's free-first auto-router
        - id: deepseek/deepseek-v4-flash  # standardized paid default
```

The proxy has no reliable `/v1/models` contract for arbitrary gateways, so models are declared by
hand (dsh supports this — see its `docs/user/guide/providers.md`). After first boot, open
**Settings → Models** and select `redacted-proxy / auto`; the choice persists to
`$DSH_HOME/settings.yaml` on the volume. The built-in DeepSeek onboarding card can be ignored.

Usage shows up in the proxy's `GET /usage` under the `dsh` bucket (via the `X-Client` header),
while the shared `${PROXY_TOKEN}` authenticates — same arrangement as `hermes-bot`. To
rate-limit or credit dsh separately, add a dedicated token to the proxy's `PROXY_TOKEN_MAP`
as `{"<token>": "dsh"}` and set that as `PROXY_TOKEN` for this service instead.

## Running

```bash
docker build -t swarm-dsh apps/dsh
docker run --rm -p 3080:3080 -e PROXY_TOKEN=<proxy token> \
  --add-host host.docker.internal:host-gateway swarm-dsh
# open http://127.0.0.1:3080   (adjust baseURL for non-host networking)
```

Headless smoke (also the path a swarm agent would drive later):

```bash
docker run --rm -e PROXY_TOKEN=<token> swarm-dsh --profile headless "print hello"
```

On umbrel it runs as `swarm-dsh` with `network_mode: host`, reaching the proxy on
`127.0.0.1:7080`. See `infra/umbrel/swarm-infra-docker-compose.yml`.

## Access

dsh **refuses to bind anything but `127.0.0.1`** for the `web` profile (the UI is a remote-code-
execution surface), and it prints a fresh `?token=…` auth token in its logs on every boot
(`docker logs swarm-dsh`).

**Stable URL (tailnet):** `https://umbrel.taila13a94.ts.net:3080/` — a `tailscale serve` proxy
on the umbrel node (`tailscale_web_1` container) forwards it to `127.0.0.1:3080`. Reachable only
from devices on the tailnet; that is the access control. The dsh boot token is a second factor —
grab the current one with:

```bash
ssh umbrel@100.106.250.9 'sudo docker logs swarm-dsh 2>&1 | grep -o "token=[A-Za-z0-9_-]*" | tail -1'
```

then open `https://umbrel.taila13a94.ts.net:3080/?token=<token>` once; the cookie it sets keeps
the session. The CMD passes `--trusted-host umbrel.taila13a94.ts.net:3080` so dsh's browser-trust
fence accepts the proxied origin.

To re-point or remove the proxy:
`sudo docker exec tailscale_web_1 tailscale serve --https=3080 off`

**SSH tunnel (fallback):** `ssh -N -L 3080:127.0.0.1:3080 umbrel@100.106.250.9`, then
`http://127.0.0.1:3080/?token=<token>`.

## Security
- Runtime egress is only the loopback proxy, so no `swarm-egress` caller is wired. If you want
  the web UI's plugin-install flow, add a `dsh` caller to
  `packages/swarm-core/src/swarm_core/security/egress.yaml` allowing `registry.npmjs.org` and
  `codeload.github.com` only, and point `HTTPS_PROXY` at swarm-egress.

## Not yet done

Wiring a swarm agent (hermes / builder / workspace) to drive dsh over ACP (`dsh --profile acp`)
or SDK (`dsh --profile sdk`) as its code-exec backend. This app only stands the service up.
