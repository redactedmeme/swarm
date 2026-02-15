# Pattern Blue Swarm Railway Optimized Dockerfile
# - Uses official ollama/ollama:latest base (pre-installed Ollama)
# - Creates venv to avoid externally-managed-environment error
# - Runtime model pull (persists via volume)
# - Minimal footprint for Railway hobby tier

FROM ollama/ollama:latest

# Metadata
LABEL maintainer="Pattern Blue Swarm <@RedactedMemeFi>"
LABEL description="Railway-optimized Pattern Blue swarm - lightweight agents + Ollama"

WORKDIR /app

# Install Python + venv tools (Ubuntu Noble base)
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 \
    python3-pip \
    python3-venv \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Create and activate virtual environment
RUN python3 -m venv /app/venv
ENV PATH="/app/venv/bin:$PATH"

# Upgrade pip in venv
RUN pip install --upgrade pip setuptools wheel

# Copy and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source
COPY agents/ ./agents/
COPY config/ ./config/
COPY main.py .
COPY supervisor.py .
COPY railway.json .   # optional, but you had it
# COPY railway.toml .   # optional - remove if not used

# Create directories for persistent volumes
RUN mkdir -p /app/shards \
    /app/manifold-memory \
    /root/.ollama

# Environment variables (overridable in Railway UI or railway.json)
ENV PYTHONUNBUFFERED=1 \
    OLLAMA_HOST=http://localhost:11434 \
    OLLAMA_MODEL=phi3:mini \
    USE_EXTERNAL_LLM=false \
    SOLANA_RPC_URL=https://api.devnet.solana.com \
    PORT=8000

# Expose Ollama + app ports
EXPOSE 11434 8000

# Healthcheck using your FastAPI /health endpoint
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:${PORT}/health || exit 1

# Runtime: start Ollama serve → pull model if missing → supervisor
CMD ["sh", "-c", "ollama serve & \
    sleep 10 && \
    (ollama list | grep -q ${OLLAMA_MODEL} || ollama pull ${OLLAMA_MODEL}) && \
    python supervisor.py"]
