FROM python:3.11-slim

WORKDIR /app

# Install deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Railway CLI
RUN apt-get update && apt-get install -y curl && \
    curl -fsSL https://railway.com/install.sh | sh && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# Copy everything
COPY . .

ENV PYTHONUNBUFFERED=1
ENV ORACLE_STATE_DIR=/data

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

CMD ["/entrypoint.sh"]
