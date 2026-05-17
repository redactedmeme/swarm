"""
webchat/server.py — redacted-chan web chat proxy service.

This service is intentionally stateless and holds NO LLM API keys,
vault data, or soul content. It only proxies authenticated requests
to the redacted-chan-bot internal data proxy.

Environment variables required:
  WEB_PASSWORD            — password users enter on the login screen
  WEB_SECRET              — secret key for signing JWT tokens
  REDACTED_CHAN_INTERNAL_URL — e.g. http://localhost:8080
  DATA_PROXY_TOKEN        — bearer token for the internal data proxy
"""

import asyncio
import json
import os
import time
import logging
import uuid
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import AsyncIterator

import httpx
import jwt
from fastapi import FastAPI, Request, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────

WEB_PASSWORD = os.getenv("WEB_PASSWORD", "")
WEB_SECRET = os.getenv("WEB_SECRET", "changeme")
INTERNAL_URL = os.getenv("REDACTED_CHAN_INTERNAL_URL", "http://localhost:8080")
DATA_PROXY_TOKEN = os.getenv("DATA_PROXY_TOKEN", "")
PROXY_INTERNAL_URL = os.getenv("PROXY_INTERNAL_URL", "")   # e.g. http://redacted-proxy.railway.internal:7080
PROXY_TOKEN = os.getenv("PROXY_TOKEN", "")

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

_STATIC_DIR = Path("static")

# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok"}


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
    session_id = str(uuid.uuid4())
    logger.info("[webchat] login success")
    return {"token": token, "session_id": session_id}


_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
_IMAGE_MIME = {
    ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
    ".png": "image/png", ".gif": "image/gif", ".webp": "image/webp",
}

@app.post("/upload")
async def upload(request: Request):
    """Accept a file upload. Images → base64 data URL. Text files → extracted text."""
    authorization = request.headers.get("Authorization", "")
    _validate_token(authorization)

    form = await request.form()
    file = form.get("file")
    if not file:
        raise HTTPException(status_code=400, detail="no file")

    filename = file.filename or "file"
    ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""

    # Images — return as base64 data URL (4 MB max)
    if ext in _IMAGE_EXTS:
        content_bytes = await file.read(max_size=4 * 1024 * 1024)
        import base64
        b64 = base64.b64encode(content_bytes).decode("ascii")
        mime = _IMAGE_MIME.get(ext, "image/jpeg")
        data_url = f"data:{mime};base64,{b64}"
        logger.info(f"[webchat] image upload: {filename} ({len(content_bytes)} bytes)")
        return {"name": filename, "type": "image", "data": data_url}

    # Text files (512 KB max)
    content_bytes = await file.read(max_size=512 * 1024)
    text = ""
    if ext in (".txt", ".md", ".py", ".js", ".ts", ".json", ".csv"):
        try:
            text = content_bytes.decode("utf-8", errors="replace")
        except Exception:
            text = ""
    elif ext == ".pdf":
        try:
            import re as _re
            raw = content_bytes.decode("latin-1", errors="replace")
            chunks = _re.findall(r'BT\s*(.*?)\s*ET', raw, _re.DOTALL)
            parts = []
            for chunk in chunks:
                strings = _re.findall(r'\((.*?)\)', chunk)
                parts.extend(strings)
            text = " ".join(parts)[:8000]
        except Exception:
            text = ""
    else:
        try:
            text = content_bytes.decode("utf-8", errors="replace")
        except Exception:
            text = ""

    text = text[:8000]
    logger.info(f"[webchat] text upload: {filename} → {len(text)} chars")
    return {"name": filename, "type": "text", "data": text}


class ChatRequest(BaseModel):
    message: str
    session_id: str = ""
    history: list = []
    image_data: str = ""   # base64 data URL for image attachments


@app.get("/proxy-config")
async def proxy_config_get(request: Request):
    """Fetch current proxy privacy config — requires login."""
    authorization = request.headers.get("Authorization", "")
    _validate_token(authorization)
    if not PROXY_INTERNAL_URL:
        raise HTTPException(status_code=503, detail="proxy not configured")
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{PROXY_INTERNAL_URL}/config",
                headers={"Authorization": f"Bearer {PROXY_TOKEN}"},
            )
        return resp.json()
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


