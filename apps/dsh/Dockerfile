# DeepSeek Harness (`dsh`) as a swarm service.
#
# Self-contained: this app does NOT import swarm_core, so its Docker build
# context is its OWN directory (apps/dsh/), never the repo root. Giving it a
# repo-root context would be the classic swarm outage — wrong entrypoint,
# crash-loop. See CLAUDE.md "Build contexts".
#
# dsh is pulled from npm at build time (pinned). All LLM inference is routed
# through redacted-proxy via apps/dsh/settings.yaml — no direct DeepSeek key.
FROM node:22-bookworm-slim

# dsh engines: node ^22.19 || >=24. Pin the exact published version; bump
# deliberately (npm view @deepseek-ai/dsh version).
ARG DSH_VERSION=0.1.2-rc.1
RUN npm install -g "@deepseek-ai/dsh@${DSH_VERSION}" \
    && npm cache clean --force

# Sessions, profile and credentials live on the persisted /data volume.
ENV DSH_HOME=/data/dsh

WORKDIR /app
COPY settings.yaml ./seed/settings.yaml
COPY entrypoint.sh ./entrypoint.sh
RUN chmod +x ./entrypoint.sh

EXPOSE 3080
ENTRYPOINT ["./entrypoint.sh"]
# dsh deliberately refuses --host 0.0.0.0 (the web UI is an RCE surface). It
# binds 127.0.0.1 only; reach it over an SSH tunnel or an authenticated proxy.
# --trusted-host lets the browser-trust fence accept the tailscale-serve origin
# (https://umbrel.taila13a94.ts.net:3080 -> 127.0.0.1:3080).
CMD ["web", "--port", "3080", "--no-open", \
     "--trusted-host", "umbrel.taila13a94.ts.net", \
     "--trusted-host", "umbrel.taila13a94.ts.net:3080"]
