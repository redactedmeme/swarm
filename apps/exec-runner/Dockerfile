FROM python:3.11-slim

# nsjail is optional — the container + rlimits are the baseline. If the base
# image gains it (or you swap to a distro that packages it) runner.py picks it
# up automatically. Kept out here to keep the image small and buildable offline.

WORKDIR /app
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Drop privileges: the service and every snippet it spawns run as nobody.
RUN install -d -o 65534 -g 65534 /run/exec /tmp
USER 65534:65534

CMD ["python", "app.py"]
