FROM python:3.11-slim

WORKDIR /app

# Copy project files
COPY . .

# Install Python dependencies (if they exist)
RUN pip install --no-cache-dir -r requirements.txt 2>/dev/null || echo "No requirements.txt, proceeding with standard library"

# Set environment
ENV PYTHONUNBUFFERED=1
ENV LOG_LEVEL=INFO
ENV SWARM_MODE=delegation

# Run delegation executor
CMD ["python", "python/hermes_delegation_executor.py", "--manifest", "fs/clawtasks_v1.json", "--mode", "dispatch"]
