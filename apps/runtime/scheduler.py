"""
Background task scheduler using APScheduler.

Runs fact_audit (daily), vault_audit (weekly), daily_digest (daily).
Results stored in-memory, accessible via /scheduled/latest/{name}.
"""

import logging
from datetime import datetime, timezone
from apscheduler.schedulers.asyncio import AsyncIOScheduler

logger = logging.getLogger(__name__)

_scheduler = AsyncIOScheduler()
_results: dict[str, dict] = {}


def get_latest(name: str) -> dict | None:
    return _results.get(name)


async def _run_fact_audit():
    from tasks.fact_audit import execute
    try:
        result = await execute()
        _results["fact_audit"] = {
            "result": result,
            "ts": datetime.now(timezone.utc).isoformat(),
        }
        logger.info("[scheduler] fact_audit completed")
    except Exception as e:
        logger.warning(f"[scheduler] fact_audit failed: {e}")


async def _run_vault_audit():
    from tasks.vault_audit import execute
    try:
        result = await execute()
        _results["vault_audit"] = {
            "result": result,
            "ts": datetime.now(timezone.utc).isoformat(),
        }
        logger.info("[scheduler] vault_audit completed")
    except Exception as e:
        logger.warning(f"[scheduler] vault_audit failed: {e}")


async def _run_daily_digest():
    from tasks.daily_digest import execute
    try:
        result = await execute()
        _results["daily_digest"] = {
            "result": result,
            "ts": datetime.now(timezone.utc).isoformat(),
        }
        logger.info("[scheduler] daily_digest completed")
    except Exception as e:
        logger.warning(f"[scheduler] daily_digest failed: {e}")


def start():
    _scheduler.add_job(_run_fact_audit, "cron", hour=4, minute=0, id="fact_audit")
    _scheduler.add_job(_run_vault_audit, "cron", day_of_week="sun", hour=4, minute=0, id="vault_audit")
    _scheduler.add_job(_run_daily_digest, "cron", hour=23, minute=0, id="daily_digest")
    _scheduler.start()
    logger.info("[scheduler] started — fact_audit(daily 04:00), vault_audit(sun 04:00), daily_digest(daily 23:00)")
