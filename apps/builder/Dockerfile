# Build context is the REPO ROOT — this service imports the shared packages:
#   docker build -f apps/builder/Dockerfile .
#
# It did NOT used to. builder built from its own directory, which was fine
# while swarm_inbox.py / task_client.py were hand-synced copies. 3a56377 turned
# both into re-export shims over swarm_core / swarm_tg, and from that moment a
# rebuild of this image produced a container that died at main.py:46 with
# ModuleNotFoundError: no swarm_core. The running container predated the shim,
# so nothing broke until someone rebuilt. Changing the context is what makes
# the shims real here — the compose entry must point at the repo root to match.
FROM python:3.11-slim

WORKDIR /app

# Shared packages first (change less often than service code).
COPY packages/ ./packages/
RUN pip install --no-cache-dir ./packages/swarm-core ./packages/swarm-tg ./packages/swarm-agent-base

COPY apps/builder/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Canonical character roster (agent_registry.load reads agents/** under SWARM_REPO_ROOT).
COPY agents/ ./agents/
COPY apps/builder/ .

ENV PYTHONUNBUFFERED=1
ENV SWARM_REPO_ROOT=/app

CMD ["python", "main.py"]
