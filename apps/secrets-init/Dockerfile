# One-shot: resolves secrets from Vaultwarden into a tmpfs file, then exits.
# Share a tmpfs volume with the agent container and gate the agent on this
# completing (compose: depends_on: { secrets-init: { condition: service_completed_successfully } }).
FROM node:22-slim

RUN npm install -g @bitwarden/cli@latest \
 && apt-get update && apt-get install -y --no-install-recommends python3 \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY apps/secrets-init/fetch.py .

# BW_SESSION / BW_CLIENTID / BW_CLIENTSECRET provided at runtime; nothing baked in.
CMD ["python3", "fetch.py"]
