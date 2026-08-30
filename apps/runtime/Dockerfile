# Build context is the REPO ROOT — this service imports the shared packages:
#   docker build -f apps/runtime/Dockerfile .
FROM python:3.11-slim

WORKDIR /app

# Shared packages first — they change less often than service code, so this
# layer stays cached across service-only edits.
COPY packages/ ./packages/
RUN pip install --no-cache-dir ./packages/swarm-core

COPY apps/runtime/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY apps/runtime/ .

# Bind loopback, not 0.0.0.0: the container runs on the host network and
# tailscaled already holds <tailscale-ip>:3000 for `tailscale serve`, so a
# 0.0.0.0 bind collides with it and uvicorn exits at startup. serve proxies
# to 127.0.0.1:3000, which is what this now listens on.
CMD ["uvicorn", "main:app", "--host", "127.0.0.1", "--port", "3000"]
