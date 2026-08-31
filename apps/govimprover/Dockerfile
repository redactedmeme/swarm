# Build context is the REPO ROOT — this service imports the shared packages:
#   docker build -f apps/govimprover/Dockerfile .
FROM python:3.11-slim

WORKDIR /app

COPY packages/ ./packages/
RUN pip install --no-cache-dir ./packages/swarm-core ./packages/swarm-tg ./packages/swarm-agent-base

COPY apps/govimprover/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Canonical character roster (agent_registry.load reads agents/** under SWARM_REPO_ROOT).
COPY agents/ ./agents/
COPY apps/govimprover/ .

ENV PYTHONUNBUFFERED=1
ENV SWARM_REPO_ROOT=/app

CMD ["python", "main.py"]
