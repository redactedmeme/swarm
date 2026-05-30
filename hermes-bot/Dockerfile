FROM python:3.11-slim

WORKDIR /app

# Install Tailscale
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates iptables \
    && curl -fsSL https://tailscale.com/install.sh | sh \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENV PYTHONUNBUFFERED=1
ENV ORACLE_STATE_DIR=/data

CMD ["/entrypoint.sh"]
