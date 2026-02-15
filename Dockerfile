# Dockerfile for Pattern Blue Swarm - Railway Optimized Variant
# - Slim base (python:3.11-slim-bookworm)
# - Tiny Ollama model pre-pulled (phi3:mini ~2.5GB)
# - Multi-agent supervisor in single container
# - Volumes for persistence: Ollama models, shards, manifold-memory
# - Fast build, low memory footprint for Railway hobby tier

FROM python:3.11-slim-bookworm

# Metadata
LABEL maintainer="Pattern Blue Swarm <@RedactedMemeFi>"
LABEL description="Railway-optimized Pattern Blue swarm - lightweight agents + tiny Ollama"

# Set working directory
WORKDIR /app

# Install system dependencies (minimal set)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    git \
    libssl-dev \
    pkg-config \
    ca-certificates \
    && curl -fsSL https://ollama.com/install.sh | sh \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Copy only essential files first (optimizes layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code (agents, config, supervisor)
COPY agents/ ./agents/
COPY config/ ./config/
COPY main.py .
COPY supervisor.py .

# Pre-pull tiny model during build (speeds first boot, keeps image ~3GB)
# phi3:mini is ~2.5GB quantized, fast on CPU, good for Railway
RUN ollama serve & \
    sleep 10 && \
    ollama pull phi3:mini && \
    killall ollama

# Create directories for volume mounts (Railway will mount over them)
RUN mkdir -p /app/shards \
    /app/manifold-memory \
    /root/.ollama

# Environment variables (defaults, can be overridden in railway.json or UI)
ENV PYTHONUNBUFFERED=1 \
    OLLAMA_HOST=http://localhost:11434 \
    OLLAMA_MODEL=phi3:mini \
    USE_EXTERNAL_LLM=false \
    SOLANA_RPC_URL=https://api.devnet.solana.com \
    PORT=8000

# Expose port (if any API/terminal endpoint exists; optional)
EXPOSE 8000

# Healthcheck (Railway uses this for readiness)
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:${PORT}/health || exit 1

# Entry point: supervisor runs agents + optional Ollama serve
CMD ["python", "supervisor.py"]
