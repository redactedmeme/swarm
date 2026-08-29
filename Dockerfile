# Root image: the swarm delegation executor.
#
# NOTE: this is NOT the image for any of the per-service deployments — each
# service has its own Dockerfile under its own directory. Historically this
# image was picked up by mistake for services deployed from the repo root,
# which crash-looped them, because its CMD is the delegation executor and
# nothing else. Check the service's rootDirectory before assuming this builds.
FROM python:3.11-slim

WORKDIR /app
COPY . .

# swarm_core replaces the former repo-root python/ directory.
RUN pip install --no-cache-dir ./packages/swarm-core ./packages/swarm-tg

ENV PYTHONUNBUFFERED=1
ENV LOG_LEVEL=INFO
ENV SWARM_MODE=delegation
ENV SWARM_DATA_DIR=/app/fs

CMD ["python", "-m", "swarm_core.hermes_delegation_executor", \
     "--manifest", "fs/clawtasks_v1.json", "--mode", "dispatch"]
