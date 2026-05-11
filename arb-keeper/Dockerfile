FROM python:3.11-slim
WORKDIR /app

# solders requires Rust at build time for any source installs — use pre-built wheel
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libssl-dev pkg-config \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
CMD ["python", "main.py"]