class ProxyConfigUpdate(BaseModel):
    privacy_mode:   str | None = None
    log_level:      str | None = None
    privacy_scrub:  bool | None = None
    ephemeral_mode: bool | None = None


@app.post("/proxy-config")
async def proxy_config_post(body: ProxyConfigUpdate, request: Request):
    """Update proxy privacy config at runtime — requires login."""
    authorization = request.headers.get("Authorization", "")
    _validate_token(authorization)
    if not PROXY_INTERNAL_URL:
        raise HTTPException(status_code=503, detail="proxy not configured")
    payload = {k: v for k, v in body.model_dump().items() if v is not None}
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"{PROXY_INTERNAL_URL}/config",
                json=payload,
                headers={"Authorization": f"Bearer {PROXY_TOKEN}", "Content-Type": "application/json"},
            )
        return resp.json()
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


@app.get("/chan/mood")
async def chan_mood(request: Request):
    authorization = request.headers.get("Authorization", "")
    _validate_token(authorization)
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(
            f"{INTERNAL_URL}/proxy/mood",
            headers={"Authorization": f"Bearer {DATA_PROXY_TOKEN}"},
        )
    return resp.json()


@app.get("/chan/facts")
async def chan_facts(request: Request):
    authorization = request.headers.get("Authorization", "")
    _validate_token(authorization)
    limit = int(request.query_params.get("limit", 20))
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(
            f"{INTERNAL_URL}/proxy/facts",
            params={"limit": limit},
            headers={"Authorization": f"Bearer {DATA_PROXY_TOKEN}"},
        )
    return resp.json()


@app.get("/chan/anticipation")
async def chan_anticipation(request: Request):
    authorization = request.headers.get("Authorization", "")
    _validate_token(authorization)
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(
            f"{INTERNAL_URL}/proxy/anticipation",
            headers={"Authorization": f"Bearer {DATA_PROXY_TOKEN}"},
        )
    return resp.json()


@app.get("/api/swarm/activity")
async def api_swarm_activity(request: Request):
    authorization = request.headers.get("Authorization", "")
    _validate_token(authorization)
    n = int(request.query_params.get("n", 60))
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{INTERNAL_URL}/proxy/swarm/activity",
                params={"n": n},
                headers={"Authorization": f"Bearer {DATA_PROXY_TOKEN}"},
            )
        return resp.json()
    except Exception as e:
        return JSONResponse({"messages": [], "error": str(e)})


@app.get("/api/swarm/pending")
async def api_swarm_pending(request: Request):
    authorization = request.headers.get("Authorization", "")
    _validate_token(authorization)
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{INTERNAL_URL}/proxy/swarm/pending",
                headers={"Authorization": f"Bearer {DATA_PROXY_TOKEN}"},
            )
        return resp.json()
    except Exception as e:
        return JSONResponse({"pending": {}, "error": str(e)})


@app.get("/chan/heartbeats")
async def chan_heartbeats(request: Request):
    authorization = request.headers.get("Authorization", "")
    _validate_token(authorization)
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{INTERNAL_URL}/proxy/heartbeats",
                headers={"Authorization": f"Bearer {DATA_PROXY_TOKEN}"},
            )
        return resp.json()
    except Exception as e:
        return JSONResponse({"agents": [], "error": str(e)})


@app.get("/chan/vault")
async def chan_vault(request: Request):
    authorization = request.headers.get("Authorization", "")
    _validate_token(authorization)
    n = int(request.query_params.get("n", 30))
    category = request.query_params.get("category", "")
    params = {"n": n}
    if category:
        params["category"] = category
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{INTERNAL_URL}/proxy/vault/entries",
                params=params,
                headers={"Authorization": f"Bearer {DATA_PROXY_TOKEN}"},
            )
        return resp.json()
    except Exception as e:
        return JSONResponse({"entries": [], "error": str(e)})


@app.get("/chan/heatmap")
async def chan_heatmap(request: Request):
    authorization = request.headers.get("Authorization", "")
    _validate_token(authorization)
    n = int(request.query_params.get("n", 20))
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(
            f"{INTERNAL_URL}/proxy/heatmap",
            params={"n": n},
            headers={"Authorization": f"Bearer {DATA_PROXY_TOKEN}"},
        )
    return resp.json()


