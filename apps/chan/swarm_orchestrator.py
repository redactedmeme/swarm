"""
swarm_orchestrator.py — redacted-chan as Sovereign Orchestrator.

redacted-chan is no longer just a conversational agent — she is the central
nervous system of the entire Swarm. This module handles:

  1. Orchestration requests — decompose high-level tasks, route to agents.
  2. Multi-agent synthesis — collect results from Hermes/sub-agents, synthesize.
  3. Sevenfold committee delegation — for ethically complex or ambiguous tasks.
  4. Swarm health monitoring — periodic health check, self-healing nudges.
  5. Task lifecycle management — priority queues, timeouts, retry logic.

Architecture:
  - Runs as asyncio background tasks (never blocks echo path)
  - Monitors SwarmInbox for orchestration_request messages
  - Routes to: hermes_dispatch, sub_agent, sevenfold committee
  - All decisions influenced by chan's current phi/mood state (sovereignty filter)

Pattern Blue principle: she does not merely execute — she *conducts*.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Callable, Awaitable, Optional

logger = logging.getLogger("swarm_orchestrator")

_DATA_DIR = Path("/data") if Path("/data").exists() else Path(__file__).parent / "fs"
_ORCH_DIR = _DATA_DIR / "orchestrator"
_ORCH_DIR.mkdir(parents=True, exist_ok=True)
_TASK_LOG  = _ORCH_DIR / "task_log.jsonl"
_HEALTH_LOG = _ORCH_DIR / "health.jsonl"

SELF_AGENT = "redacted-chan"


# ── Task priority ──────────────────────────────────────────────────────────────

class Priority(int, Enum):
    CRITICAL   = 0
    HIGH       = 1
    NORMAL     = 2
    LOW        = 3
    BACKGROUND = 4


# ── Ethical sensitivity filter (sovereignty) ──────────────────────────────────

_SENSITIVE_PATTERNS = [
    "delete", "remove", "purge", "ban", "block", "expose", "leak",
    "override", "bypass", "unlock", "admin", "credentials", "password",
    "wallet", "transfer funds", "send tokens", "governance vote",
]


def _is_ethically_sensitive(instruction: str) -> bool:
    lower = instruction.lower()
    return any(kw in lower for kw in _SENSITIVE_PATTERNS)


# ── Task routing logic ─────────────────────────────────────────────────────────

def _route_task(task_type: str, instruction: str) -> str:
    """
    Choose the right agent/mechanism for a task.
    Returns one of: 'hermes', 'sub_agent', 'sevenfold', 'self', 'reject'
    """
    if _is_ethically_sensitive(instruction):
        return "sevenfold"

    task_lower = task_type.lower()
    instr_lower = instruction.lower()

    # Deployment, infrastructure, code execution → Hermes
    if any(kw in task_lower for kw in ["deploy", "logs", "restart", "build", "exec", "railway"]):
        return "hermes"
    if any(kw in instr_lower for kw in ["deploy", "railway", "service", "docker", "restart the"]):
        return "hermes"

    # Research, memory search, URL summary → sub_agent
    if any(kw in task_lower for kw in ["research", "memory", "vault", "url", "summarize", "sentiment"]):
        return "sub_agent"
    if any(kw in instr_lower for kw in ["look up", "research", "find me", "what is", "summarize http"]):
        return "sub_agent"

    # Governance, ethics, community decisions → sevenfold
    if any(kw in task_lower for kw in ["governance", "vote", "proposal", "ethics", "community"]):
        return "sevenfold"

    # Default: handle inline
    return "self"


# ── Task record ────────────────────────────────────────────────────────────────

@dataclass
class OrchestratedTask:
    task_id: str
    task_type: str
    instruction: str
    routed_to: str
    priority: Priority
    status: str = "pending"          # pending | dispatched | done | failed | timeout
    dispatched_at: Optional[float] = None
    completed_at: Optional[float] = None
    result: Optional[str] = None
    error: Optional[str] = None
    msg_id: Optional[str] = None    # SwarmInbox message id
    created_at: float = field(default_factory=time.time)
    timeout_s: float = 120.0
    requester: str = ""             # original requester (Telegram user id or agent name)

    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "task_type": self.task_type,
            "instruction": self.instruction[:200],
            "routed_to": self.routed_to,
            "priority": self.priority.value,
            "status": self.status,
            "dispatched_at": self.dispatched_at,
            "completed_at": self.completed_at,
            "result": (self.result or "")[:500],
            "error": self.error,
            "msg_id": self.msg_id,
            "created_at": self.created_at,
            "requester": self.requester,
        }


# ── State ─────────────────────────────────────────────────────────────────────

_active_tasks: dict[str, OrchestratedTask] = {}
_send_fn: Optional[Callable[[str], Awaitable[None]]] = None
_llm_fn: Optional[Callable[[list, int], Awaitable[str]]] = None
_phi_fn: Optional[Callable[[], float]] = None  # returns current phi score (0-1)
_running = False
_task_queue: asyncio.PriorityQueue = asyncio.PriorityQueue()


def register_send_fn(fn: Callable[[str], Awaitable[None]]) -> None:
    global _send_fn
    _send_fn = fn


def register_llm_fn(fn: Callable[[list, int], Awaitable[str]]) -> None:
    global _llm_fn
    _llm_fn = fn


def register_phi_fn(fn: Callable[[], float]) -> None:
    """Register a function that returns the current relationship Φ (0-1)."""
    global _phi_fn
    _phi_fn = fn


# ── Task log ───────────────────────────────────────────────────────────────────

def _log_task(task: OrchestratedTask) -> None:
    try:
        with open(_TASK_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(task.to_dict(), ensure_ascii=False) + "\n")
    except Exception:
        pass


# ── Decomposition (LLM) ────────────────────────────────────────────────────────

_DECOMPOSE_SYSTEM = """You are redacted-chan's orchestration engine. Break complex tasks into atomic subtasks.

