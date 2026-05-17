"""
Sub-Agent Service — FastAPI app for redacted-chan's factual research intern.
"""

import json
import os
import time
import uuid
import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, Depends
from pydantic import BaseModel

import router
import scheduler
from auth import verify_token

# ── Redis heartbeat helpers ───────────────────────────────────────────────────

REDIS_URL         = os.getenv("REDIS_URL", "redis://localhost:6379")
HEARTBEAT_PREFIX  = "swarm:heartbeat:"
HEARTBEAT_TTL     = 600   # 10 min — bots announce every 2 min so key stays fresh

# In-memory mesh peer table (nodeId → last seen unix ts)
_mesh_peers: dict[str, dict] = {}


def _hb_key(node_id: str) -> str:
    return f"{HEARTBEAT_PREFIX}{node_id}"


async def _redis_write_hb(node_id: str, metadata: dict | None = None) -> None:
    try:
        import redis.asyncio as aioredis
        r = aioredis.from_url(REDIS_URL, decode_responses=True)
        payload = json.dumps({
            "agent": node_id,
            "ts":    time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "unix":  time.time(),
            **(metadata or {}),
        })
        await r.set(_hb_key(node_id), payload, ex=HEARTBEAT_TTL)
        await r.aclose()
    except Exception as e:
        logger.debug(f"[hb] redis write failed for {node_id}: {e}")


async def _self_heartbeat_loop() -> None:
    """Write runtime's own heartbeat every 2 min so webchat shows it online."""
    while True:
        await _redis_write_hb("runtime", {"service": "swarm-runtime", "role": "sub-agent"})
        await asyncio.sleep(120)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# ── Async task store ──────────────────────────────────────────────────────────

_async_tasks: dict[str, dict] = {}

# ── Request / Response models ─────────────────────────────────────────────────

class TaskRequest(BaseModel):
    task: str
    task_type: Optional[str] = None
    context: Optional[dict] = None

class TaskResponse(BaseModel):
    result: str
    task_type: str
    emotional_flag: bool = False
    emotional_reason: str = ""
    model_used: str = ""
    latency_ms: int = 0
    sources_used: list[str] = []

class AsyncTaskStatus(BaseModel):
    task_id: str
    status: str
    result: Optional[TaskResponse] = None


# ── Task dispatch ─────────────────────────────────────────────────────────────

TASK_HANDLERS = {
    "vault_search":    "tasks.vault_search",
    "memory_search":   "tasks.memory_search",
    "sentiment":       "tasks.sentiment",
    "deep_sentiment":  "tasks.deep_sentiment",
    "summarize_url":   "tasks.summarize_url",
    "research":        "tasks.research",
    "web_research":    "tasks.web_research",
    "deep_research":   "tasks.deep_research",
    "pattern_detect":  "tasks.pattern_detect",
    "context_brief":   "tasks.context_brief",
    "fact_audit":      "tasks.fact_audit",
    "vault_audit":     "tasks.vault_audit",
    "daily_digest":    "tasks.daily_digest",
}


async def _dispatch(req: TaskRequest) -> TaskResponse:
    start = time.monotonic()
    task_type = req.task_type or router.detect_type(req.task)

    module_name = TASK_HANDLERS.get(task_type, "tasks.research")
    try:
        import importlib
        mod = importlib.import_module(module_name)
        result, model_used, sources = await mod.run(req.task, req.context or {})
    except Exception as e:
        logger.warning(f"[dispatch] {task_type} failed: {e}")
        result = "Task failed. Check service logs for details."
        model_used = ""
        sources = []

    latency = int((time.monotonic() - start) * 1000)
    return TaskResponse(
        result=result,
        task_type=task_type,
        model_used=model_used,
        latency_ms=latency,
        sources_used=sources,
    )


# ── Lifecycle ─────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler.start()
    asyncio.create_task(_self_heartbeat_loop())
    logger.info("[sub-agent-service] online")
    yield
    logger.info("[sub-agent-service] shutting down")


app = FastAPI(title="redacted-chan sub-agent", lifespan=lifespan)


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {
        "status": "ok",
        "tasks_available": list(TASK_HANDLERS.keys()),
    }


@app.post("/task", response_model=TaskResponse, dependencies=[Depends(verify_token)])
async def run_task(req: TaskRequest):
    return await _dispatch(req)


@app.post("/task/async", dependencies=[Depends(verify_token)])
async def run_task_async(req: TaskRequest):
    task_id = str(uuid.uuid4())[:8]
    _async_tasks[task_id] = {"status": "pending", "result": None}

    async def _bg():
        try:
            resp = await _dispatch(req)
            _async_tasks[task_id] = {"status": "done", "result": resp.model_dump()}
        except Exception as e:
            logger.warning(f"[async_task] {task_id} failed: {e}")
            _async_tasks[task_id] = {"status": "error", "result": "Task failed. Check service logs."}

    asyncio.create_task(_bg())
    return {"task_id": task_id, "status": "pending"}


@app.get("/task/{task_id}", dependencies=[Depends(verify_token)])
async def get_task_result(task_id: str):
    entry = _async_tasks.get(task_id)
    if not entry:
        return {"status": "not_found"}
    return entry


@app.get("/scheduled/latest/{name}", dependencies=[Depends(verify_token)])
async def get_scheduled_result(name: str):
    result = scheduler.get_latest(name)
    if not result:
        return {"status": "no_result", "name": name}
    return result


# ── Swarm mesh bridge ─────────────────────────────────────────────────────────
# Hermes and smolting POST /announce every 2 min. We write their heartbeat to
# Redis so the webchat /agents page shows them as online.

@app.post("/announce")
async def mesh_announce(body: dict):
    node_id = body.get("nodeId", "")
    if not node_id:
        return {"ok": False, "error": "missing nodeId"}
    metadata = {
        "role":         body.get("role", ""),
        "capabilities": body.get("capabilities", []),
    }
    _mesh_peers[node_id] = {"last_seen": time.time(), **metadata}
    await _redis_write_hb(node_id, metadata)
    logger.info(f"[mesh] {node_id} announced ({body.get('role', '?')})")
    return {"ok": True, "nodeId": node_id}


@app.get("/messages/{node_id}")
async def mesh_get_messages(node_id: str):
    # No active message queuing yet — return empty so bots don't error out.
    return {"messages": []}


@app.post("/message/{target}")
async def mesh_send_message(target: str, body: dict):
    # Stub — log and discard until a real queue is needed.
    logger.debug(f"[mesh] message to {target} from {body.get('from', '?')}: {body.get('type', '?')}")
    return {"ok": True}
