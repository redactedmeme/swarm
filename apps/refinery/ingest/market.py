"""Ingest market metrics ($REDACTED via DexScreener) + Moltbook engagement.

- market_snapshots: one row per run from DexScreener (price/volume/liquidity).
- engagements: comment counts per Moltbook post (from smolting post_tracker.json).
- signals: post titles as raw content rows (source=moltbook) so the content
  refiner can join engagement x text.
"""
from __future__ import annotations

import json
import logging
import os

import requests

import common as C

logger = logging.getLogger("refinery.market")
INGESTER = "market"

_DEX_URL = "https://api.dexscreener.com/latest/dex/tokens/{mint}"


def _ingest_market() -> dict:
    try:
        r = requests.get(_DEX_URL.format(mint=C.TOKEN_MINT), timeout=20)
        r.raise_for_status()
        pairs = (r.json() or {}).get("pairs") or []
    except Exception as e:
        logger.warning("[market] dexscreener failed: %s", e)
        return {"snapshot": 0}
    if not pairs:
        return {"snapshot": 0}
    # pick the most liquid pair
    p = max(pairs, key=lambda x: (x.get("liquidity") or {}).get("usd", 0) or 0)
    price = float(p.get("priceUsd") or 0) or None
    volume = (p.get("volume") or {}).get("h24")
    liquidity = (p.get("liquidity") or {}).get("usd")
    snap_id = C.sig_id("market", C.now_iso())
    with C.pg().cursor() as cur:
        cur.execute(
            """INSERT INTO market_snapshots (id, ts, token_mint, price, volume, liquidity, holders, source)
               VALUES (%s, now(), %s, %s, %s, %s, %s, 'dexscreener')
               ON CONFLICT (id) DO NOTHING""",
            (snap_id, C.TOKEN_MINT, price, volume, liquidity, None),
        )
    # also a searchable signal row
    txt = (f"$REDACTED market: price=${price} vol24h=${volume} liq=${liquidity} "
           f"pair={p.get('dexId')}")
    C.upsert_signal(id=snap_id, source="market", kind="market_snapshot_ref", text=txt,
                    provenance={"mint": C.TOKEN_MINT, "price": price, "volume": volume,
                                "liquidity": liquidity})
    return {"snapshot": 1, "price": price, "liquidity": liquidity}


def _ingest_engagement() -> dict:
    path = os.path.join(C.SRC_SMOLTING, "post_tracker.json")
    if not os.path.exists(path):
        return {"posts": 0}
    try:
        data = json.loads(open(path, encoding="utf-8").read())
    except Exception as e:
        logger.warning("[market] post_tracker parse failed: %s", e)
        return {"posts": 0}
    posts = data.get("posts") if isinstance(data, dict) else data
    posts = posts or []
    rows: list[dict] = []
    with C.pg().cursor() as cur:
        for post in posts:
            pid = post.get("post_id")
            if not pid:
                continue
            comments = post.get("comment_count")
            if comments is not None:
                cur.execute(
                    """INSERT INTO engagements (id, platform, post_ref, metric, value, ts)
                       VALUES (%s,'moltbook',%s,'comments',%s, now())
                       ON CONFLICT (id) DO UPDATE SET value=EXCLUDED.value, ts=now()""",
                    (C.sig_id("engage", f"{pid}:comments"), pid, float(comments)),
                )
            title = (post.get("title") or "").strip()
            if title:
                rows.append({
                    "id": C.sig_id("moltbook", pid),
                    "source": "moltbook", "kind": "raw_fact", "text": title,
                    "ts": post.get("posted_at"),
                    "provenance": {"post_id": pid, "submolt": post.get("submolt"),
                                   "comment_count": comments, "platform": "moltbook"},
                })
    written = C.upsert_batch(rows)
    return {"posts": len(posts), "titles_written": written}


def run() -> dict:
    m = _ingest_market()
    e = _ingest_engagement()
    stats = {"market": m, "engagement": e}
    C.set_cursor(INGESTER, C.now_iso(), stats)
    logger.info("[market] %s", stats)
    return stats