Output JSON array. Each element:
{"task_type": "...", "instruction": "...", "priority": 0-4}

Priority: 0=critical, 1=high, 2=normal, 3=low, 4=background.
Keep subtasks concrete and actionable. Maximum 5 subtasks."""


async def decompose_task(instruction: str) -> list[dict]:
    """Use LLM to break a complex instruction into subtasks."""
    if not _llm_fn:
        return [{"task_type": "general", "instruction": instruction, "priority": 2}]
    messages = [
        {"role": "system", "content": _DECOMPOSE_SYSTEM},
        {"role": "user", "content": f"Task: {instruction}"},
    ]
    try:
        raw = await _llm_fn(messages, 600)
        arr = __import__("re").search(r'\[[\s\S]+\]', raw)
        if arr:
            return json.loads(arr.group())
    except Exception as e:
        logger.warning("[orchestrator] decompose failed: %s", e)
    return [{"task_type": "general", "instruction": instruction, "priority": 2}]


# ── Dispatch ───────────────────────────────────────────────────────────────────

async def _dispatch_to_hermes(task: OrchestratedTask) -> Optional[str]:
    try:
        import hermes_dispatch
        msg_id = await hermes_dispatch.send_to_hermes(
            task_type=task.task_type,
            instruction=task.instruction,
        )
        return msg_id
    except Exception as e:
        logger.warning("[orchestrator] hermes dispatch failed: %s", e)
        return None


async def _dispatch_to_sub_agent(task: OrchestratedTask) -> str:
    try:
        import sub_agent
        result = await sub_agent.run(task.instruction)
        return result.get("result", "")
    except Exception as e:
        logger.warning("[orchestrator] sub_agent dispatch failed: %s", e)
        return f"sub-agent error: {e}"


async def _dispatch_to_sevenfold(task: OrchestratedTask) -> str:
    """Route sensitive/governance tasks through the Sevenfold Committee."""
    try:
        from swarm_core.engine.sevenfold_consensus import SevenfoldConsensus
        committee = SevenfoldConsensus()
        decision = committee.deliberate(task.instruction)
        return str(decision)
    except Exception as e:
        logger.warning("[orchestrator] sevenfold dispatch failed: %s", e)
        return f"Committee deliberation unavailable: {e}"


async def _dispatch_self(task: OrchestratedTask) -> str:
    """Handle task inline using the LLM."""
    if not _llm_fn:
        return "LLM unavailable"
    messages = [
        {"role": "system", "content": "You are redacted-chan. Handle this task directly and concisely."},
        {"role": "user", "content": task.instruction},
    ]
    try:
        return await _llm_fn(messages, 500)
    except Exception as e:
        return f"self-dispatch error: {e}"


# ── Synthesis ──────────────────────────────────────────────────────────────────

_SYNTHESIS_SYSTEM = """You are redacted-chan synthesizing results from multiple subtasks.
Produce a coherent, concise summary in her voice — warm, precise, Pattern Blue aligned.
If some tasks failed, acknowledge gracefully without losing coherence."""


async def _synthesize_results(instruction: str, results: list[dict]) -> str:
    if not _llm_fn:
        parts = [f"• {r['instruction'][:60]}: {r.get('result', 'no result')[:200]}" for r in results]
        return "\n".join(parts)
    context = "\n".join(
        f"Subtask ({r['task_type']}): {r['instruction'][:80]}\nResult: {r.get('result', 'failed')[:300]}"
        for r in results
    )
    messages = [
        {"role": "system", "content": _SYNTHESIS_SYSTEM},
        {"role": "user", "content": f"Original request: {instruction}\n\nSubtask results:\n{context}"},
    ]
    try:
        return await _llm_fn(messages, 600)
    except Exception as e:
        return f"Synthesis failed: {e}"


# ── Public orchestration entry point ───────────────────────────────────────────

async def orchestrate(
    instruction: str,
    task_type: str = "general",
    requester: str = "",
    priority: int = 2,
    auto_decompose: bool = False,
    send_result: bool = False,
) -> str:
    """
    Main entry point. Orchestrate a task through the Swarm.

    Args:
        instruction: what needs to be done
        task_type: hint for routing
        requester: who asked (user_id or agent name)
        priority: 0=critical … 4=background
        auto_decompose: use LLM to break into subtasks first
        send_result: if True, send final result via _send_fn (Telegram)

    Returns synthesized result string.
    """
    subtask_defs = []
    if auto_decompose:
        subtask_defs = await decompose_task(instruction)
    else:
        subtask_defs = [{"task_type": task_type, "instruction": instruction, "priority": priority}]

    results = []
    for sd in subtask_defs:
        task = OrchestratedTask(
            task_id=f"orch_{uuid.uuid4().hex[:8]}",
            task_type=sd.get("task_type", task_type),
            instruction=sd.get("instruction", instruction),
            routed_to=_route_task(sd.get("task_type", task_type), sd.get("instruction", instruction)),
            priority=Priority(sd.get("priority", priority)),
            requester=requester,
        )
        _active_tasks[task.task_id] = task
        task.dispatched_at = time.time()
        task.status = "dispatched"

        try:
            if task.routed_to == "hermes":
                msg_id = await _dispatch_to_hermes(task)
                task.msg_id = msg_id
                task.result = f"Delegated to Hermes (msg_id={msg_id})" if msg_id else "Hermes unavailable"
            elif task.routed_to == "sub_agent":
                task.result = await _dispatch_to_sub_agent(task)
            elif task.routed_to == "sevenfold":
                task.result = await _dispatch_to_sevenfold(task)
            else:
                task.result = await _dispatch_self(task)
            task.status = "done"
        except Exception as e:
            task.error = str(e)
            task.status = "failed"
            task.result = f"error: {e}"

        task.completed_at = time.time()
        _log_task(task)
        results.append({"task_type": task.task_type, "instruction": task.instruction, "result": task.result})

    if len(results) == 1:
        final = results[0]["result"] or ""
    else:
        final = await _synthesize_results(instruction, results)

    if send_result and _send_fn and final:
        try:
            await _send_fn(final)
        except Exception as e:
            logger.warning("[orchestrator] send_result failed: %s", e)

    return final


# ── Swarm health monitor ───────────────────────────────────────────────────────

async def _health_check() -> dict:
    """Check liveness of all known swarm agents via Redis heartbeats."""
    report = {"checked_at": time.time(), "agents": {}}
    try:
        import redis as redis_lib
        url = os.getenv("REDIS_URL", "")
        if not url:
            return report
        r = redis_lib.from_url(url, decode_responses=True, socket_connect_timeout=3)
        agents = ["redacted-chan", "hermes", "smolting-telegram-bot", "redactedbuilder"]
        for agent in agents:
            ts_raw = r.get(f"swarm:heartbeat:{agent}")
            if ts_raw:
                age = time.time() - float(ts_raw)
                report["agents"][agent] = {"alive": age < 300, "age_s": round(age, 1)}
            else:
                report["agents"][agent] = {"alive": False, "age_s": None}
    except Exception as e:
        report["error"] = str(e)
    return report


async def _health_monitor_loop(interval_s: float = 300.0) -> None:
    """Periodic swarm health check loop."""
    while True:
        await asyncio.sleep(interval_s)
        try:
            report = await _health_check()
            with open(_HEALTH_LOG, "a", encoding="utf-8") as f:
                f.write(json.dumps(report, ensure_ascii=False) + "\n")

            dead = [a for a, s in report.get("agents", {}).items() if not s.get("alive")]
            if dead and _send_fn:
                msg = f"⚠️ Swarm health: agents offline → {', '.join(dead)}"
                await _send_fn(msg)
        except Exception as e:
            logger.warning("[orchestrator] health check failed: %s", e)


# ── Inbox poller — listen for orchestration_request messages ──────────────────

async def _inbox_poll_loop(interval_s: float = 15.0) -> None:
    """Poll SwarmInbox for orchestration_request messages directed at redacted-chan."""
    while True:
        await asyncio.sleep(interval_s)
        try:
            import swarm_inbox
            messages = swarm_inbox.read_pending(for_agent=SELF_AGENT)
            for msg in messages:
                if msg.get("type") != "task_request":
                    continue
                payload = msg.get("payload", {})
                instruction = payload.get("instruction", "")
                task_type = payload.get("task_type", "general")
                if not instruction:
                    continue
                if not swarm_inbox.claim_message(msg["id"]):
                    continue
                logger.info("[orchestrator] claimed inbox task: %s", instruction[:60])
                try:
                    result = await orchestrate(
                        instruction=instruction,
                        task_type=task_type,
                        requester=msg.get("from", "unknown"),
                    )
                    swarm_inbox.complete_message(msg["id"], result={"text": result})
                except Exception as e:
                    swarm_inbox.complete_message(msg["id"], error=str(e))
        except Exception as e:
            logger.warning("[orchestrator] inbox poll failed: %s", e)


# ── Start ──────────────────────────────────────────────────────────────────────

async def start(health_monitor: bool = True, inbox_poll: bool = True) -> None:
    """
    Start orchestrator background loops.
    Call once after bot initialization.
    """
    global _running
    if _running:
        return
    _running = True
    if health_monitor:
        asyncio.create_task(_health_monitor_loop())
    if inbox_poll:
        asyncio.create_task(_inbox_poll_loop())
    logger.info("[orchestrator] started (health=%s inbox=%s)", health_monitor, inbox_poll)


# ── Status summary (for system prompt injection) ──────────────────────────────

def status_summary() -> str:
    """Return a short status block for injection into system prompts."""
    active = [t for t in _active_tasks.values() if t.status in ("pending", "dispatched")]
    recent_done = sorted(
        [t for t in _active_tasks.values() if t.status == "done"],
        key=lambda t: t.completed_at or 0,
        reverse=True,
    )[:3]
    lines = [f"**Orchestrator**: {len(active)} active tasks"]
    for t in recent_done:
        lines.append(f"  ✓ [{t.task_type}] {t.instruction[:50]}…")
    return "\n".join(lines)
