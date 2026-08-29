"""swarm-refinery entrypoint.

Boot sequence:
  1. apply Postgres schema + ensure Qdrant collection
  2. run one full ingest + refine cycle immediately (proves the substrate)
  3. schedule recurring ingest (INGEST_INTERVAL_MIN) + refine (REFINE_INTERVAL_MIN)
  4. serve the Layer-2 read API on REFINERY_PORT (default 8090)
"""
from __future__ import annotations

import logging
import os

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("refinery.main")

import common as C  # noqa: E402
from ingest import redis_msgs, agent_facts, lore, orchestrator, market  # noqa: E402
from refine import content, market as refine_market, governance, meta  # noqa: E402

_SCHEMA = os.path.join(os.path.dirname(__file__), "schema.sql")

INGEST_INTERVAL_MIN = int(os.getenv("INGEST_INTERVAL_MIN", "30"))
REFINE_INTERVAL_MIN = int(os.getenv("REFINE_INTERVAL_MIN", "60"))
REFINERY_PORT = int(os.getenv("REFINERY_PORT", "8090"))
ALERT_INTERVAL_SEC = int(os.getenv("ALERT_INTERVAL_SEC", "120"))

_INGESTERS = [
    ("redis_msgs", redis_msgs.run),
    ("agent_facts", agent_facts.run),
    ("lore", lore.run),
    ("orchestrator", orchestrator.run),
    ("market", market.run),
]
_REFINERS = [
    ("content", content.run),
    ("market", refine_market.run),
    ("governance", governance.run),
    ("meta", meta.run),
]


def run_ingest():
    for name, fn in _INGESTERS:
        try:
            fn()
        except Exception as e:
            logger.exception("[ingest:%s] failed: %s", name, e)


def run_refine():
    for name, fn in _REFINERS:
        try:
            fn()
        except Exception as e:
            logger.exception("[refine:%s] failed: %s", name, e)


def main():
    logger.info("=== swarm-refinery boot ===")
    C.init_schema(_SCHEMA)
    C.ensure_qdrant_collection()
    # warm the embedder once so first request isn't slow
    C.embed("warmup")

    # Only do the heavy initial ingest on a cold store; on restart, data is
    # already present (idempotent) so we skip it and let the scheduler refresh.
    # Set FORCE_INITIAL_INGEST=true to override.
    force = os.getenv("FORCE_INITIAL_INGEST", "false").lower() in ("1", "true", "yes")
    count = C.signals_count()
    if count == 0 or force:
        logger.info("=== initial ingest cycle (signals=%d, force=%s) ===", count, force)
        run_ingest()
    else:
        logger.info("=== skipping initial ingest: %d signals present; scheduler will refresh in %dm ===",
                    count, INGEST_INTERVAL_MIN)
    logger.info("=== initial refine cycle ===")
    run_refine()

    from apscheduler.schedulers.background import BackgroundScheduler
    sched = BackgroundScheduler(timezone="UTC")
    sched.add_job(run_ingest, "interval", minutes=INGEST_INTERVAL_MIN, id="ingest",
                  max_instances=1, coalesce=True)
    sched.add_job(run_refine, "interval", minutes=REFINE_INTERVAL_MIN, id="refine",
                  max_instances=1, coalesce=True)
    import alerting
    sched.add_job(alerting.alert_sweep, "interval", seconds=ALERT_INTERVAL_SEC,
                  id="alert_sweep", max_instances=1, coalesce=True)
    sched.start()
    logger.info("scheduler started: ingest/%dm refine/%dm alert/%ds",
                INGEST_INTERVAL_MIN, REFINE_INTERVAL_MIN, ALERT_INTERVAL_SEC)

    from aiohttp import web
    import api
    logger.info("serving API on :%d", REFINERY_PORT)
    web.run_app(api.make_app(), host="0.0.0.0", port=REFINERY_PORT, print=None)


if __name__ == "__main__":
    main()
