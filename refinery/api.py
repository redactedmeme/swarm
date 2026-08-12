"""Layer-2 read API for refined signals.

    GET  /healthz                     -> liveness + counts
    GET  /signals?kind=&limit=&include_private=  -> recent signals
    GET  /stats                       -> ingest cursors + row counts
    POST /query  {"text":..,"kind":..,"limit":..,"include_private":false}
                                      -> semantic search via Qdrant

Private rows (redacted-chan soul-adjacent) are withheld unless the caller is
on-box AND explicitly sets include_private=true. They never leave the box.
"""
from __future__ import annotations

import logging

from aiohttp import web

import common as C

logger = logging.getLogger("refinery.api")


async def healthz(request):
    with C.pg().cursor() as cur:
        cur.execute("SELECT count(*) FROM signals")
        n = cur.fetchone()[0]
    return web.json_response({"ok": True, "signals": n})


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
    include_private = request.query.get("include_private", "false").lower() in ("1", "true", "yes")
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


async def query(request):
    body = await request.json()
    text = (body.get("text") or "").strip()
    if not text:
        return web.json_response({"error": "text required"}, status=400)
    limit = min(int(body.get("limit", 10)), 100)
    kind = body.get("kind")
    include_private = bool(body.get("include_private", False))

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


def make_app() -> web.Application:
    app = web.Application()
    app.add_routes([
        web.get("/healthz", healthz),
        web.get("/stats", stats),
        web.get("/signals", signals),
        web.post("/query", query),
    ])
    return app
