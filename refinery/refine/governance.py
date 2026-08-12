"""governance_signal — sentiment + proposal-readiness from community + orchestrator.

Aggregates recent convictions/insights (orchestrator, private) and community facts
into a compact governance read. Private source *text* is summarized but the emitted
signal is kept non-private (it is a derived, aggregate read — no raw private lines).
"""
from __future__ import annotations

import logging

import common as C

logger = logging.getLogger("refinery.refine.governance")


def run() -> dict:
    with C.pg().cursor() as cur:
        cur.execute(
            """SELECT text FROM signals
               WHERE kind='raw_orchestrator'
                 AND (provenance->>'hint' IN ('conviction','insight','decision'))
               ORDER BY ts DESC LIMIT 30""")
        convictions = [r[0] for r in cur.fetchall()]
        cur.execute(
            """SELECT text FROM signals
               WHERE kind='raw_fact' AND source IN ('smolting_facts','moltbook')
               ORDER BY ts DESC LIMIT 30""")
        community = [r[0] for r in cur.fetchall()]

    if not convictions and not community:
        return {"emitted": 0}

    corpus = "CONVICTIONS/DECISIONS:\n" + "\n".join(convictions[:20]) + \
             "\n\nCOMMUNITY:\n" + "\n".join(community[:20])
    llm = C.summarize(
        corpus + "\n\nIn one sentence: current governance sentiment and whether "
        "any proposal looks ready to advance.",
        system="You are a DAO analyst. One sentence, concrete.")
    body = llm or (f"Governance read from {len(convictions)} convictions + "
                   f"{len(community)} community signals (LLM offline; raw aggregate).")
    C.upsert_signal(
        id=C.sig_id("refine", "governance_read"),
        source="refine", kind="governance_signal", text=body, confidence=0.6,
        provenance={"n_convictions": len(convictions), "n_community": len(community),
                    "llm": bool(llm)})
    logger.info("[governance] emitted governance_signal (llm=%s)", bool(llm))
    return {"emitted": 1}
