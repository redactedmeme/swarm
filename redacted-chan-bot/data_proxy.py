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
    app.router.add_get("/proxy/history", handle_history)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logger.info(f"[data_proxy] started on :{port}")
