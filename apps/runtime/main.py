"""
Sub-Agent Service — FastAPI app for redacted-chan's factual research intern.
Hyperbolic kernel provides manifold-based task placement and organism health.
"""

import sys
import json
import os
import time
import uuid
import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Depends
from pydantic import BaseModel


import router
import scheduler
from auth import verify_token
from swarm_core.kernel.hyperbolic_kernel import HyperbolicKernel, HealthStatus

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


async def _redis_write_doors(node_id: str, capabilities: list) -> None:
    """Persist each announced capability as a door.

    A heartbeat says the announce loop ran; a door says a named capability is
    being asserted. Announce-driven on purpose — the agent asserts its own
    doors, so no reader of these keys needs an outbound-request capability.
    """
    if not capabilities:
        return
    try:
        import redis.asyncio as aioredis
        from swarm_core.swarm_heartbeat import build_door_payload, door_redis_key

        r = aioredis.from_url(REDIS_URL, decode_responses=True)
        for cap in capabilities:
            if isinstance(cap, dict):
                name, kind, is_open = cap.get("name"), cap.get("kind", ""), cap.get("open", True)
            else:
                name, kind, is_open = cap, "", True
            if not name:
                continue
            payload = json.dumps(build_door_payload(str(name), str(kind), bool(is_open)))
            await r.set(door_redis_key(node_id, str(name)), payload, ex=HEARTBEAT_TTL)
        await r.aclose()
    except Exception as e:
        logger.debug(f"[hb] redis door write failed for {node_id}: {e}")


async def _self_heartbeat_loop() -> None:
    """Write runtime's own heartbeat every 2 min so webchat shows it online."""
    while True:
        await _redis_write_hb("runtime", {"service": "swarm-runtime", "role": "sub-agent"})
        await asyncio.sleep(120)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# ── Hyperbolic kernel (singleton) ─────────────────────────────────────────────

_kernel: HyperbolicKernel | None = None

def get_kernel() -> HyperbolicKernel:
    global _kernel
    if _kernel is None:
        _kernel = HyperbolicKernel(curvature_initial=13.0)
    return _kernel

# ── Async task store ──────────────────────────────────────────────────────────

_async_tasks: dict[str, dict] = {}
_task_tiles: dict[str, tuple] = {}  # task_id → tile (x, y) coord

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


_TASK_WEIGHTS = {
    "deep_research":  "agent",
    "deep_sentiment": "agent",
    "pattern_detect": "ritual",
    "vault_search":   "sigil",
    "memory_search":  "sigil",
    "sentiment":      "ritual",
    "research":       "agent",
    "web_research":   "agent",
    "summarize_url":  "ritual",
    "context_brief":  "ritual",
    "fact_audit":     "agent",
    "vault_audit":    "sigil",
    "daily_digest":   "agent",
}

_TASK_TIMEOUT = int(os.getenv("TASK_TIMEOUT_SEC", "120"))


async def _dispatch(req: TaskRequest, task_id: str | None = None) -> TaskResponse:
    start = time.monotonic()
    task_type = req.task_type or router.detect_type(req.task)
    kernel = get_kernel()

    # Place task on manifold
    process_type = _TASK_WEIGHTS.get(task_type, "agent")
    tile_coord = await kernel.schedule_process({
        "type":      process_type,
        "task_type": task_type,
        "task_id":   task_id or "sync",
        "state":     "RUNNING",
    })
    tile_key = (round(tile_coord.x, 6), round(tile_coord.y, 6))
    if task_id:
        _task_tiles[task_id] = tile_key

    module_name = TASK_HANDLERS.get(task_type, "tasks.research")
    result = model_used = ""
    sources: list[str] = []
    timed_out = False

    try:
        import importlib
        mod = importlib.import_module(module_name)
        result, model_used, sources = await asyncio.wait_for(
            mod.run(req.task, req.context or {}),
            timeout=_TASK_TIMEOUT,
        )
    except asyncio.TimeoutError:
        timed_out = True
        result = f"Task timed out after {_TASK_TIMEOUT}s."
        logger.warning(f"[dispatch] {task_type} timed out — degrading tile {tile_key}")
    except Exception as e:
        logger.warning(f"[dispatch] {task_type} failed: {e}")
        result = "Task failed. Check service logs for details."

    # Mark tile done or degrade it on failure/timeout
    async with kernel._manifold_lock:
        tile = kernel.tiles.get(tile_key)
        if tile:
            if timed_out:
                tile.corruption_level = min(1.0, tile.corruption_level + 0.25)
                tile.health = HealthStatus.DEGRADED
            else:
                tile.data = {"process": "EMPTY", "state": "READY"}
                tile.corruption_level = max(0.0, tile.corruption_level - 0.05)

    latency = int((time.monotonic() - start) * 1000)
    return TaskResponse(
        result=result,
        task_type=task_type,
        model_used=model_used,
        latency_ms=latency,
        sources_used=sources,
    )


