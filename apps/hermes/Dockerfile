# Build context is the REPO ROOT — this service imports the shared packages:
#   docker build -f apps/hermes/Dockerfile .
FROM python:3.11-slim

WORKDIR /app

# Shared packages first — they change less often than service code, so this
# layer stays cached across service-only edits.
COPY packages/ ./packages/
RUN pip install --no-cache-dir ./packages/swarm-core ./packages/swarm-tg

# Install deps
COPY apps/hermes/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy everything
COPY apps/hermes/ .

ENV PYTHONUNBUFFERED=1
ENV ORACLE_STATE_DIR=/data

COPY apps/hermes/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

CMD ["/entrypoint.sh"]
