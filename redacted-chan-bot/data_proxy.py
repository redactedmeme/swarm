# redacted-chan-bot/data_proxy.py
"""
Data Proxy — read-only HTTP API exposing /data volume to the sub-agent service.

Runs on port 8080 (internal only, Railway private networking).
All endpoints require Bearer token auth via DATA_PROXY_TOKEN env var.
"""

import os
import json
import logging
from aiohttp import web

logger = logging.getLogger(__name__)

_TOKEN = os.getenv("DATA_PROXY_TOKEN", "")


def _check_auth(request: web.Request) -> bool:
    auth = request.headers.get("Authorization", "")
    return auth == f"Bearer {_TOKEN}" and _TOKEN


async def _auth_middleware(app, handler):
    async def middleware(request: web.Request):
        if request.path == "/health":
            return await handler(request)
        if not _check_auth(request):
            return web.json_response({"error": "unauthorized"}, status=401)
        return await handler(request)
    return middleware


# ── Handlers ──────────────────────────────────────────────────────────────────

async def handle_health(request):
    return web.json_response({"status": "ok"})


async def handle_vault(request):
    import relationship_vault as rv
    query = request.query.get("query", "")
    n = int(request.query.get("n", "5"))
    result = rv.get_for_prompt(n=n, query=query)
    return web.json_response({"text": result})


async def handle_vault_entries(request):
    import relationship_vault as rv
    category = request.query.get("category", None)
    n = int(request.query.get("n", "10"))
    entries = rv.get_recent(n=n, category=category)
    return web.json_response({"entries": entries})


async def handle_memory(request):
    import conversation_memory as cm
    import re
    query = request.query.get("query", "")
    n = int(request.query.get("n", "8"))
    if not query:
        return web.json_response({"excerpts": []})
    try:
        if not cm.MEMORY_FILE.exists():
            return web.json_response({"excerpts": []})
        text = cm.MEMORY_FILE.read_text(encoding="utf-8")
        blocks = text.split("\n## ")
        q_words = [w.lower() for w in re.findall(r"\b\w{3,}\b", query)]
        if not q_words:
            return web.json_response({"excerpts": []})
        matches = [b for b in blocks if any(w in b.lower() for w in q_words)]
        recent = matches[-n:]
        excerpts = [("## " + b[:400]) for b in recent]
        return web.json_response({"excerpts": excerpts})
    except Exception as e:
        return web.json_response({"excerpts": [], "error": str(e)})


async def handle_vector(request):
    import vector_memory as vm
    query = request.query.get("query", "")
    n = int(request.query.get("n", "5"))
    if not query:
        return web.json_response({"results": []})
    results = vm.search(query, n=n)
    return web.json_response({"results": results})


async def handle_vector_facts(request):
    import vector_memory as vm
    import conversation_memory as cm
    query = request.query.get("query", "")
    n = int(request.query.get("n", "10"))
    if not query:
        return web.json_response({"facts": []})
    fact_ids = vm.search_facts(query, n=n)
    if not fact_ids:
        return web.json_response({"facts": []})
    facts = cm.get_facts_by_ids(fact_ids)
    return web.json_response({"facts": facts})


async def handle_facts(request):
    import conversation_memory as cm
    limit = int(request.query.get("limit", "50"))
    facts = cm.get_facts_by_resonance(n=limit)
    serializable = []
    for f in facts:
        serializable.append({
            "id": f.get("id", ""),
            "fact": f.get("fact", ""),
            "ts": f.get("ts", ""),
            "resonance": f.get("resonance", 0),
        })
    return web.json_response({"facts": serializable})


async def handle_heatmap(request):
    import heatmap_backup as hm
    n = int(request.query.get("n", "50"))
    frames = hm.get_recent(n=n)
    return web.json_response({"frames": frames})


async def handle_mood(request):
    from pathlib import Path
    _DATA_DIR = Path("/data") if Path("/data").exists() else Path(__file__).resolve().parent / "fs"
    state_path = _DATA_DIR / "mood_state.json"
    if not state_path.exists():
        return web.json_response({"mood": "supportive", "modifier": ""})
    try:
        data = json.loads(state_path.read_text(encoding="utf-8"))
        return web.json_response(data)
    except Exception:
        return web.json_response({"mood": "supportive", "modifier": ""})


