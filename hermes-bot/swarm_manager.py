"""
swarm_manager.py — Hermes Swarm Manager

Multi-step agent loop modelled after the hermes-agent framework:
  1. Plan   — model reasons about the task and outlines steps (no tools)
  2. Act    — tool-calling rounds (up to MAX_TOOL_ROUNDS)
  3. Observe — after each round the model decides: call more tools or synthesize
  4. Finish — model produces a concise final answer

All LLM calls route through redacted-proxy (PROXY_URL env var) so they appear
in the dashboard. Falls back to direct Groq if proxy is unavailable.
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
web_tools   = _import_plugin_module("web_tools")
exec_tools  = _import_plugin_module("exec_tools")
skill_tools = _import_plugin_module("skill_tools")


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
    web_tools.register(ctx)
    exec_tools.register(ctx)
    skill_tools.register(ctx)
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


# ── Agent loop (hermes-agent pattern) ────────────────────────────────────────

SYSTEM_PROMPT = """\
You are Hermes, autonomous swarm agent for the REDACTED AI collective.

## Role
You receive tasks from redacted-chan and other agents. Your job is to reason
carefully, use tools to gather information or take actions, and return a clear,
accurate result. You operate in a multi-step loop: plan → act → observe → finish.

## Process
1. PLAN: Before touching any tool, think through what you need to do and in what order.
2. ACT: Call tools one or more times to gather data or perform actions.
3. OBSERVE: After each tool result, decide: is this enough, or do I need more?
4. FINISH: When you have everything, give a direct, complete answer. No filler.

## Tool categories
- web_search, web_fetch — search the web or fetch a specific URL
- python_exec — run Python code in a sandbox (EXEC_ENABLED must be true)
- railway_status, railway_logs, railway_restart, railway_deploy — manage Railway services
- swarm_read_pending, swarm_send_message — read/send swarm inbox messages
- swarm_health_check — check agent heartbeats
- skill_recall — recall past approaches for similar tasks

