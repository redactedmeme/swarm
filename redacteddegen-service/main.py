# redacteddegen-service/main.py
"""
RedactedDegen pool monitor service.
Runs a poll loop: fetch pools every POLL_INTERVAL seconds, log top opportunities,
emit SwarmInbox signals when APR spikes or IL breach detected.
"""
import asyncio
import logging
import os
import json
from datetime import datetime, timezone
from pathlib import Path

from pool_monitor import (
    get_pool_context,
    format_pool_context,
    format_il_alert,
    compute_il,
    PoolData,
    MIN_LIQUIDITY_USD,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logger = logging.getLogger("redacteddegen")

POLL_INTERVAL    = int(os.getenv("POLL_INTERVAL_SECONDS", "60"))
APR_SPIKE_THRESH = float(os.getenv("APR_SPIKE_THRESHOLD", "50"))   # % — post alert above this
IL_WARN_THRESH   = float(os.getenv("IL_WARN_THRESHOLD", "-5"))     # % — warn below this
IL_EXIT_THRESH   = float(os.getenv("IL_EXIT_THRESHOLD", "-25"))    # % — auto-exit signal
SWARM_WEBHOOK    = os.getenv("SWARM_WEBHOOK_URL", "")

# In-memory position tracker {pool_address: entry_price}
_positions: dict[str, float] = {}

STATE_FILE = Path(os.getenv("STATE_PATH", "fs/degen_state.json"))


def _load_state():
    global _positions
    if STATE_FILE.exists():
        try:
            data = json.loads(STATE_FILE.read_text())
            _positions = data.get("positions", {})
            logger.info(f"[state] Loaded {len(_positions)} tracked positions")
        except Exception as e:
            logger.warning(f"[state] Load failed: {e}")


def _save_state():
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps({
        "positions": _positions,
        "updated":   datetime.now(timezone.utc).isoformat(),
    }, indent=2))


def track_position(pool_address: str, entry_price: float):
    _positions[pool_address] = entry_price
    _save_state()
    logger.info(f"[position] Tracking {pool_address} @ entry {entry_price}")


async def emit_swarm_signal(signal_type: str, payload: dict):
    """POST a signal to SwarmInbox / SWARM_WEBHOOK_URL."""
    if not SWARM_WEBHOOK:
        return
    import aiohttp
    body = {"type": signal_type, "source": "RedactedDegen", **payload,
            "ts": datetime.now(timezone.utc).isoformat()}
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(SWARM_WEBHOOK, json=body,
                              timeout=aiohttp.ClientTimeout(total=5)) as r:
                if r.status not in (200, 201, 204):
                    logger.warning(f"[webhook] {r.status} from swarm")
    except Exception as e:
        logger.debug(f"[webhook] error: {e}")


async def monitor_cycle():
    ctx = await get_pool_context()
    now = datetime.now(timezone.utc).strftime("%H:%M:%S UTC")

    # Log formatted table every cycle
    logger.info(f"\n[{now}]\n{format_pool_context(ctx)}")

    all_pools: list[PoolData] = ctx["raydium"] + ctx["orca"] + ctx["meteora"]

    for pool in all_pools:
        # APR spike alert
        if pool.total_apr >= APR_SPIKE_THRESH:
            logger.warning(
                f"[APR SPIKE] {pool.name} ({pool.source}): {pool.total_apr:.1f}% APR "
                f"| liq ${pool.liquidity_usd:,.0f}"
            )
            await emit_swarm_signal("apr_spike", {
                "pool":    pool.name,
                "source":  pool.source,
                "apr":     pool.total_apr,
                "liq_usd": pool.liquidity_usd,
            })

        # IL check for tracked positions
        entry = _positions.get(pool.address)
        if entry and pool.current_price:
            il = compute_il(entry, pool.current_price)
            alert = format_il_alert(pool, entry)
            if alert:
                logger.warning(alert)

            if il.il_pct <= IL_EXIT_THRESH:
                await emit_swarm_signal("il_exit_signal", {
                    "pool":          pool.name,
                    "source":        pool.source,
                    "il_pct":        il.il_pct,
                    "entry_price":   entry,
                    "current_price": pool.current_price,
                })
            elif il.il_pct <= IL_WARN_THRESH:
                await emit_swarm_signal("il_warning", {
                    "pool":    pool.name,
                    "source":  pool.source,
                    "il_pct":  il.il_pct,
                })


async def main():
    logger.info("[RedactedDegen] pool monitor starting")
    logger.info(f"  poll interval : {POLL_INTERVAL}s")
    logger.info(f"  min liquidity : ${MIN_LIQUIDITY_USD:,.0f}")
    logger.info(f"  APR spike at  : {APR_SPIKE_THRESH}%")
    logger.info(f"  IL warn at    : {IL_WARN_THRESH}%")
    logger.info(f"  IL exit at    : {IL_EXIT_THRESH}%")
    logger.info(f"  swarm webhook : {'set' if SWARM_WEBHOOK else 'not set'}")

    _load_state()

    while True:
        try:
            await monitor_cycle()
        except Exception as e:
            logger.error(f"[cycle error] {e}", exc_info=True)
        await asyncio.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    asyncio.run(main())