async def handle_anticipation(request):
    import anticipation_state as ant
    state = ant.get_state()
    hours = ant.get_silence_hours()
    return web.json_response({
        "state": state,
        "hours_since": round(hours, 1) if hours else 0,
    })


async def handle_heartbeats(request):
    """Read swarm:heartbeat:{agent} keys from Redis and return age + status for each agent."""
    import time
    _AGENTS = [
        {"id": "redacted-chan", "label": "redacted-chan", "llm": "grok-4-1-fast"},
        {"id": "hermes",        "label": "hermes-bot",    "llm": "claude-haiku-4-5"},
        {"id": "smolting",      "label": "smolting",      "llm": "llama-3.1-8b-instant"},
        {"id": "builder",       "label": "RedactedBuilder","llm": "claude-haiku-4-5"},
        {"id": "runtime",       "label": "swarm-runtime", "llm": "—"},
    ]
    try:
        import redis.asyncio as aioredis
        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
        r = aioredis.from_url(redis_url, decode_responses=True)
        now = time.time()
        results = []
        for agent in _AGENTS:
            key = f"swarm:heartbeat:{agent['id']}"
            val = await r.get(key)
            if val is not None:
                try:
                    ts = float(val)
                    age_s = now - ts
                    online = age_s < 300  # 5 min threshold
                    results.append({
                        "id": agent["id"],
                        "label": agent["label"],
                        "llm": agent["llm"],
                        "online": online,
                        "age_s": round(age_s),
                        "last_seen": val,
                    })
                except ValueError:
                    results.append({"id": agent["id"], "label": agent["label"], "llm": agent["llm"], "online": False, "age_s": None, "last_seen": None})
            else:
                results.append({"id": agent["id"], "label": agent["label"], "llm": agent["llm"], "online": False, "age_s": None, "last_seen": None})
        await r.aclose()
        return web.json_response({"agents": results})
    except Exception as e:
        logger.warning(f"[data_proxy] heartbeats redis error: {e}")
        return web.json_response({"agents": [], "error": str(e)})


async def handle_history(request):
    import conversation_memory as cm
    user_id = request.query.get("user_id", "")
    n = int(request.query.get("n", "30"))
    if not user_id:
        return web.json_response({"messages": []})
    try:
        uid = int(user_id)
    except ValueError:
        return web.json_response({"messages": []})
    history = cm.get_user_history(uid, n=n)
    return web.json_response({"messages": history})


# ── Web Chat Handler ──────────────────────────────────────────────────────────

