FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir \
    "python-telegram-bot[webhooks,job-queue]==20.7" \
    "aiohttp==3.9.1" \
    "requests==2.31.0" \
    "python-dotenv==1.0.0" \
    "pyyaml>=6.0" \
    "APScheduler>=3.10" \
    "openai>=1.6.1" \
    "groq>=0.4.0"

COPY . .

CMD ["python", "main.py"]
