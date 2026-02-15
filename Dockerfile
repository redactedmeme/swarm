# Dockerfile — Final Railway version for Pattern Blue Swarm
FROM ollama/ollama:latest

WORKDIR /app

# Install Python + venv
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 python3-pip python3-venv \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Create venv
RUN python3 -m venv /app/venv
ENV PATH="/app/venv/bin:$PATH"

# Upgrade pip
RUN pip install --upgrade pip setuptools wheel

# Copy & install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY agents/ ./agents/
COPY config/ ./config/
COPY main.py .
COPY supervisor.py .

# Create volume directories
RUN mkdir -p /app/shards /app/manifold-memory /root/.ollama

# Environment
ENV PYTHONUNBUFFERED=1 \
    OLLAMA_HOST=http://localhost:11434 \
    OLLAMA_MODEL=phi3:mini \
    USE_EXTERNAL_LLM=false \
    SOLANA_RPC_URL=https://api.devnet.solana.com \
    PORT=8000

EXPOSE 11434 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:${PORT}/health || exit 1

# Start Ollama + supervisor
CMD ["sh", "-c", "ollama serve & \
    sleep 10 && \
    (ollama list | grep -q ${OLLAMA_MODEL} || ollama pull ${OLLAMA_MODEL}) && \
    python supervisor.py"]