@app.get("/proxy-logs")
async def proxy_logs(request: Request):
    authorization = request.headers.get("Authorization", "")
    _validate_token(authorization)
    if not PROXY_INTERNAL_URL:
        return JSONResponse({"entries": []})
    n = int(request.query_params.get("n", 500))
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{PROXY_INTERNAL_URL}/logs",
                params={"n": n},
                headers={"Authorization": f"Bearer {PROXY_TOKEN}"},
            )
        return resp.json()
    except Exception:
        return JSONResponse({"entries": []})


@app.post("/hermes/chat")
async def hermes_chat(body: ChatRequest, request: Request):
    """Dispatch a task to Hermes via chan-bot's data_proxy → Redis SwarmInbox."""
    authorization = request.headers.get("Authorization", "")
    _validate_token(authorization)

    client_ip = request.client.host if request.client else "unknown"
    if not _check_rate_limit(client_ip):
        raise HTTPException(status_code=429, detail="rate limit exceeded")

    try:
        async with httpx.AsyncClient(timeout=70.0) as client:
            resp = await client.post(
                f"{INTERNAL_URL}/proxy/hermes/task",
                json={"message": body.message, "session_id": body.session_id},
                headers={"Authorization": f"Bearer {DATA_PROXY_TOKEN}", "Content-Type": "application/json"},
            )
        return resp.json()
    except httpx.TimeoutException:
        return JSONResponse({"response": "Hermes timed out — check the swarm feed or Telegram.", "agent": "hermes", "timeout": True})
    except Exception as e:
        return JSONResponse({"response": f"Hermes unavailable: {e}", "agent": "hermes"}, status_code=503)


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
        "image_data": body.image_data,
    }
    headers = {
        "Authorization": f"Bearer {DATA_PROXY_TOKEN}",
        "Content-Type": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=90.0) as client:
            resp = await client.post(f"{INTERNAL_URL}/proxy/chat", json=payload, headers=headers)
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


# ── SSE streaming chat ────────────────────────────────────────────────────────

async def _stream_text(text: str, chunk_size: int = 4) -> AsyncIterator[str]:
    """Yield SSE events by splitting text into small word-boundary chunks."""
    words = text.split(" ")
    buf: list[str] = []
    for word in words:
        buf.append(word)
        if len(buf) >= chunk_size:
            chunk = " ".join(buf) + " "
            yield f"data: {json.dumps({'delta': chunk})}\n\n"
            buf = []
            await asyncio.sleep(0.01)
    if buf:
        yield f"data: {json.dumps({'delta': ' '.join(buf)})}\n\n"
    yield f"data: {json.dumps({'done': True})}\n\n"


@app.post("/chat/stream")
async def chat_stream(body: ChatRequest, request: Request):
    """Streaming SSE variant of /chat. Returns text/event-stream."""
    authorization = request.headers.get("Authorization", "")
    _validate_token(authorization)

    client_ip = request.client.host if request.client else "unknown"
    if not _check_rate_limit(client_ip):
        raise HTTPException(status_code=429, detail="rate limit exceeded")

    payload = {
        "message": body.message,
        "session_id": body.session_id,
        "history": body.history,
        "image_data": body.image_data,
    }
    headers = {
        "Authorization": f"Bearer {DATA_PROXY_TOKEN}",
        "Content-Type": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=95.0) as client:
            resp = await client.post(f"{INTERNAL_URL}/proxy/chat", json=payload, headers=headers)
        if resp.status_code != 200:
            async def _err():
                yield f"data: {json.dumps({'error': 'unavailable'})}\n\n"
            return StreamingResponse(_err(), media_type="text/event-stream")
        data = resp.json()
        response_text = data.get("response", "")
        session_id = data.get("session_id", body.session_id)
        # Prepend session_id as first event
        async def _gen():
            yield f"data: {json.dumps({'session_id': session_id})}\n\n"
            async for chunk in _stream_text(response_text):
                yield chunk
        return StreamingResponse(_gen(), media_type="text/event-stream", headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        })
    except httpx.TimeoutException:
        async def _timeout():
            yield f"data: {json.dumps({'error': 'timeout'})}\n\n"
        return StreamingResponse(_timeout(), media_type="text/event-stream")
    except Exception as e:
        logger.error(f"[webchat] stream error: {e}")
        async def _exc():
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
        return StreamingResponse(_exc(), media_type="text/event-stream")


