# Pattern Blue Swarm Railway Optimized Dockerfile
FROM ollama/ollama:latest

WORKDIR /app

# Install Python and system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 \
    python3-pip \
    python3-venv \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Upgrade pip and install Python dependencies
RUN pip3 install --no-cache-dir --upgrade pip

# Copy requirements and install Python packages
COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt

# Copy application source
COPY agents/ ./agents/
COPY config/ ./config/
COPY main.py .
COPY supervisor.py .
COPY railway.json .
COPY railway.toml .

# Create necessary directories for volumes
RUN mkdir -p /app/shards /app/manifold-memory /root/.ollama

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    OLLAMA_HOST=http://localhost:11434 \
    OLLAMA_MODEL=phi3:mini \
    USE_EXTERNAL_LLM=false \
    SOLANA_RPC_URL=https://api.devnet.solana.com \
    PORT=8000

EXPOSE 11434 8000

# Health check for Railway
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:${PORT}/health || exit 1

# Start Ollama serve and main application
CMD ["sh", "-c", "ollama serve & \
     sleep 10 && \
     (ollama list | grep -q ${OLLAMA_MODEL} || ollama pull ${OLLAMA_MODEL}) && \
     python3 -m uvicorn main:app --host 0.0.0.0 --port ${PORT}"]
