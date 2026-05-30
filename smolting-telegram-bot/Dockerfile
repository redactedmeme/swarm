FROM python:3.11-slim

WORKDIR /app

# Install Tailscale
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates iptables \
    && curl -fsSL https://tailscale.com/install.sh | sh \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir \
    "python-telegram-bot[webhooks,job-queue]==20.7" \
    "aiohttp==3.9.1" \
    "requests==2.31.0" \
    "python-dotenv==1.0.0" \
    "pyyaml>=6.0" \
    "APScheduler>=3.10" \
    "openai>=1.6.1" \
    "groq>=0.4.0" \
    "redis>=5.0.0"

COPY . .
COPY start.sh /start.sh
RUN chmod +x /start.sh

CMD ["/start.sh"]