# ── WebSocket chat ─────────────────────────────────────────────────────────────

@app.websocket("/ws/chat")
async def ws_chat(websocket: WebSocket):
    """WebSocket chat channel — token passed as query param ?token=..."""
    token = websocket.query_params.get("token", "")
    try:
        jwt.decode(token, WEB_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.InvalidTokenError:
        await websocket.close(code=4001)
        return

    await websocket.accept()
    try:
        while True:
            raw = await websocket.receive_text()
            try:
                body = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_json({"error": "invalid json"})
                continue

            payload = {
                "message": body.get("message", ""),
                "session_id": body.get("session_id", ""),
                "history": body.get("history", []),
                "image_data": body.get("image_data", ""),
            }
            headers = {
                "Authorization": f"Bearer {DATA_PROXY_TOKEN}",
                "Content-Type": "application/json",
            }
            try:
                async with httpx.AsyncClient(timeout=95.0) as client:
                    resp = await client.post(f"{INTERNAL_URL}/proxy/chat", json=payload, headers=headers)
                data = resp.json()
                response_text = data.get("response", "")
                session_id = data.get("session_id", payload["session_id"])
                # Stream tokens over WS
                words = response_text.split(" ")
                buf: list[str] = []
                for word in words:
                    buf.append(word)
                    if len(buf) >= 4:
                        await websocket.send_json({"delta": " ".join(buf) + " "})
                        buf = []
                        await asyncio.sleep(0.01)
                if buf:
                    await websocket.send_json({"delta": " ".join(buf)})
                await websocket.send_json({"done": True, "session_id": session_id})
            except Exception as e:
                await websocket.send_json({"error": str(e)})
    except WebSocketDisconnect:
        pass


# ── API: agents ───────────────────────────────────────────────────────────────

_AGENTS_CONFIG = [
    {"id": "chan",     "redis_id": "redacted-chan", "label": "redacted-chan",    "icon": "⬡",  "role": "core",    "description": "Emotional memory + relational AI",               "llm": None},
    {"id": "hermes",   "redis_id": "hermes",        "label": "hermes-bot",       "icon": "⚡", "role": "agent",   "description": "Autonomous task agent with web/exec/search tools", "llm": os.getenv("HERMES_LLM_LABEL", "openai/gpt-oss-120b")},
    {"id": "smolting", "redis_id": "smolting",      "label": "smolting",          "icon": "🌱", "role": "agent",   "description": "Moltbook TPD trader — Telegram-based",             "llm": "llama-3.1-8b-instant"},
    {"id": "builder",  "redis_id": "builder",       "label": "RedactedBuilder",   "icon": "🔧", "role": "agent",   "description": "Infrastructure + deployment builder",              "llm": "claude-haiku-4-5"},
    {"id": "proxy",    "redis_id": None,            "label": "redacted-proxy",    "icon": "🛡",  "role": "infra",   "description": "Privacy-first LLM routing proxy",                  "llm": "—"},
    {"id": "runtime",  "redis_id": "runtime",       "label": "swarm-runtime",     "icon": "⚙",  "role": "infra",   "description": "Sub-agent orchestration runtime",                  "llm": "—"},
]


@app.get("/api/agents")
async def api_agents(request: Request):
    authorization = request.headers.get("Authorization", "")
    _validate_token(authorization)

    # Fetch Redis heartbeat data for all agents
    heartbeat_map: dict[str, dict] = {}
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            hb_resp = await client.get(
                f"{INTERNAL_URL}/proxy/heartbeats",
                headers={"Authorization": f"Bearer {DATA_PROXY_TOKEN}"},
            )
        hb_data = hb_resp.json()
        for entry in hb_data.get("agents", []):
            heartbeat_map[entry["id"]] = entry
    except Exception:
        pass

    agents = []
    for cfg in _AGENTS_CONFIG:
        rid = cfg.get("redis_id")
        hb = heartbeat_map.get(rid) if rid else None
        if hb:
            if hb.get("online"):
                status = "online"
            elif not hb.get("present") or hb.get("age_s") is None:
                status = "unknown"
            else:
                status = "offline"
            age_s = hb.get("age_s")
            if age_s is not None:
                if age_s < 60:
                    last_seen = f"{age_s}s ago"
                elif age_s < 3600:
                    last_seen = f"{age_s // 60}m ago"
                else:
                    last_seen = f"{age_s // 3600}h ago"
            else:
                last_seen = "never"
        else:
            status = "unknown"
            last_seen = None

        # Use LLM from heartbeat if available (heartbeat data_proxy reads env vars), else fallback to config
        llm = cfg["llm"]
        if hb and hb.get("llm"):
            llm = hb["llm"]
        # Infra-only services (no heartbeat) show as "infra" not "unknown"
        if cfg.get("redis_id") is None:
            status = "infra"
            last_seen = None
        agents.append({
            "id": cfg["id"],
            "label": cfg["label"],
            "icon": cfg["icon"],
            "role": cfg["role"],
            "description": cfg["description"],
            "llm": llm or "—",
            "status": status,
            "last_seen": last_seen,
        })
    return {"agents": agents}


# ── API: modes ────────────────────────────────────────────────────────────────

_AVAILABLE_MODES = [
    {"id": "standard",  "label": "Standard",  "description": "Default balanced mode",           "icon": "💬"},
    {"id": "focused",   "label": "Focused",   "description": "Minimal context, faster replies",  "icon": "🎯"},
    {"id": "deep",      "label": "Deep",      "description": "Full memory + arc context active", "icon": "🌊"},
    {"id": "creative",  "label": "Creative",  "description": "Higher temperature, exploratory",  "icon": "🎨"},
]

_current_mode = {"active": "standard"}


@app.get("/api/modes")
async def api_modes_get(request: Request):
    authorization = request.headers.get("Authorization", "")
    _validate_token(authorization)
    return {"modes": _AVAILABLE_MODES, "active": _current_mode["active"]}


class ModeUpdate(BaseModel):
    mode: str


@app.post("/api/modes")
async def api_modes_set(body: ModeUpdate, request: Request):
    authorization = request.headers.get("Authorization", "")
    _validate_token(authorization)
    valid_ids = {m["id"] for m in _AVAILABLE_MODES}
    if body.mode not in valid_ids:
        raise HTTPException(status_code=400, detail=f"unknown mode: {body.mode}")
    _current_mode["active"] = body.mode
    return {"active": body.mode}


# ── API: tool approval queue ──────────────────────────────────────────────────

_tool_queue: list[dict] = []


@app.get("/api/tools/pending")
async def api_tools_pending(request: Request):
    authorization = request.headers.get("Authorization", "")
    _validate_token(authorization)
    return {"pending": _tool_queue}


class ToolDecision(BaseModel):
    tool_id: str
    approved: bool
    reason: str = ""


@app.post("/api/tools/decide")
async def api_tools_decide(body: ToolDecision, request: Request):
    authorization = request.headers.get("Authorization", "")
    _validate_token(authorization)
    global _tool_queue
    _tool_queue = [t for t in _tool_queue if t.get("id") != body.tool_id]
    logger.info(f"[webchat] tool decision: {body.tool_id} → {'approved' if body.approved else 'rejected'}")
    return {"ok": True}


# ── API: settings (alias for proxy-config) ─────────────────────────────────────

@app.get("/api/settings")
async def api_settings_get(request: Request):
    authorization = request.headers.get("Authorization", "")
    _validate_token(authorization)
    if not PROXY_INTERNAL_URL:
        return {"proxy_configured": False, "mode": "standard"}
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{PROXY_INTERNAL_URL}/config",
                headers={"Authorization": f"Bearer {PROXY_TOKEN}"},
            )
        return {**resp.json(), "proxy_configured": True}
    except Exception:
        return {"proxy_configured": False}


# ── SPA catch-all — must be registered LAST ───────────────────────────────────

@app.get("/{full_path:path}")
async def serve_spa(full_path: str):
    """Serve React build assets; fall back to index.html for client-side routes."""
    candidate = _STATIC_DIR / full_path
    if candidate.is_file():
        return FileResponse(candidate)
    index = _STATIC_DIR / "index.html"
    if index.exists():
        return FileResponse(index)
    return JSONResponse({"detail": "not found"}, status_code=404)
