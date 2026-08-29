# Build context is the REPO ROOT — this service imports the shared packages:
#   docker build -f apps/refinery/Dockerfile .
FROM python:3.11-slim

WORKDIR /app

# Shared packages first — they change less often than service code, so this
# layer stays cached across service-only edits.
COPY packages/ ./packages/
RUN pip install --no-cache-dir ./packages/swarm-core

# CPU-only torch (sentence-transformers dep) — keep the image lean.
ENV PIP_NO_CACHE_DIR=1 \
    PYTHONUNBUFFERED=1 \
    HF_HOME=/models \
    SENTENCE_TRANSFORMERS_HOME=/models

COPY apps/refinery/requirements.txt .
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu \
 && pip install --no-cache-dir -r requirements.txt

# Pre-download the embedding model at build time so first boot is fast and offline.
RUN python -c "from sentence_transformers import SentenceTransformer; \
    SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')"

COPY apps/refinery/ .

CMD ["python", "main.py"]
