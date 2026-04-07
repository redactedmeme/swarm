FROM python:3.11-slim

WORKDIR /app

# Install Rust (required for solders build)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl build-essential pkg-config libssl-dev \
    && curl https://sh.rustup.rs -sSf | sh -s -- -y --default-toolchain stable \
    && apt-get clean && rm -rf /var/lib/apt/lists/*
ENV PATH="/root/.cargo/bin:${PATH}"

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy builder source
COPY . .

CMD ["python", "main.py"]
