"""swarm-status — the swarm's only public read-only surface.

Reads `swarm:heartbeat:{agent}` from the mesh Redis and serves a deliberately thin,
deliberately boring view of who is alive. redacted.meme proxies this and renders it
as the MESH STATUS section.

What it will *never* expose: model or provider names, prompt or response content,
message counts, queue depths, token usage, exact timestamps, or any key not in
AGENT_LABELS. Age is reported as a coarse bucket rather than a number so the feed
cannot be used to fingerprint an agent's cadence.

    GET /status   -> {"agents": [{"id","label","online","last_seen_bucket"}], "ts": ...}
    GET /healthz  -> {"status": "ok", "redis": true|false}

Env:
    REDIS_URL     redis://swarm-redis:6379/0
    PORT          8098
    ALLOW_ORIGIN  CORS origin, default https://redacted.meme
"""
from __future__ import annotations

import asyncio
import logging
import os
import sys
import time
from datetime import datetime, timezone

from aiohttp import web

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "vendor"))

from swarm_heartbeat import (  # noqa: E402
    HEARTBEAT_LOOKUP_KEYS,
    heartbeat_redis_key,
    parse_heartbeat_value,
    pick_best_heartbeat,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
log = logging.getLogger("swarm-status")

REDIS_URL = os.environ.get("REDIS_URL", "redis://swarm-redis:6379/0")
PORT = int(os.environ.get("PORT", "8098"))
ALLOW_ORIGIN = os.environ.get("ALLOW_ORIGIN", "https://redacted.meme")
CACHE_TTL = float(os.environ.get("CACHE_TTL", "15"))

# The allow-list. An agent absent from here is absent from the public feed, even if
# it is writing heartbeats.
AGENT_LABELS: dict[str, str] = {
    "smolting": "smolting",
    "redacted-chan": "redacted-chan",
    "hermes": "hermes",
    "builder": "RedactedBuilder",
}


def bucket(age_s: float | None, present: bool) -> str:
    """Coarse last-seen bucket. Never an exact age."""
    if not present or age_s is None:
        return "no signal"
    if age_s < 60:
        return "just now"
    if age_s < 300:
        return "< 5 min ago"
    if age_s < 3600:
        return "< 1 hour ago"
    if age_s < 86400:
        return "< 1 day ago"
    return "over a day ago"


_cache: dict = {"ts": 0.0, "payload": None}


async def read_agents(redis_client) -> list[dict]:
    now = time.time()
    out = []
    for agent_id, label in AGENT_LABELS.items():
        candidates = []
        for key in HEARTBEAT_LOOKUP_KEYS.get(agent_id, [agent_id]):
            raw = await redis_client.get(heartbeat_redis_key(key))
            if raw is None:
                continue
            if isinstance(raw, bytes):
                raw = raw.decode("utf-8", "replace")
            candidates.append(parse_heartbeat_value(raw, now))
        hb = pick_best_heartbeat(candidates)
        out.append({
            "id": agent_id,
            "label": label,
            "online": bool(hb.get("online")),
            "last_seen_bucket": bucket(hb.get("age_s"), bool(hb.get("present"))),
        })
    return out


async def status(request: web.Request) -> web.Response:
    now = time.time()
    if _cache["payload"] is not None and now - _cache["ts"] < CACHE_TTL:
        return _json(_cache["payload"])

    redis_client = request.app["redis"]
    try:
        agents = await read_agents(redis_client)
    except Exception as exc:  # noqa: BLE001 — a public endpoint must not 500 on Redis blips
        log.warning("heartbeat read failed: %s", exc)
        return _json({"agents": [], "ts": _now_iso()})

    payload = {"agents": agents, "ts": _now_iso()}
    _cache.update(ts=now, payload=payload)
    return _json(payload)


async def healthz(request: web.Request) -> web.Response:
    try:
        await request.app["redis"].ping()
        ok = True
    except Exception:  # noqa: BLE001
        ok = False
    return _json({"status": "ok", "redis": ok})


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _json(payload: dict) -> web.Response:
    return web.json_response(payload, headers={
        "Access-Control-Allow-Origin": ALLOW_ORIGIN,
        "Cache-Control": "public, max-age=15",
    })


async def make_app() -> web.Application:
    import redis.asyncio as aioredis

    app = web.Application()
    app["redis"] = aioredis.from_url(REDIS_URL, decode_responses=True)
    app.router.add_get("/status", status)
    app.router.add_get("/healthz", healthz)

    async def close_redis(app_):
        await app_["redis"].aclose()

    app.on_cleanup.append(close_redis)
    return app


if __name__ == "__main__":
    log.info("swarm-status on :%s — redis=%s allow-origin=%s", PORT, REDIS_URL, ALLOW_ORIGIN)
    web.run_app(asyncio.get_event_loop().run_until_complete(make_app()), port=PORT, print=None)