# ── Lifecycle ─────────────────────────────────────────────────────────────────

async def _publish_capabilities() -> None:
    """Publish swarm-runtime capabilities to Redis for agent discovery."""
    redis_url = os.getenv("REDIS_URL", "")
    if not redis_url:
        return
    try:
        import json
        import redis.asyncio as aioredis
        caps = list(TASK_HANDLERS.keys())
        r = aioredis.from_url(redis_url, decode_responses=True)
        await r.set("swarm:caps:swarm-runtime", json.dumps(caps), ex=86400)
        await r.aclose()
        logger.info("[caps] published capabilities: %s", caps)
    except Exception as e:
        logger.warning("[caps] capability publish failed: %s", e)


@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler.start()
    asyncio.create_task(_self_heartbeat_loop())
    asyncio.create_task(_publish_capabilities())
    kernel = get_kernel()
    await kernel.start_lifecycle(tick_rate=1.0)
    logger.info("[sub-agent-service] online — hyperbolic kernel started (%d tiles)", len(kernel.tiles))
    yield
    await kernel.stop_lifecycle()
    logger.info("[sub-agent-service] shutting down")


app = FastAPI(title="redacted-chan sub-agent", lifespan=lifespan)


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    kernel = get_kernel()
    organism = await kernel.get_organism_status()
    return {
        "status": "ok",
        "tasks_available": list(TASK_HANDLERS.keys()),
        "kernel": {
            "alive": organism.get("status") == "alive",
            "tiles": organism.get("total_tiles", 0),
            "atp_reserve": round(organism.get("atp_reserve", 0), 1),
            "dna_generation": organism.get("dna_generation", 0),
        },
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
            resp = await _dispatch(req, task_id=task_id)
            _async_tasks[task_id] = {"status": "done", "result": resp.model_dump()}
        except Exception as e:
            logger.warning(f"[async_task] {task_id} failed: {e}")
            _async_tasks[task_id] = {"status": "error", "result": "Task failed. Check service logs."}
        finally:
            _task_tiles.pop(task_id, None)

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


# ── Kernel status ─────────────────────────────────────────────────────────────

@app.get("/kernel/status")
async def kernel_status():
    kernel = get_kernel()
    status = await kernel.get_organism_status()
    status["active_tasks"] = len(_task_tiles)
    status["tile_count"] = len(kernel.tiles)
    return status


@app.get("/kernel/tiles")
async def kernel_tiles():
    """Return a summary of all tiles for visualisation."""
    kernel = get_kernel()
    async with kernel._manifold_lock:
        tiles = []
        for (x, y), tile in kernel.tiles.items():
            tiles.append({
                "x": round(x, 4),
                "y": round(y, 4),
                "health": tile.health.value,
                "process": tile.data.get("process", "EMPTY"),
                "task_type": tile.data.get("task_type", ""),
                "corruption": round(tile.corruption_level, 3),
                "age": round(tile.age, 1),
                "atp": round(tile.metabolism.atp, 1),
                "curvature_pressure": round(tile.curvature_pressure, 3),
            })
    return {"tiles": tiles}


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
    await _redis_write_doors(node_id, metadata.get("capabilities") or [])
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
