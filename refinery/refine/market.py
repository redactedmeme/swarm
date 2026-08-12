"""market_signal — price/volume/liquidity deltas from market_snapshots."""
from __future__ import annotations

import logging

import common as C

logger = logging.getLogger("refinery.refine.market")


def _pct(new, old):
    if old in (None, 0) or new is None:
        return None
    return (new - old) / old * 100.0


def run() -> dict:
    with C.pg().cursor() as cur:
        cur.execute(
            """SELECT ts, price, volume, liquidity FROM market_snapshots
               WHERE token_mint=%s ORDER BY ts DESC LIMIT 2""", (C.TOKEN_MINT,))
        rows = cur.fetchall()
    if not rows:
        return {"emitted": 0}
    cur_ts, price, volume, liq = rows[0]
    if len(rows) == 2:
        _, p0, v0, l0 = rows[1]
        dp, dv, dl = _pct(price, p0), _pct(volume, v0), _pct(liq, l0)
    else:
        dp = dv = dl = None

    def fmt(x):
        return f"{x:+.1f}%" if x is not None else "n/a"

    text = (f"$REDACTED: price ${price} ({fmt(dp)}), 24h vol ${volume} ({fmt(dv)}), "
            f"liquidity ${liq} ({fmt(dl)}) since prior snapshot")
    # confidence scales with how much moved
    conf = 0.6 + min(0.4, (abs(dp or 0) + abs(dl or 0)) / 100.0)
    C.upsert_signal(
        id=C.sig_id("refine", "market_delta"),
        source="refine", kind="market_signal", text=text, confidence=round(conf, 2),
        provenance={"price": price, "volume": volume, "liquidity": liq,
                    "delta_pct": {"price": dp, "volume": dv, "liquidity": dl}})
    logger.info("[market] emitted market_signal: %s", text)
    return {"emitted": 1}
