"""meta_signal — which past decisions correlated with good market outcomes.

First-pass heuristic: pair recent orchestrator decisions with the market direction
that followed. Without per-decision outcome labels this is a coarse read, but it
establishes the loop the plan calls for (decision x market). Refined as labels grow.
"""
from __future__ import annotations

import logging

import common as C

logger = logging.getLogger("refinery.refine.meta")


def run() -> dict:
    with C.pg().cursor() as cur:
        cur.execute(
            """SELECT provenance->'delta_pct'->>'price' FROM signals
               WHERE kind='market_signal' ORDER BY ts DESC LIMIT 1""")
        row = cur.fetchone()
        price_dir = None
        if row and row[0] not in (None, "None"):
            try:
                price_dir = float(row[0])
            except Exception:
                price_dir = None
        cur.execute(
            """SELECT text FROM signals
               WHERE kind='raw_orchestrator' AND provenance->>'hint'='decision'
               ORDER BY ts DESC LIMIT 10""")
        decisions = [r[0] for r in cur.fetchall()]

    if not decisions:
        return {"emitted": 0}

    direction = ("up" if (price_dir or 0) > 0 else
                 "down" if (price_dir or 0) < 0 else "flat")
    llm = C.summarize(
        "Recent swarm decisions:\n" + "\n".join(decisions[:8]) +
        f"\n\n$REDACTED price moved {direction} ({price_dir}%) after these. "
        "In one sentence: which decision pattern to reinforce or avoid?",
        system="You are a strategy analyst. One sentence.")
    body = llm or (f"{len(decisions)} recent decisions; market {direction} "
                   f"({price_dir}%). Outcome labels pending for stronger attribution.")
    C.upsert_signal(
        id=C.sig_id("refine", "meta_decision_outcome"),
        source="refine", kind="meta_signal", text=body, confidence=0.4,
        provenance={"price_dir_pct": price_dir, "n_decisions": len(decisions),
                    "llm": bool(llm)})
    logger.info("[meta] emitted meta_signal (market=%s)", direction)
    return {"emitted": 1}
