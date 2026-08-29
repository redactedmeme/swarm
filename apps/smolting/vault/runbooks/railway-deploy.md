# Railway Deployment Runbook

---

## Services

| Service | Directory | Start Command | Status |
|---------|-----------|---------------|--------|
| smolting-telegram-bot | `smolting-telegram-bot/` | `python main.py` | ✅ LIVE |
| redactedbuilder-bot | (separate repo) | `python main.py` | ✅ LIVE |
| hermes-deployment | (separate repo) | — | ✅ LIVE |
| redacteddegen-service | `redacteddegen-service/` | `python main.py` | 🔨 Not deployed |

---

## Deploy a New Service

1. Create directory with `Dockerfile` + `.railway/railway.toml`
2. Set env vars in Railway dashboard
3. Link GitHub repo → Railway auto-deploys on push to `main`

**Standard `railway.toml`:**
```toml
[build]
builder = "NIXPACKS"

[deploy]
startCommand = "python main.py"
restartPolicyType = "ON_FAILURE"
restartPolicyMaxRetries = 3
```

**Standard `Dockerfile`:**
```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["python", "main.py"]
```

---

## Health Checks

All services expose `GET /health` → 200 OK. Configure in Railway dashboard under service settings.

---

## Volume Mounts

GnosisAccelerator and state files need Railway persistent volumes.  
Mount at `/data` → set `STATE_PATH=/data/...` env var.

---

## Restart Policy

`ON_FAILURE` with max 3 retries. After 3 failures Railway stops the service — check logs in dashboard.

---

## Logs

Railway dashboard → service → Deployments → View Logs.  
Or via CLI: `railway logs --service <name>`

---

## Webhook vs Polling

| Mode | Trigger | Config |
|------|---------|--------|
| Webhook (production) | `WEBHOOK_URL` env var set | Faster, Railway-recommended |
| Polling (local dev) | No `WEBHOOK_URL` | `application.run_polling()` |

smolting-telegram-bot auto-detects based on `WEBHOOK_URL` env var.
