# apps/workspace — persistent per-agent computer (fs + shell + browser).
#
# Build context is the REPO ROOT (it imports swarm_core) — see CLAUDE.md
# "Build contexts". In infra/umbrel/swarm-infra-docker-compose.yml the context
# is /home/umbrel/swarm and dockerfile is apps/workspace/Dockerfile.
#
# Uses the Playwright base image so Chromium + its system libs are already
# present (the browser download needs network at build time regardless of base).
FROM mcr.microsoft.com/playwright/python:v1.47.0-jammy

WORKDIR /app
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1

# Shared packages first so this layer caches across service-only edits.
COPY packages/ ./packages/
RUN pip install --no-cache-dir "./packages/swarm-core[web]"

COPY apps/workspace/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY apps/workspace/ .

# Socket dir + a home for the unprivileged user's data volume mount point.
RUN install -d -m 770 /run/workspace /data

CMD ["python", "app.py"]
