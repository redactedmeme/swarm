# Build context is the REPO ROOT — this service imports the shared packages:
#   docker build -f apps/settler/Dockerfile .
FROM python:3.11-slim

WORKDIR /app

# Shared packages first — they change less often than service code, so this
# layer stays cached across service-only edits. The [solana] extra pulls
# solders/solana/anchorpy for the burn transaction path.
COPY packages/ ./packages/
RUN pip install --no-cache-dir "./packages/swarm-core[solana]"

COPY apps/settler/ .

CMD ["python", "-u", "app.py"]
