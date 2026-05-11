"""
main.py — arb-keeper entry point.

Phase 1 (EXECUTE_TRADES=false): detect opportunities, log to Redis, no execution.
Phase 2+ (EXECUTE_TRADES=true):  execute arbs as Jito bundles.

Env vars required:
  SOLANA_PRIVATE_KEY  — 64-byte base58 keypair
  HELIUS_API_KEY      — for Solana RPC
  REDIS_URL           — redis://swarm-redis.railway.internal:6379
  EXECUTE_TRADES      — "true" to enable execution (default: false)
"""

import asyncio
import logging
import socket
import sys
import time
import urllib.request
import json as _json

# ── DNS bypass via DNS-over-HTTPS (DoH) ───────────────────────────────────────
# Railway containers receive a broken /etc/resolv.conf AND may block outbound
# UDP 53 to external resolvers. DoH uses HTTPS (TCP/443) to Cloudflare's
# anycast IP 1.1.1.1 — no system resolver, no UDP, just TCP to a known IP.
print('[dns-bootstrap] installing DoH socket.getaddrinfo patch', flush=True)

_dns_cache: dict[str, tuple[str, float]] = {}
_DNS_CACHE_TTL = 300  # seconds
_orig_getaddrinfo = socket.getaddrinfo


def _doh_resolve(hostname: str) -> str | None:
    """Resolve hostname via Cloudflare DoH at 1.1.1.1 (HTTPS, no DNS needed)."""
    now = time.monotonic()
    cached = _dns_cache.get(hostname)
    if cached and (now - cached[1] < _DNS_CACHE_TTL):
        return cached[0]

    for endpoint in ('https://1.1.1.1/dns-query', 'https://8.8.8.8/resolve'):
        try:
            url = f'{endpoint}?name={hostname}&type=A'
            req = urllib.request.Request(url, headers={'Accept': 'application/dns-json'})
            with urllib.request.urlopen(req, timeout=4) as resp:
                data = _json.loads(resp.read().decode())
            for ans in data.get('Answer', []):
                if ans.get('type') == 1:  # A record
                    ip = ans['data']
                    _dns_cache[hostname] = (ip, now)
                    print(f'[dns-bootstrap] {hostname} → {ip} (via {endpoint})', flush=True)
                    return ip
        except Exception as e:
            print(f'[dns-bootstrap] {endpoint} failed for {hostname}: {e}', flush=True)
    return None


def _patched_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
    if host and isinstance(host, str) and not host.replace('.', '').replace(':', '').isdigit():
        ip = _doh_resolve(host)
        if ip:
            return _orig_getaddrinfo(ip, port, family, type, proto, flags)
    return _orig_getaddrinfo(host, port, family, type, proto, flags)


socket.getaddrinfo = _patched_getaddrinfo

# Sanity check at startup — try to resolve Jupiter immediately so we see the
# result in logs before the main loop starts.
_test = _doh_resolve('quote-api.jup.ag')
print(f'[dns-bootstrap] startup resolve quote-api.jup.ag = {_test}', flush=True)

import config
import logger as swarm_log
from price_feed import get_price_snapshot
from detector import find_opportunity
from circuit_breaker import CircuitBreaker

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    datefmt='%H:%M:%S',
)
log = logging.getLogger('arb-keeper')

# Suppress noisy httpx logs
logging.getLogger('httpx').setLevel(logging.WARNING)
logging.getLogger('httpcore').setLevel(logging.WARNING)


def _load_wallet():
    """Load keypair if execution is enabled. Returns (keypair, pubkey_str)."""
    if not config.EXECUTE_TRADES:
        return None, None
    from wallet import load_keypair
    kp = load_keypair()
    pubkey = str(kp.pubkey())
    log.info(f'Keeper wallet: {pubkey}')
    return kp, pubkey


async def _get_balance(pubkey: str) -> float:
    if not pubkey:
        return 999.0  # dummy balance for detect-only mode
    from wallet import get_sol_balance
    try:
        return await get_sol_balance(pubkey)
    except Exception as e:
        log.warning(f'Balance check failed: {e}')
        return 0.0


async def run():
    mode = 'EXECUTE' if config.EXECUTE_TRADES else 'DETECT-ONLY'
    log.info(f'arb-keeper starting — mode: {mode}')
    log.info(f'MIN_PROFIT={config.MIN_PROFIT_SOL*1000:.2f} mSOL  '
             f'MAX_TRADE={config.MAX_TRADE_SOL} SOL  '
             f'POLL={config.POLL_INTERVAL}s  '
             f'TIP={config.JITO_TIP_LAMPORTS} lamports')

    keypair, pubkey = _load_wallet()
    cb = CircuitBreaker()

    # Heartbeat counter — log circuit status every 60 polls
    heartbeat = 0
    opps_seen  = 0
    trades_run = 0

    while True:
        loop_start = time.monotonic()

        try:
            # ── Circuit check ────────────────────────────────────────────────
            if config.EXECUTE_TRADES and cb.is_open():
                await asyncio.sleep(config.POLL_INTERVAL)
                continue

            # ── Price snapshot ───────────────────────────────────────────────
            snapshot = await get_price_snapshot(probe_sol=config.PROBE_SOL)
            if snapshot is None:
                log.debug('Price snapshot unavailable — skipping')
                await asyncio.sleep(config.POLL_INTERVAL)
                continue

            # ── Balance check ────────────────────────────────────────────────
            sol_balance = await _get_balance(pubkey)

            # ── Detect opportunity ───────────────────────────────────────────
            opp = find_opportunity(snapshot, sol_balance)

            if opp:
                opps_seen += 1
                swarm_log.log_opportunity(opp)

                if config.EXECUTE_TRADES:
                    # ── Execute ──────────────────────────────────────────────
                    from executor import execute_arb
                    result = await execute_arb(opp, keypair)
                    trades_run += 1
                    swarm_log.log_trade(result)

                    if result.success:
                        cb.record_success(result.actual_profit_sol or opp.net_profit_sol)
                    else:
                        # Only count as a loss if the bundle was submitted (not a build failure)
                        loss = 0.0
                        if result.bundle_id:
                            # Tip was spent even if bundle timed out
                            loss = config.JITO_TIP_LAMPORTS / config.SOL_LAMPORTS
                        cb.record_failure(loss)
                else:
                    log.info(f'[DETECT-ONLY] Would execute: {opp.describe()}')

            # ── Periodic heartbeat ───────────────────────────────────────────
            heartbeat += 1
            if heartbeat % 60 == 0:
                bal_str = f'{sol_balance:.4f} SOL' if pubkey else 'n/a'
                log.info(
                    f'Heartbeat: {opps_seen} opps seen | {trades_run} trades run | '
                    f'balance {bal_str} | spread {snapshot.spread_pct:.4f}%'
                )
                swarm_log.log_circuit_status({**cb.status(), 'opps_seen': opps_seen, 'trades_run': trades_run})

        except Exception as e:
            log.error(f'Main loop error: {e}', exc_info=True)

        # ── Pace to poll interval ────────────────────────────────────────────
        elapsed = time.monotonic() - loop_start
        sleep_for = max(0.0, config.POLL_INTERVAL - elapsed)
        await asyncio.sleep(sleep_for)


if __name__ == '__main__':
    asyncio.run(run())
