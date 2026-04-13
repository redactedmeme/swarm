FROM python:3.11-slim

WORKDIR /app

RUN pip install --no-cache-dir flask==3.0.0 flask-cors==4.0.0 requests==2.31.0 apscheduler==3.10.4

COPY app.py .
COPY moltbook_auto.py .
COPY website/ ./website/

RUN mkdir -p fs/swarm_messages

EXPOSE 8080

CMD ["python", "app.py"]
