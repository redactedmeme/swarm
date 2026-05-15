"""
logger.py — Redis SwarmInbox push for rebalance trade events.
"""

import json
import logging
import time
import uuid

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
    msg = {'id': str(uuid.uuid4()), 'type': msg_type, 'from': 'arb-keeper',
           'ts': int(time.time()), **payload}
    serialized = json.dumps(msg)
    try:
        pipe = r.pipeline()
        pipe.lpush(f'swarm:msg:{msg["id"]}', serialized)
        pipe.lpush('swarm:pending:arb-keeper', msg['id'])
        pipe.execute()
        # swarm:all intentionally omitted — key type conflict with other services
    except Exception as e:
        log.warning(f'Redis push failed: {e}')


def log_opportunity(opp) -> None:
    _push('rebalance_signal', {
        'is_buy_token':    opp.is_buy_token,
        'sol_amount':      round(opp.sol_amount, 6),
        'token_amount':    opp.token_amount,
        'current_ratio':   round(opp.current_ratio, 4),
        'target_ratio':    opp.target_ratio,
        'deviation_pct':   round(opp.deviation * 100, 2),
        'price_sol_per_token': round(opp.price_sol_per_token, 8),
        'total_value_sol': round(opp.total_value_sol, 6),
        'executed':        False,
    })


def log_trade(result) -> None:
    opp = result.opportunity
    _push('rebalance_trade', {
        'success':         result.success,
        'bundle_id':       result.bundle_id,
        'is_buy_token':    opp.is_buy_token,
        'sol_amount':      round(opp.sol_amount, 6),
        'token_amount':    opp.token_amount,
        'deviation_pct':   round(opp.deviation * 100, 2),
        'error':           result.error,
    })


def log_circuit_status(status: dict) -> None:
    _push('arb_status', status)
