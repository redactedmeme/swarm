"""
Sub-Agent Service — FastAPI app for redacted-chan's factual research intern.
"""

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
