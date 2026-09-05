# Build context is the REPO ROOT — this service imports swarm_core:
#   docker build -f apps/terminal/Dockerfile .
FROM python:3.11-slim

WORKDIR /app

COPY packages/ ./packages/
RUN pip install --no-cache-dir ./packages/swarm-core

COPY apps/terminal/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY apps/terminal/ .

# Data the terminal reads at runtime and that lives outside the service dir.
COPY agents/ ./agents/
COPY spaces/ ./spaces/
# NB: no top-level `nodes/` — the monorepo reorg moved it to agents/nodes/,
# which arrives with COPY agents/ above. Copying it separately is what made
# this image un-buildable, and is why the service sat on an August build.
COPY skills/ ./skills/
COPY terminal/ ./terminal/
COPY plugins/ ./plugins/

ENV SWARM_REPO_ROOT=/app
ENV PYTHONUNBUFFERED=1

EXPOSE 8080
# Must keep the gevent-websocket worker: the terminal streams over socket.io.
CMD ["sh", "-c", "gunicorn --worker-class geventwebsocket.gunicorn.workers.GeventWebSocketWorker --workers 1 --bind 0.0.0.0:${PORT:-8080} app:app"]
