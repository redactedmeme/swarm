"""
webchat/server.py — redacted-chan web chat proxy service.

This service is intentionally stateless and holds NO LLM API keys,
vault data, or soul content. It only proxies authenticated requests
to the redacted-chan-bot internal data proxy.

Environment variables required:
  WEB_PASSWORD            — password users enter on the login screen
  WEB_SECRET              — secret key for signing JWT tokens
  REDACTED_CHAN_INTERNAL_URL — e.g. http://redacted-chan-bot.railway.internal:8080
  DATA_PROXY_TOKEN        — bearer token for the internal data proxy
"""

import os
import time
import logging
from collections import defaultdict
from datetime import datetime, timezone, timedelta

import httpx
import jwt
from fastapi import FastAPI, Request, Response, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────

WEB_PASSWORD = os.getenv("WEB_PASSWORD", "")
WEB_SECRET = os.getenv("WEB_SECRET", "changeme")
INTERNAL_URL = os.getenv("REDACTED_CHAN_INTERNAL_URL", "http://redacted-chan-bot.railway.internal:8080")
DATA_PROXY_TOKEN = os.getenv("DATA_PROXY_TOKEN", "")

JWT_ALGORITHM = "HS256"
JWT_EXPIRY_HOURS = 24

# ── Rate limiter (in-memory, per IP) ─────────────────────────────────────────

# Stores list of request timestamps per IP
_rate_limit_store: dict[str, list[float]] = defaultdict(list)
RATE_LIMIT_MAX = 30       # requests
RATE_LIMIT_WINDOW = 60    # seconds


def _check_rate_limit(ip: str) -> bool:
    """Return True if the request is allowed, False if rate limit exceeded."""
    now = time.monotonic()
    window_start = now - RATE_LIMIT_WINDOW
    timestamps = _rate_limit_store[ip]
    # Evict old entries
    _rate_limit_store[ip] = [t for t in timestamps if t > window_start]
    if len(_rate_limit_store[ip]) >= RATE_LIMIT_MAX:
        return False
    _rate_limit_store[ip].append(now)
    return True


# ── JWT helpers ───────────────────────────────────────────────────────────────

def _mint_token() -> str:
    payload = {
        "sub": "webchat",
        "exp": datetime.now(timezone.utc) + timedelta(hours=JWT_EXPIRY_HOURS),
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, WEB_SECRET, algorithm=JWT_ALGORITHM)


def _validate_token(authorization: str) -> bool:
    """Validate a Bearer JWT. Returns True if valid, raises HTTPException otherwise."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="missing token")
    token = authorization[len("Bearer "):]
    try:
        jwt.decode(token, WEB_SECRET, algorithms=[JWT_ALGORITHM])
        return True
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="invalid token")


# ── App ───────────────────────────────────────────────────────────────────────

app = FastAPI(title="redacted-chan webchat", docs_url=None, redoc_url=None)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

# Mount static files (index.html etc.)
app.mount("/static", StaticFiles(directory="static"), name="static")


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/")
async def root():
    """Serve the main chat UI."""
    return FileResponse("static/index.html")


class LoginRequest(BaseModel):
    password: str


@app.post("/login")
async def login(body: LoginRequest):
    """Validate password and return a signed JWT."""
    if not WEB_PASSWORD:
        raise HTTPException(status_code=500, detail="server misconfigured: WEB_PASSWORD not set")
    if body.password != WEB_PASSWORD:
        raise HTTPException(status_code=401, detail="wrong password")
    token = _mint_token()
    logger.info("[webchat] login success")
    return {"token": token}


class ChatRequest(BaseModel):
    message: str
    session_id: str = ""
    history: list = []


@app.post("/chat")
async def chat(body: ChatRequest, request: Request):
    """Proxy an authenticated chat message to the internal redacted-chan data proxy."""
    # Auth
    authorization = request.headers.get("Authorization", "")
    _validate_token(authorization)

    # Rate limit by client IP
    client_ip = request.client.host if request.client else "unknown"
    if not _check_rate_limit(client_ip):
        raise HTTPException(status_code=429, detail="rate limit exceeded — slow down")

    # Forward to internal API
    payload = {
        "message": body.message,
        "session_id": body.session_id,
        "history": body.history,
    }
    headers = {
        "Authorization": f"Bearer {DATA_PROXY_TOKEN}",
        "Content-Type": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=90.0) as client:
            resp = await client.post(f"{INTERNAL_URL}/chat", json=payload, headers=headers)
        if resp.status_code != 200:
            logger.warning(f"[webchat] internal API returned {resp.status_code}")
            return JSONResponse({"error": "redacted-chan is unavailable"}, status_code=503)
        return resp.json()
    except httpx.TimeoutException:
        logger.warning("[webchat] internal API timeout")
        return JSONResponse({"error": "redacted-chan is unavailable"}, status_code=503)
    except Exception as e:
        logger.error(f"[webchat] internal API error: {e}")
        return JSONResponse({"error": "redacted-chan is unavailable"}, status_code=503)
