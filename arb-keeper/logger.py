"""
logger.py — Redis SwarmInbox push for arb trade events.

Pushes trade results and opportunity detections to:
  swarm:pending:arb-keeper  — per-agent inbox (picked up by hermes/dashboard)
  swarm:all                 — global broadcast list
"""

import json
import logging
import time
import uuid
from typing import Optional

import config

log = logging.getLogger(__name__)

_redis_client = None


def _get_redis():
    global _redis_client
    if _redis_client is None:
        try:
            import redis as redis_lib
            _redis_client = redis_lib.from_url(config.REDIS_URL, decode_responses=True)
            _redis_client.ping()
            log.info('Redis connected')
        except Exception as e:
            log.warning(f'Redis unavailable — logging disabled: {e}')
            _redis_client = None
    return _redis_client


def _push(msg_type: str, payload: dict):
    r = _get_redis()
    if not r:
        return
    msg = {
        'id':        str(uuid.uuid4()),
        'type':      msg_type,
        'from':      'arb-keeper',
        'ts':        int(time.time()),
        **payload,
    }
    serialized = json.dumps(msg)
    try:
        pipe = r.pipeline()
        pipe.lpush(f'swarm:msg:{msg["id"]}', serialized)
        pipe.lpush('swarm:pending:arb-keeper', msg['id'])
        pipe.lpush('swarm:all', msg['id'])
        pipe.execute()
    except Exception as e:
        log.warning(f'Redis push failed: {e}')


def log_opportunity(opp) -> None:
    """Log a detected arb opportunity (detect-only mode or pre-execution)."""
    _push('arb_opportunity', {
        'net_profit_sol':      round(opp.net_profit_sol, 8),
        'gross_profit_sol':    round(opp.gross_profit_lamports / 1e9, 8),
        'buy_sol':             round(opp.buy_sol_lamports / 1e9, 6),
        'expected_tokens':     opp.expected_tokens,
        'buy_route':           opp.buy_route_summary,
        'sell_route':          opp.sell_route_summary,
        'executed':            False,
    })


def log_trade(result) -> None:
    """Log a completed trade attempt (success or failure)."""
    opp = result.opportunity
    _push('arb_trade', {
        'success':          result.success,
        'bundle_id':        result.bundle_id,
        'actual_profit_sol': result.actual_profit_sol,
        'est_profit_sol':   round(opp.net_profit_sol, 8),
        'buy_sol':          round(opp.buy_sol_lamports / 1e9, 6),
        'buy_route':        opp.buy_route_summary,
        'sell_route':       opp.sell_route_summary,
        'error':            result.error,
    })


def log_circuit_status(status: dict) -> None:
    """Periodic heartbeat with circuit breaker state."""
    _push('arb_status', status)
