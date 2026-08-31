# secrets-init (IronClaw control 2)

Resolves a manifest of secret names from Vaultwarden into a **tmpfs** file at
container start, so agents stop carrying raw provider/wallet keys in their own
environment or image.

## Flow

```
secrets-init  ──writes──▶  /run/secrets/swarm.env  (tmpfs, 0600)
                                   │
agent container  ──reads──▶  swarm_core.security.secrets.get_secret("OPENAI_API_KEY")
```

`get_secret()` resolution order: process cache → `SWARM_SECRETS_FILE` → env
(logged as deprecated) → Vaultwarden. So migration is incremental: wire
`secrets-init` first, switch call sites from `os.getenv` to `get_secret` over
time, then remove the plaintext env vars from compose.

## Compose wiring (per agent)

```yaml
  hermes-secrets:
    build: { context: /home/umbrel/swarm, dockerfile: apps/secrets-init/Dockerfile }
    environment:
      SWARM_SECRETS_FILE: /run/secrets/swarm.env
      SECRETS_MANIFEST: "GROQ_API_KEY,OPENROUTER_API_KEY,MOLTBOOK_API_KEY,X_API_KEY,X_API_KEY_SECRET,X_ACCESS_TOKEN,X_ACCESS_TOKEN_SECRET"
      SECRETS_BACKEND: bw
      BW_SESSION: ${BW_SESSION}
      SECRETS_STRICT: "1"
    volumes: [ "hermes-secrets:/run/secrets" ]
    restart: "no"

  hermes-bot:
    # ...
    environment:
      SWARM_SECRETS_FILE: /run/secrets/swarm.env
    volumes: [ "hermes-secrets:/run/secrets" ]
    depends_on:
      hermes-secrets: { condition: service_completed_successfully }
```

The `hermes-secrets` volume must be a tmpfs (declare `driver_opts: { type: tmpfs, device: tmpfs }`)
so nothing lands on disk.

## Backends

* `bw` (default) — `@bitwarden/cli` against the swarm's Vaultwarden. Needs
  `BW_SESSION` (or `BW_CLIENTID`/`BW_CLIENTSECRET` + an unlock step).
* `env` — passthrough for local dev (copies named vars into the file).
