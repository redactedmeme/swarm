FROM python:3.11-slim

WORKDIR /app

# Install hermes-agent + our deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Railway CLI
RUN apt-get update && apt-get install -y curl && \
    curl -fsSL https://railway.com/install.sh | sh && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# Copy everything (config, plugin, legacy files)
COPY . .

# Set up Hermes config and plugin paths
ENV HERMES_CONFIG=/app/cli-config.yaml
ENV HERMES_ENABLE_PROJECT_PLUGINS=1
ENV PYTHONUNBUFFERED=1

# The entrypoint script decides: run hermes gateway if configured, else legacy main.py
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

CMD ["/entrypoint.sh"]
