"""
swarm_manager.py — Hermes Swarm Manager

Polls the SwarmInbox Redis queue every 60s for task_request messages from
redacted-chan (and other authorized agents), reasons about them using a
Groq tool-calling loop, executes the appropriate tools, and sends results back.

Runs as a separate process alongside main.py (the legacy Hermes Telegram/Moltbook bot).
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("swarm_manager")

# ── Ensure plugins are importable ───────────────────────────────────────────
_APP_DIR = Path(__file__).parent  # /app
sys.path.insert(0, str(_APP_DIR))

# Make the swarm-manager directory importable as a package named swarm_manager
_PLUGIN_DIR = _APP_DIR / "plugins" / "swarm-manager"
sys.path.insert(0, str(_PLUGIN_DIR.parent))  # /app/plugins

# Rename the directory at runtime if needed (dash → underscore for import)
import importlib.util as _ilu

def _import_plugin_module(mod_name: str):
    """Import a module from plugins/swarm-manager/ (handles hyphenated dir name)."""
    spec = _ilu.spec_from_file_location(mod_name, _PLUGIN_DIR / f"{mod_name}.py")
    mod = _ilu.module_from_spec(spec)
    sys.modules[mod_name] = mod
    spec.loader.exec_module(mod)
    return mod

inbox_tools = _import_plugin_module("inbox_tools")
railway_tools = _import_plugin_module("railway_tools")
audit_tools = _import_plugin_module("audit_tools")
health_tools = _import_plugin_module("health_tools")


# ── Tool registry ─────────────────────────────────────────────────────────────

TOOLS: dict[str, dict] = {}        # name → {schema, handler}


class _ToolCtx:
    """Minimal ctx passed to plugin register() functions."""
    def register_tool(self, name: str, toolset: str, schema: dict, handler):
        TOOLS[name] = {"schema": schema, "handler": handler}
        logger.debug("[tools] Registered: %s", name)


def _load_tools():
    ctx = _ToolCtx()
    inbox_tools.register(ctx)
    railway_tools.register(ctx)
    audit_tools.register(ctx)
    health_tools.register(ctx)
    logger.info("[swarm_manager] %d tools loaded: %s", len(TOOLS), list(TOOLS))


def _groq_tool_schemas() -> list[dict]:
    """Convert our tool schemas to Groq/OpenAI tool format."""
    result = []
    for name, t in TOOLS.items():
        s = t["schema"]
        result.append({
            "type": "function",
            "function": {
                "name": name,
                "description": s.get("description", ""),
                "parameters": s.get("parameters", {"type": "object", "properties": {}}),
            },
        })
    return result


def _call_tool(name: str, args: dict) -> str:
    t = TOOLS.get(name)
    if not t:
        return json.dumps({"status": "error", "error": f"Unknown tool: {name}"})
    try:
        return t["handler"](args)
    except Exception as e:
        logger.exception("[tools] Error calling %s", name)
        return json.dumps({"status": "error", "error": str(e)})


# ── Groq agent loop ───────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are Hermes, swarm manager for the REDACTED AI agent collective.
You receive task_request messages from redacted-chan and other agents.
Use your tools to fulfill each request accurately and efficiently.

Available tool categories:
- swarm_read_pending, swarm_send_message, swarm_claim_task, swarm_complete_task, swarm_heartbeat: SwarmInbox operations
- railway_status, railway_logs, railway_restart, railway_deploy: Railway service operations
- swarm_health_check: Check agent heartbeats
- swarm_audit_log: Read operation audit trail

Always respond with concrete results. If a service check is requested, actually call the tool and return the output.
After completing a task, call swarm_complete_task with the result.
"""

MAX_TOOL_ROUNDS = 8


def _get_groq_client():
    try:
        from groq import Groq
        return Groq(api_key=os.getenv("GROQ_API_KEY", ""))
    except ImportError:
        logger.error("[groq] groq package not installed")
        return None