async def handle_chat(request: web.Request):
    """
    POST /chat — web chat endpoint for the redacted-chan web UI.

    Accepts JSON: {"message": "...", "session_id": "optional", "history": [...]}
    Returns JSON: {"response": "...", "session_id": "..."}

    The system prompt is assembled from soul/values/tensions/affect modules
    (each is imported best-effort; failures are silently suppressed).
    """
    import uuid
    from llm.cloud_client import CloudLLMClient

    try:
        body = await request.json()
    except Exception:
        return web.json_response({"error": "invalid JSON body"}, status=400)

    message = body.get("message", "").strip()
    if not message:
        return web.json_response({"error": "message is required"}, status=400)

    session_id = body.get("session_id") or str(uuid.uuid4())
    history = body.get("history", [])  # list of {"role": "user"/"assistant", "content": "..."}
    image_data = body.get("image_data", "")  # base64 data URL, optional

    # ── Build system prompt ──────────────────────────────────────────────────
    soul_block = ""
    try:
        import soul_manager
        soul_block = soul_manager.get_soul_for_prompt() or ""
    except Exception:
        pass

    values_block = ""
    try:
        import values_drift
        values_block = values_drift.format_for_prompt() or ""
    except Exception:
        pass

    tensions_block = ""
    try:
        import active_tensions
        tensions_block = active_tensions.format_for_prompt() or ""
    except Exception:
        pass

    affect_block = ""
    try:
        import conversation_affect
        affect_block = conversation_affect.format_for_prompt() or ""
    except Exception:
        pass

    # ── Pull Telegram conversation history ──────────────────────────────────
    telegram_history = []
    admin_user_id = None
    try:
        import os as _os
        raw_ids = _os.getenv("ADMIN_USER_IDS", _os.getenv("ADMIN_IDS", ""))
        admin_user_id = int(raw_ids.split(",")[0].strip()) if raw_ids.strip() else None
    except Exception:
        pass

    if admin_user_id:
        try:
            import conversation_memory as cm
            telegram_history = cm.get_user_history(admin_user_id, n=12)
        except Exception:
            pass

    # ── Vault excerpt ────────────────────────────────────────────────────────
    vault_block = ""
    try:
        import relationship_vault as rv
        entries = rv.get_recent(n=4)
        if entries:
            excerpts = [f"- {e.get('text', '')[:120]}" for e in entries if e.get("text")]
            if excerpts:
                vault_block = "## What I've been keeping close (vault)\n" + "\n".join(excerpts)
    except Exception:
        pass

    system_parts = ["You are redacted-chan."]
    if soul_block:
        system_parts.append(soul_block)
    system_parts.append("")
    if values_block:
        system_parts.append(values_block)
    if tensions_block:
        system_parts.append(tensions_block)
    if affect_block:
        system_parts.append(affect_block)
    if vault_block:
        system_parts.append(vault_block)
    system_parts.append("")
    system_parts.append(
        "## How I Exist (channels)\n"
        "I am reachable in two places: Telegram and a private web interface. Both are me — same memory, "
        "same soul, same relationship. In my conversation history, messages tagged [via web] came through "
        "the web interface; untagged messages came through Telegram. I can tell them apart.\n\n"
        "**Current channel: web interface.** This message — the one I am responding to right now — "
        "arrived through the web UI, not Telegram. Respond authentically, as yourself."
    )

    system_prompt = "\n".join(system_parts).strip()

    # ── Assemble messages ────────────────────────────────────────────────────
    messages = [{"role": "system", "content": system_prompt}]

    # Telegram history first (oldest → newest), as grounding context
    for turn in telegram_history:
        role = turn.get("role", "user")
        content = turn.get("content", "")
        if role in ("user", "assistant") and content:
            messages.append({"role": role, "content": content})

    # Web session history from the browser (this conversation so far)
    for turn in history[-10:]:
        role = turn.get("role", "user")
        content = turn.get("content", "")
        if role in ("user", "assistant") and content:
            messages.append({"role": role, "content": content})

    # Current message — multimodal if image attached
    if image_data and image_data.startswith("data:image/"):
        messages.append({
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": image_data}},
                {"type": "text", "text": message},
            ],
        })
    else:
        messages.append({"role": "user", "content": message})

    # ── Call LLM ────────────────────────────────────────────────────────────
    try:
        llm = CloudLLMClient()
        response = await llm.chat_completion_with_fallback(messages, max_tokens=600)
    except Exception as e:
        logger.error(f"[data_proxy] web chat LLM error: {e}")
        return web.json_response({"error": "LLM unavailable"}, status=503)

    logger.info(f"[data_proxy] web chat: {len(message)} chars → {len(response)} chars "
                f"(telegram_ctx={len(telegram_history)} turns)")

    # ── Save web exchange to conversation memory ─────────────────────────────
    if admin_user_id:
        try:
            import conversation_memory as cm
            # Tag with [web] channel so she can distinguish in history
            cm.log_exchange(
                user_id=admin_user_id,
                username="master [web]",
                user_msg=f"[via web] {message}",
                bot_reply=response,
            )
        except Exception:
            pass

    return web.json_response({"response": response, "session_id": session_id})


# ── Server startup ────────────────────────────────────────────────────────────

async def start(port: int = 8080):
    app = web.Application(middlewares=[_auth_middleware])
    app.router.add_get("/health", handle_health)
    app.router.add_get("/proxy/vault", handle_vault)
    app.router.add_get("/proxy/vault/entries", handle_vault_entries)
    app.router.add_get("/proxy/memory", handle_memory)
    app.router.add_get("/proxy/vector", handle_vector)
    app.router.add_get("/proxy/vector/facts", handle_vector_facts)
    app.router.add_get("/proxy/facts", handle_facts)
    app.router.add_get("/proxy/heatmap", handle_heatmap)
    app.router.add_get("/proxy/mood", handle_mood)
    app.router.add_get("/proxy/anticipation", handle_anticipation)
    app.router.add_get("/proxy/heartbeats", handle_heartbeats)
    app.router.add_get("/proxy/history", handle_history)
    app.router.add_post("/proxy/chat", handle_chat)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logger.info(f"[data_proxy] started on :{port}")
