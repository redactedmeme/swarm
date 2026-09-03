# Build context is the REPO ROOT — this service imports the shared packages:
#   docker build -f apps/smolting/Dockerfile .
FROM python:3.11-slim

WORKDIR /app

# Shared packages first — they change less often than service code, so this
# layer stays cached across service-only edits.
COPY packages/ ./packages/
RUN pip install --no-cache-dir ./packages/swarm-core ./packages/swarm-tg ./packages/swarm-agent-base

COPY apps/smolting/requirements.txt .
RUN pip install --no-cache-dir \
    "python-telegram-bot[webhooks,job-queue]==20.7" \
    "aiohttp==3.9.1" \
    "requests==2.31.0" \
    "python-dotenv==1.0.0" \
    "pyyaml>=6.0" \
    "APScheduler>=3.10" \
    "openai>=1.6.1" \
    "groq>=0.4.0" \
    "redis>=5.0.0"

COPY apps/smolting/ .

# smolting bundles its own copy of the markdown vault; point swarm_core at it
# rather than the repo-root vault/, which is not in this image.
ENV SWARM_VAULT_DIR=/app/vault
ENV PYTHONUNBUFFERED=1

CMD ["python", "main.py"]
