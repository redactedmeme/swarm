# Umbrel box — captured stack definitions

These files are the **authoritative** definitions for everything running on the
umbrel node (`umbrel@${UMBREL_HOST}`). Until 2026-08-29 they existed only on the
box and were not in version control; losing the box meant losing the stack.

| File | Lives on box at | What it is |
|---|---|---|
| `swarm-infra-docker-compose.yml` | `/home/umbrel/swarm-infra/docker-compose.yml` | The swarm stack: runtime, hermes-bot, smolting, refinery, builder, redacted-proxy + postgres/redis/qdrant/gluetun/cloudflared |
| `redacted-chan-docker-compose.yml` | `/home/umbrel/redacted-chan/docker-compose.yml` | redacted-chan, its config API, webchat, and its own redis |
| `autostart-bootstrap-docker-compose.yml` | `/home/umbrel/autostart-bootstrap/docker-compose.yml` | Boot shim container (`restart: always`) that runs the script below |
| `autostart-stacks.sh` | `/home/umbrel/autostart-stacks.sh` | Brings every custom stack up after a reboot or umbrelOS update |

## Why boot goes through a container, not systemd

umbrelOS updates wipe `/etc` — which removes systemd units *and* the cron binary
entirely. `/var/lib/docker` survives. So a `restart: always` container is the only
durable boot hook on this host. `autostart-stacks.sh` also self-heals two things
umbrelOS resets: the `fs.inotify` limits (~50 containers exhaust the default 256
instances and crash-loop cadvisor) and `umbrel`'s membership in the `docker` group.

Note: `secrets/NETWORK_INFRA.md` refers to `/etc/systemd/system/swarm-infra.service`.
That unit **does not exist** — it was a casualty of exactly the `/etc` wipe described
above, and the autostart container replaced it.

## Build contexts

Every swarm service builds with its **own directory as the Docker context**:

```
context: /home/umbrel/swarm/<service>
dockerfile: Dockerfile
```

This is the binding constraint on the monorepo reorganization: a service's build
context does not include the repo root, so it cannot see a shared `packages/`
directory. Introducing a shared package requires either moving the build context
up to the repo root (and setting `dockerfile:` to the service path), or publishing
the shared package and installing it as a normal dependency.

## Keeping these in sync

These are **copies**. Editing them here changes nothing on the box. After changing
one, copy it up and re-up the stack:

```bash
scp -i secrets/ssh/homelab_ed25519 infra/umbrel/swarm-infra-docker-compose.yml \
    umbrel@${UMBREL_HOST}:/home/umbrel/swarm-infra/docker-compose.yml
```

## Redactions

`swarm-infra-docker-compose.yml` inlines two real proxy tokens on the box
(`hermes-bot` and `refinery`). Both are replaced here with `${PROXY_TOKEN}`.
The live values are on the box and in `secrets/swarm_proxy_tokens.txt`; do not
copy this file back up without restoring them, or both services lose proxy access.