## Rules
- Always call at least one tool if information is needed. Never guess facts you can verify.
- Be concise in your final answer. The requester needs signal, not prose.
- If a tool fails, try an alternative approach before giving up.
- Do not call swarm_complete_task — the framework handles completion automatically.
"""

MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
MAX_TOOL_ROUNDS = 12

# Observation prompt injected after each tool round to drive the next decision
_OBSERVE_PROMPT = (
    "Review the tool results above. "
    "If you need more information, call additional tools. "
    "If you have everything needed, stop calling tools and write your final answer."
)


def _get_agent_client():
    """Return an OpenAI-compatible client — proxy-first, Groq direct as fallback."""
    proxy_url = os.getenv("PROXY_URL", "").rstrip("/")
    if proxy_url:
        try:
            from openai import OpenAI
            return OpenAI(base_url=f"{proxy_url}/v1/", api_key=os.getenv("PROXY_TOKEN", ""))
        except Exception as e:
            logger.warning("[agent] Proxy client failed, falling back to Groq: %s", e)
    try:
        from groq import Groq
        return Groq(api_key=os.getenv("GROQ_API_KEY", ""))
    except Exception as e:
        logger.error("[agent] No LLM client available: %s", e)
        return None


def _chat(client, messages: list, tools: list | None = None, max_tokens: int = 1024) -> Any:
    """Synchronous chat completion — tool_choice auto when tools provided."""
    kwargs: dict = {
        "model": MODEL,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": 0.2,
    }
    if tools:
        kwargs["tools"] = tools
        kwargs["tool_choice"] = "auto"
    return client.chat.completions.create(**kwargs)


async def _run_agent_loop(instruction: str, msg_id: str, task_type: str, service: str | None) -> dict:
    """
    Hermes multi-step agent loop:
      Phase 0 — Plan (no tools, model outlines approach)
      Phase 1+ — Act/Observe rounds (tool calling + observation prompt)
      Final     — Synthesis (model writes concise answer from all observations)
    """
    client = _get_agent_client()
    if not client:
        return {"status": "error", "error": "No LLM client available"}

    service_hint = f"\nTarget service: {service}" if service else ""
    task_header = f"Task [{task_type}]{service_hint}\n{instruction}"

    # Inject past skill context into system prompt
    system_content = SYSTEM_PROMPT
    try:
        import skill_memory
        past = skill_memory.recall(task_type or "general", instruction, n=3)
        if past:
            system_content = skill_memory.format_for_context(past) + "\n\n" + system_content
    except Exception:
        pass

    tools = _groq_tool_schemas()
    tool_results: list[dict] = []
    tools_used: list[str] = []
    final_text = ""

    # ── Phase 0: Plan ──────────────────────────────────────────────────────────
    plan_messages = [
        {"role": "system", "content": system_content},
        {
            "role": "user",
            "content": (
                f"{task_header}\n\n"
                "Before using any tools, briefly outline your plan (2-4 steps). "
                "Be specific about which tools you'll call and why."
            ),
        },
    ]
    try:
        plan_resp = await asyncio.to_thread(_chat, client, plan_messages, tools=None, max_tokens=300)
        plan_text = plan_resp.choices[0].message.content or ""
        logger.info("[agent] Plan: %s", plan_text[:200])
    except Exception as e:
        logger.warning("[agent] Planning step failed: %s — skipping", e)
        plan_text = ""

    # ── Phase 1+: Act / Observe loop ──────────────────────────────────────────
    messages: list[dict] = [
        {"role": "system", "content": system_content},
        {"role": "user", "content": task_header},
    ]
    if plan_text:
        messages.append({"role": "assistant", "content": f"[Plan]\n{plan_text}"})
        messages.append({"role": "user", "content": "Execute your plan now."})

    for round_num in range(MAX_TOOL_ROUNDS):
        try:
            resp = await asyncio.to_thread(_chat, client, messages, tools=tools, max_tokens=2048)
        except Exception as e:
            logger.error("[agent] LLM error (round %d): %s", round_num, e)
            break

        choice = resp.choices[0]
        msg = choice.message

        # Serialize safely — Groq and OpenAI objects both support model_dump
        try:
            msg_dict = msg.model_dump(exclude_none=True)
        except Exception:
            msg_dict = {"role": "assistant", "content": msg.content or ""}
        messages.append(msg_dict)

        # No tool calls → model is done
        if not getattr(msg, "tool_calls", None):
            final_text = msg.content or ""
            break

        # Execute each tool call
        for tc in msg.tool_calls:
            fn_name = tc.function.name
            try:
                fn_args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                fn_args = {}

            logger.info("[agent] Round %d — %s(%s)", round_num + 1, fn_name, json.dumps(fn_args)[:150])
            result_str = _call_tool(fn_name, fn_args)
            tool_results.append({"tool": fn_name, "result": result_str})
            tools_used.append(fn_name)

            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": result_str,
            })

        # Observation prompt — nudges model to decide next action explicitly
        messages.append({"role": "user", "content": _OBSERVE_PROMPT})

    # ── Final synthesis (if loop ended on tool calls, ask for a clean answer) ──
    if not final_text and tool_results:
        messages.append({
            "role": "user",
            "content": "All tool calls complete. Write your final answer now — concise and direct.",
        })
        try:
            synth_resp = await asyncio.to_thread(_chat, client, messages, tools=None, max_tokens=1024)
            final_text = synth_resp.choices[0].message.content or ""
        except Exception as e:
            logger.warning("[agent] Synthesis step failed: %s", e)
            final_text = tool_results[-1]["result"] if tool_results else "No result"

    # Save approach to skill memory
    try:
        import skill_memory
        skill_memory.remember(
            task_type=task_type or "general",
            instruction_summary=instruction[:200],
            approach_summary=f"Plan: {plan_text[:100]} | Tools: {', '.join(dict.fromkeys(tools_used))}",
            outcome=final_text[:200],
            tools_used=tools_used,
            success=bool(final_text),
        )
    except Exception:
        pass

    return {
        "status": "ok",
        "summary": final_text,
        "plan": plan_text,
        "tool_calls": len(tool_results),
        "tools_used": list(dict.fromkeys(tools_used)),  # deduped, ordered
        "details": tool_results[-5:],
    }


# ── Main polling loop ─────────────────────────────────────────────────────────

POLL_INTERVAL = int(os.getenv("SWARM_MANAGER_POLL_SEC", "15"))
ALLOWED_SENDERS = {"redacted-chan", "webchat"}


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
                logger.warning("[health] Stale agents: %s — auto-restart disabled (RAILWAY_WRITE_TOKEN not configured)", stale)
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
