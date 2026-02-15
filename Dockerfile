# Dockerfile - Railway Optimized Pattern Blue Swarm
# Base: official Ollama image (Ollama binary pre-installed)
# Runtime model pull + persistent volume for ~/.ollama
# Python agents + supervisor in same container
# Minimal footprint for Railway hobby tier

FROM ollama/ollama:latest

# Metadata
LABEL maintainer="Pattern Blue Swarm <@RedactedMemeFi>"
LABEL description="Railway-optimized Pattern Blue swarm - agents on official Ollama base"

# Set working directory for Python code
WORKDIR /app

# Install minimal Python + pip (bookworm base has python3)
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 \
    python3-pip \
    python3-venv \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Copy and install requirements (cached layer)
COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt

# Copy source (agents, config, main, supervisor)
COPY agents/ ./agents/
COPY config/ ./config/
COPY main.py .
COPY supervisor.py .

# Ensure volume directories exist (Railway mounts over them)
RUN mkdir -p /app/shards \
    /app/manifold-memory \
    /root/.ollama

# Environment defaults (overridable in railway.json or UI)
ENV PYTHONUNBUFFERED=1 \
    OLLAMA_HOST=http://localhost:11434 \
    OLLAMA_MODEL=phi3:mini \
    USE_EXTERNAL_LLM=false \
    SOLANA_RPC_URL=https://api.devnet.solana.com \
    PORT=8000

# Expose Ollama (11434) + app port (8000)
EXPOSE 11434 8000

# Healthcheck: use your FastAPI /health endpoint
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:${PORT}/health || exit 1

# Runtime entrypoint: start Ollama serve → pull model (if not present) → supervisor
CMD ["sh", "-c", "ollama serve & \
    sleep 8 && \
    (ollama list | grep -q ${OLLAMA_MODEL} || ollama pull ${OLLAMA_MODEL}) && \
    python3 supervisor.py"]
