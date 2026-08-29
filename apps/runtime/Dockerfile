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

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "3000"]
