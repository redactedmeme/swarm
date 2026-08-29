"""content_signal — engagement-weighted topics/timing/framing.

Joins Moltbook post titles (signals.source='moltbook') with their comment counts
(engagements) to surface what themes and posting times earn engagement. Emits a
small number of content_signal rows the posting paths can query.
"""
from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime

import common as C

logger = logging.getLogger("refinery.refine.content")


def _hour_of(ts: str) -> int | None:
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00")).hour
    except Exception:
        return None


def run() -> dict:
    with C.pg().cursor() as cur:
        cur.execute(
            """SELECT s.text, s.ts, s.provenance,
                      COALESCE(e.value, 0) AS comments
               FROM signals s
               LEFT JOIN engagements e
                 ON e.post_ref = s.provenance->>'post_id' AND e.metric='comments'
               WHERE s.source='moltbook' AND s.kind='raw_fact'""")
        rows = cur.fetchall()

    if not rows:
        logger.info("[content] no moltbook rows yet")
        return {"emitted": 0}

    scored = sorted(rows, key=lambda r: r[3] or 0, reverse=True)
    top = scored[:10]

    # timing aggregate
    by_hour = defaultdict(list)
    for text, ts, prov, comments in rows:
        h = _hour_of(ts) if ts else None
        if h is not None:
            by_hour[h].append(comments or 0)
    best_hours = sorted(((h, sum(v) / len(v)) for h, v in by_hour.items() if v),
                        key=lambda x: x[1], reverse=True)[:3]

    emitted = 0

    # 1) top-performing themes
    top_titles = "; ".join(f"{t[0]} ({int(t[3])} comments)" for t in top[:5])
    llm = C.summarize(
        f"These Moltbook posts earned the most engagement:\n{top_titles}\n"
        "In one sentence, what topic/framing pattern should the swarm lean into?")
    body = llm or f"Top-engaging themes: {top_titles}"
    C.upsert_signal(
        id=C.sig_id("refine", "content_top_themes"),
        source="refine", kind="content_signal", text=body, confidence=0.8,
        provenance={"basis": "moltbook_engagement", "n": len(rows),
                    "top": [{"title": t[0], "comments": int(t[3] or 0)} for t in top[:5]]})
    emitted += 1

    # 2) best posting windows
    if best_hours:
        hours_txt = ", ".join(f"{h:02d}:00 UTC (avg {avg:.0f} comments)" for h, avg in best_hours)
        C.upsert_signal(
            id=C.sig_id("refine", "content_timing"),
            source="refine", kind="content_signal",
            text=f"Highest-engagement posting windows: {hours_txt}", confidence=0.7,
            provenance={"basis": "hour_of_day", "best_hours": [h for h, _ in best_hours]})
        emitted += 1

    logger.info("[content] emitted=%d over %d posts", emitted, len(rows))
    return {"emitted": emitted, "posts": len(rows)}
