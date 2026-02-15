# Stage 1: Builder with Rust + Python deps
FROM python:3.11-slim-bookworm AS builder

WORKDIR /app

# Install build deps + Rust
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libssl-dev \
    pkg-config \
    curl \
    && curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y \
    && rm -rf /var/lib/apt/lists/*

# Activate Rust (correct sh syntax)
ENV PATH="/root/.cargo/bin:${PATH}"
RUN rustup default stable

# Create venv
RUN python -m venv /app/venv
ENV PATH="/app/venv/bin:$PATH"

# Upgrade pip
RUN pip install --upgrade pip setuptools wheel

# Copy & install requirements (loose solders to allow build)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Stage 2: Ollama base + copied venv
FROM ollama/ollama:latest

WORKDIR /app

# Copy venv from builder
COPY --from=builder /app/venv /app/venv
ENV PATH="/app/venv/bin:$PATH"

# Copy source
COPY agents/ ./agents/
COPY config/ ./config/
COPY main.py .
COPY supervisor.py .

# Volume dirs
RUN mkdir -p /app/shards /app/manifold-memory /root/.ollama

ENV PYTHONUNBUFFERED=1 \
    OLLAMA_HOST=http://localhost:11434 \
    OLLAMA_MODEL=phi3:mini \
    USE_EXTERNAL_LLM=false \
    SOLANA_RPC_URL=https://api.devnet.solana.com \
    PORT=8000

EXPOSE 11434 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:${PORT}/health || exit 1

CMD ["sh", "-c", "ollama serve & \
    sleep 8 && \
    (ollama list | grep -q ${OLLAMA_MODEL} || ollama pull ${OLLAMA_MODEL}) && \
    python supervisor.py"]
