FROM python:3.11-slim

WORKDIR /app

# CPU-only torch (sentence-transformers dep) — keep the image lean.
ENV PIP_NO_CACHE_DIR=1 \
    PYTHONUNBUFFERED=1 \
    HF_HOME=/models \
    SENTENCE_TRANSFORMERS_HOME=/models

COPY requirements.txt .
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu \
 && pip install --no-cache-dir -r requirements.txt

# Pre-download the embedding model at build time so first boot is fast and offline.
RUN python -c "from sentence_transformers import SentenceTransformer; \
    SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')"

COPY . .

CMD ["python", "main.py"]
