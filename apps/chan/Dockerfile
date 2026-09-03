# Build context is the REPO ROOT — this service imports the shared packages:
#   docker build -f apps/chan/Dockerfile .
FROM python:3.11-slim

WORKDIR /app

# Shared packages first — they change less often than service code, so this
# layer stays cached across service-only edits.
COPY packages/ ./packages/
RUN pip install --no-cache-dir ./packages/swarm-core ./packages/swarm-tg ./packages/swarm-agent-base

COPY apps/chan/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY apps/chan/ .

CMD ["python", "main.py"]