async def _run_agent_loop(instruction: str, msg_id: str, task_type: str, service: str | None) -> dict:
    """Run a Groq tool-calling loop to fulfill one task."""
    client = _get_groq_client()
    if not client:
        return {"status": "error", "error": "Groq client unavailable"}

    service_hint = f"\nTarget service: {service}" if service else ""
    user_msg = f"Task (id={msg_id}, type={task_type}){service_hint}\nInstruction: {instruction}"

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_msg},
    ]
    tools = _groq_tool_schemas()

    final_text = ""
    tool_results: list[dict] = []

    for round_num in range(MAX_TOOL_ROUNDS):
        try:
            resp = await asyncio.to_thread(
                client.chat.completions.create,
                model=os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile"),
                messages=messages,
                tools=tools,
                tool_choice="auto",
                max_tokens=2048,
                temperature=0.3,
            )
        except Exception as e:
            logger.error("[agent] Groq API error (round %d): %s", round_num, e)
            return {"status": "error", "error": str(e)}

        choice = resp.choices[0]
        msg = choice.message
        messages.append(msg.model_dump(exclude_none=True))

        # No tool calls → done
        if not msg.tool_calls:
            final_text = msg.content or ""
            break

        # Execute all tool calls
        for tc in msg.tool_calls:
            fn_name = tc.function.name
            try:
                fn_args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                fn_args = {}

            logger.info("[agent] Tool call: %s(%s)", fn_name, json.dumps(fn_args)[:200])
            result_str = _call_tool(fn_name, fn_args)
            tool_results.append({"tool": fn_name, "args": fn_args, "result": result_str})

            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": result_str,
            })

        if choice.finish_reason == "stop":
            break

    result = {
        "status": "ok",
        "instruction": instruction,
        "task_type": task_type,
        "service": service,
        "summary": final_text,
        "tool_calls": len(tool_results),
        "tools_used": list({t["tool"] for t in tool_results}),
        "details": tool_results[-3:] if tool_results else [],  # last 3 tool results
    }
    return result


# ── Main polling loop ─────────────────────────────────────────────────────────

POLL_INTERVAL = 60  # seconds
ALLOWED_SENDERS = {"redacted-chan"}


async def _process_message(msg: dict) -> None:
    msg_id = msg["id"]
    payload = msg.get("payload", {})
    from_agent = msg.get("from", "")

    if from_agent not in ALLOWED_SENDERS:
        logger.warning("[manager] Ignoring msg from unauthorized sender: %s", from_agent)
        inbox_tools._complete_message(msg_id, error=f"Unauthorized sender: {from_agent}")
        return

    task_type = payload.get("task_type", "general")
    instruction = payload.get("instruction", "")
    service = payload.get("service")

    if not instruction:
        inbox_tools._complete_message(msg_id, error="Empty instruction")
        return

    logger.info("[manager] Processing %s: %s (from=%s)", task_type, instruction[:100], from_agent)

    # Claim it first
    inbox_tools._claim_message(msg_id)

    start = time.time()
    try:
        result = await _run_agent_loop(instruction, msg_id, task_type, service)
    except Exception as e:
        logger.exception("[manager] Agent loop failed")
        result = {"status": "error", "error": str(e)}

    duration_ms = (time.time() - start) * 1000
    audit_tools.log_task(msg, result, duration_ms)
    inbox_tools._complete_message(msg_id, result=result, error=result.get("error"))
    logger.info("[manager] Completed %s in %.0fms (status=%s)", msg_id, duration_ms, result.get("status"))


async def poll_loop():
    logger.info("[manager] Swarm Manager started — polling every %ds", POLL_INTERVAL)

    # Initial heartbeat
    inbox_tools._heartbeat("hermes", {"role": "swarm_manager", "mode": "active"})

    while True:
        try:
            msgs = inbox_tools._read_pending("hermes")
            if msgs:
                logger.info("[manager] %d pending message(s)", len(msgs))
                for msg in msgs:
                    if msg.get("type") == "task_request":
                        asyncio.create_task(_process_message(msg))
                    elif msg.get("type") == "heartbeat":
                        # Ack and skip
                        inbox_tools._complete_message(msg["id"], result={"ack": True})
            else:
                logger.debug("[manager] No pending messages")

        except Exception as e:
            logger.error("[manager] Poll error: %s", e)

        # Heartbeat every poll cycle
        try:
            inbox_tools._heartbeat("hermes", {
                "role": "swarm_manager",
                "mode": "active",
                "tools": len(TOOLS),
            })
        except Exception:
            pass

        await asyncio.sleep(POLL_INTERVAL)


async def health_sweep_loop():
    """Run health check every 5 minutes, auto-restart stale services."""
    await asyncio.sleep(120)  # Initial delay
    while True:
        try:
            result_str = health_tools._handle_health_check({})
            result = json.loads(result_str)
            stale = result.get("stale_agents", [])
            if stale:
                logger.warning("[health] Stale agents: %s", stale)
                for agent in stale:
                    svc = health_tools.AGENT_SERVICE_MAP.get(agent)
                    if svc and svc != "hermes-bot":  # Don't restart ourselves
                        logger.info("[health] Auto-restarting %s (%s)", agent, svc)
                        restart_result = railway_tools._handle_railway_restart({"service": svc})
                        logger.info("[health] Restart result: %s", restart_result[:200])
            else:
                logger.info("[health] All agents healthy (%d/%d)",
                            result.get("healthy_count", 0), result.get("total_count", 0))
        except Exception as e:
            logger.error("[health] Sweep error: %s", e)

        await asyncio.sleep(300)  # 5 minutes


async def main():
    _load_tools()
    async with asyncio.TaskGroup() as tg:
        tg.create_task(poll_loop())
        tg.create_task(health_sweep_loop())


if __name__ == "__main__":
    asyncio.run(main())
