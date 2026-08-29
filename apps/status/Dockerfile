# Build context is the REPO ROOT, not this directory — the service needs
# packages/ alongside its own source:
#   docker build -f apps/status/Dockerfile .
FROM python:3.11-slim

WORKDIR /app

# Shared packages first: they change less often than service code, so the
# dependency layer stays cached across service-only edits.
COPY packages/ ./packages/
RUN pip install --no-cache-dir ./packages/swarm-core

COPY apps/status/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY apps/status/ .

EXPOSE 8098
CMD ["python", "-u", "app.py"]
