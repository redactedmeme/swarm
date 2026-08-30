"""Layer-2 read API for refined signals.

    GET  /healthz                     -> liveness + counts
    GET  /liveness                    -> swarm agent heartbeats + queue depth
    GET  /signals?kind=&limit=&include_private=  -> recent signals
    GET  /stats                       -> ingest cursors + row counts
    POST /query  {"text":..,"kind":..,"limit":..,"include_private":false}
                                      -> semantic search via Qdrant

Private rows (redacted-chan soul-adjacent) are withheld unless the caller
presents the operator token. Until now this docstring claimed the caller had to
be "on-box AND explicitly set include_private=true", but no on-box check existed
anywhere — `include_private` was read straight off the request by an endpoint
with no authentication at all, so anyone who could reach the port could read
soul-adjacent rows. `_is_operator` is that missing check.

`POST /query` is a priced endpoint (see `swarm_core.tokens.PRICE_SHEET`).
Operator-token callers — the agents on our own mesh — bypass payment.
"""
from __future__ import annotations

import hmac
import logging
import os

import redis.asyncio as aioredis
from aiohttp import web

from swarm_core.x402 import require_payment

import common as C
import liveness

logger = logging.getLogger("refinery.api")

#: Shared secret for on-mesh callers. Unset means no caller is ever treated as
#: an operator — private rows stay withheld and every /query call must pay.
OPERATOR_TOKEN = os.getenv("REFINERY_OPERATOR_TOKEN", "").strip()


def _is_operator(request: web.Request) -> bool:
    """True only for a caller presenting the operator token.

    Compared with `compare_digest` because this gates both private rows and
    free access; a timing-distinguishable comparison here is a real leak.
    """
    if not OPERATOR_TOKEN:
        return False
    presented = (request.headers.get("Authorization", "")
                 .removeprefix("Bearer ").strip())
    if not presented:
        return False
    return hmac.compare_digest(presented, OPERATOR_TOKEN)


def _wants_private(request: web.Request, requested: bool) -> bool:
    """Resolve `include_private`, refusing rather than silently downgrading.

    Silently returning public-only rows would let a caller believe they had
    searched everything. Raising makes the boundary visible.
    """
    if not requested:
        return False
    if not _is_operator(request):
        raise web.HTTPForbidden(
            reason="include_private requires the operator token"
        )
    return True


async def healthz(request):
    with C.pg().cursor() as cur:
        cur.execute("SELECT count(*) FROM signals")
        n = cur.fetchone()[0]
    return web.json_response({"ok": True, "signals": n})


async def liveness_handler(request):
    return web.json_response(liveness.collect_liveness())


async def stats(request):
    with C.pg().cursor() as cur:
        cur.execute("SELECT kind, count(*) FROM signals GROUP BY kind ORDER BY 2 DESC")
        by_kind = {k: v for k, v in cur.fetchall()}
        cur.execute("SELECT ingester, cursor, updated_at, stats FROM ingest_cursors")
        cursors = [{"ingester": r[0], "cursor": r[1], "updated_at": str(r[2]), "stats": r[3]}
                   for r in cur.fetchall()]
        cur.execute("SELECT count(*) FROM engagements")
        eng = cur.fetchone()[0]
        cur.execute("SELECT count(*) FROM market_snapshots")
        mkt = cur.fetchone()[0]
    return web.json_response({"by_kind": by_kind, "engagements": eng,
                              "market_snapshots": mkt, "cursors": cursors})


async def signals(request):
    kind = request.query.get("kind")
    limit = min(int(request.query.get("limit", "20")), 200)
    include_private = _wants_private(
        request,
        request.query.get("include_private", "false").lower() in ("1", "true", "yes"),
    )
    q = "SELECT id, source, kind, text, ts, confidence, private FROM signals WHERE 1=1"
    args = []
    if kind:
        q += " AND kind=%s"
        args.append(kind)
    if not include_private:
        q += " AND private=false"
    q += " ORDER BY ts DESC LIMIT %s"
    args.append(limit)
    with C.pg().cursor() as cur:
        cur.execute(q, args)
        cols = [d[0] for d in cur.description]
        out = [dict(zip(cols, r)) for r in cur.fetchall()]
    for r in out:
        r["ts"] = str(r["ts"])
    return web.json_response({"count": len(out), "signals": out})


@require_payment("refine", bypass=_is_operator)
async def query(request):
    body = await request.json()
    text = (body.get("text") or "").strip()
    if not text:
        return web.json_response({"error": "text required"}, status=400)
    limit = min(int(body.get("limit", 10)), 100)
    kind = body.get("kind")
    include_private = _wants_private(request, bool(body.get("include_private", False)))

    vec = C.embed(text)
    from qdrant_client.models import Filter, FieldCondition, MatchValue
    must = []
    if kind:
        must.append(FieldCondition(key="kind", match=MatchValue(value=kind)))
    if not include_private:
        must.append(FieldCondition(key="private", match=MatchValue(value=False)))
    flt = Filter(must=must) if must else None
    resp = C.qdrant().query_points(
        collection_name=C.QDRANT_COLLECTION, query=vec, limit=limit,
        query_filter=flt, with_payload=True)
    results = [{"score": h.score, **(h.payload or {})} for h in resp.points]
    return web.json_response({"count": len(results), "results": results})


async def _close_redis(app: web.Application) -> None:
    client = app.get("redis")
    if client is not None:
        await client.aclose()


def make_app() -> web.Application:
    app = web.Application()
    # The payment middleware's replay guard needs this. Without it a priced
    # route returns 503 rather than serving unpaid — fail closed, by design.
    app["redis"] = aioredis.from_url(C.REDIS_URL, decode_responses=True)
    app.on_cleanup.append(_close_redis)
    app.add_routes([
        web.get("/healthz", healthz),
        web.get("/liveness", liveness_handler),
        web.get("/stats", stats),
        web.get("/signals", signals),
        web.post("/query", query),
    ])
    return app
