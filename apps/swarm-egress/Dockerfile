# Build context is the REPO ROOT — imports the shared package:
#   docker build -f apps/swarm-egress/Dockerfile .
FROM python:3.11-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1

COPY packages/ ./packages/
RUN pip install --no-cache-dir ./packages/swarm-core

COPY apps/swarm-egress/ .

CMD ["python", "proxy.py"]
