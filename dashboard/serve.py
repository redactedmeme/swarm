"""REDACTED SWARM Volume Tracker — dashboard server with snapshots + live trade feed."""
import os
import json
import time
import threading
import urllib.request
from http.server import HTTPServer, SimpleHTTPRequestHandler

TOKEN         = '9a21gb7fWGm9dD2UFdZAzgFn5K1NwfmYkjyLbpAcKgnM'
HELIUS_KEY    = os.environ.get('HELIUS_API_KEY', '')
DEXSCREENER   = f'https://api.dexscreener.com/latest/dex/tokens/{TOKEN}'
HELIUS_TXN    = 'https://api-mainnet.helius-rpc.com/v0/addresses/{addr}/transactions/?api-key={key}&type=SWAP&limit=30'

SNAPSHOT_INTERVAL = 1800   # 30 min
TRADES_INTERVAL   = 30     # seconds
MAX_SNAPSHOTS     = 336    # 7 days of 30-min snapshots
MAX_TRADES        = 100
TOP_POOLS_COUNT   = 5      # query top N pools for live trades

# ── Shared state ──────────────────────────────────────────────────────────────

snapshots      = []
snapshots_lock = threading.Lock()

trades_cache   = []
trades_lock    = threading.Lock()

top_pools      = []   # [{addr, label, dex}] — updated from DexScreener
top_pools_lock = threading.Lock()

last_sigs      = {}   # pool_addr → newest sig seen (for incremental fetches)

# ── DexScreener snapshot ──────────────────────────────────────────────────────

def take_snapshot():
    try:
        req = urllib.request.Request(DEXSCREENER, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())

        pairs = data.get('pairs', [])
        pairs.sort(key=lambda p: (p.get('volume') or {}).get('h24', 0) or 0, reverse=True)

        def v(p, k): return (p.get('volume') or {}).get(k, 0) or 0
        def liq(p):  return ((p.get('liquidity') or {}).get('usd', 0) or 0)
        def txn(p, k): return (p.get('txns', {}).get('h24', {}).get(k, 0) or 0)

        entry = {
            'ts':     int(time.time()),
            'vol24h': sum(v(p, 'h24') for p in pairs),
            'vol6h':  sum(v(p, 'h6')  for p in pairs),
            'vol1h':  sum(v(p, 'h1')  for p in pairs),
            'liq':    sum(liq(p)      for p in pairs),
            'buys':   sum(txn(p, 'buys')  for p in pairs),
            'sells':  sum(txn(p, 'sells') for p in pairs),
            'price':  float(pairs[0].get('priceUsd', 0) or 0) if pairs else 0,
            'mcap':   float(pairs[0].get('marketCap') or pairs[0].get('fdv') or 0) if pairs else 0,
            'pools':  len(pairs),
        }

        with snapshots_lock:
            snapshots.append(entry)
            if len(snapshots) > MAX_SNAPSHOTS:
                snapshots.pop(0)

        # Update top pool list for trade fetching
        with top_pools_lock:
            top_pools.clear()
            for p in pairs[:TOP_POOLS_COUNT]:
                base  = (p.get('baseToken')  or {}).get('symbol', '?')
                quote = (p.get('quoteToken') or {}).get('symbol', '?')
                top_pools.append({
                    'addr':  p.get('pairAddress', ''),
                    'label': f'{base}/{quote}',
                    'dex':   p.get('dexId', 'unknown'),
                })

        print(f'[snapshot] {time.strftime("%H:%M")} vol24h=${entry["vol24h"]:.0f} '
              f'liq=${entry["liq"]:.0f} pools={entry["pools"]}')
    except Exception as e:
        print(f'[snapshot error] {e}')


def snapshot_loop():
    take_snapshot()
    while True:
        time.sleep(SNAPSHOT_INTERVAL)
        take_snapshot()

# ── Helius trade fetch ────────────────────────────────────────────────────────

def fetch_trades_for_pool(pool_addr, pool_label, dex):
    if not HELIUS_KEY:
        return []

    url = HELIUS_TXN.format(addr=pool_addr, key=HELIUS_KEY)
    until = last_sigs.get(pool_addr)
    if until:
        url += f'&until={until}'

    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=10) as resp:
            txns = json.loads(resp.read())
    except Exception as e:
        print(f'[trades error] {pool_label}: {e}')
        return []

    if not txns:
        return []

    # Advance cursor so next poll only gets newer txns
    last_sigs[pool_addr] = txns[0].get('signature', until)

    results = []
    for tx in txns:
        sig = tx.get('signature', '')
        ts  = tx.get('timestamp', int(time.time()))

        swap = (tx.get('events') or {}).get('swap') or {}
        if not swap:
            continue

        t_in   = swap.get('tokenInputs',  [])
        t_out  = swap.get('tokenOutputs', [])
        n_in   = swap.get('nativeInput')  or {}
        n_out  = swap.get('nativeOutput') or {}

        redacted_in  = next((t for t in t_in  if t.get('mint') == TOKEN), None)
        redacted_out = next((t for t in t_out if t.get('mint') == TOKEN), None)

        if redacted_out:
            direction = 'buy'
            raw_tok   = redacted_out.get('rawTokenAmount', {})
            tok_amt   = float(raw_tok.get('tokenAmount', 0)) / (10 ** int(raw_tok.get('decimals', 6)))
            sol_amt   = int(n_in.get('amount', 0)) / 1e9
        elif redacted_in:
            direction = 'sell'
            raw_tok   = redacted_in.get('rawTokenAmount', {})
            tok_amt   = float(raw_tok.get('tokenAmount', 0)) / (10 ** int(raw_tok.get('decimals', 6)))
            sol_amt   = int(n_out.get('amount', 0)) / 1e9
        else:
            continue  # doesn't involve REDACTED

        # Approximate USD from snapshots price if available
        price = 0.0
        with snapshots_lock:
            if snapshots:
                price = snapshots[-1].get('price', 0)
        usd_val = tok_amt * price if price else sol_amt * 150  # fallback: SOL≈$150

        wallet = tx.get('feePayer', '')
        short_wallet = wallet[:4] + '..' + wallet[-4:] if len(wallet) > 8 else wallet

        results.append({
            'sig':       sig,
            'ts':        ts,
            'pool':      pool_label,
            'dex':       dex,
            'direction': direction,
            'tok_amt':   round(tok_amt, 2),
            'sol_amt':   round(sol_amt, 6),
            'usd_val':   round(usd_val, 4),
            'wallet':    short_wallet,
        })

    return results


def fetch_all_trades():
    with top_pools_lock:
        pools = list(top_pools)

    if not pools:
        return

    new_trades = []
    for p in pools:
        if not p.get('addr'):
            continue
        trades = fetch_trades_for_pool(p['addr'], p['label'], p['dex'])
        new_trades.extend(trades)

    if not new_trades:
        return

    # Dedup by sig, merge with cache
    with trades_lock:
        existing_sigs = {t['sig'] for t in trades_cache}
        fresh = [t for t in new_trades if t['sig'] not in existing_sigs]
        trades_cache[:0] = sorted(fresh, key=lambda t: t['ts'], reverse=True)
        if len(trades_cache) > MAX_TRADES:
            del trades_cache[MAX_TRADES:]

    print(f'[trades] +{len(fresh)} new swaps (total {len(trades_cache)})')


def trades_loop():
    # Wait for first snapshot so top_pools is populated
    for _ in range(60):
        with top_pools_lock:
            if top_pools:
                break
        time.sleep(1)

    while True:
        fetch_all_trades()
        time.sleep(TRADES_INTERVAL)

# ── HTTP server ───────────────────────────────────────────────────────────────

class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=os.path.dirname(os.path.abspath(__file__)), **kwargs)

    def do_GET(self):
        if self.path == '/api/snapshots':
            with snapshots_lock:
                body = json.dumps(snapshots).encode()
            self._json(body)
            return

        if self.path == '/api/trades':
            with trades_lock:
                body = json.dumps(trades_cache).encode()
            self._json(body)
            return

        if self.path in ('/', ''):
            self.path = '/index.html'
        super().do_GET()

    def _json(self, body):
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Cache-Control', 'no-cache')
        self.end_headers()
        self.wfile.write(body)

    def end_headers(self):
        if not self.path.startswith('/api/'):
            self.send_header('Cache-Control', 'no-cache, max-age=300')
        super().end_headers()

    def log_message(self, fmt, *args):
        if args and str(args[0]).startswith(('GET /api/snapshots', 'GET /api/trades')):
            return
        super().log_message(fmt, *args)


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 3001))

    threading.Thread(target=snapshot_loop, daemon=True).start()
    threading.Thread(target=trades_loop,   daemon=True).start()

    print(f'Dashboard on port {port} | snapshots every {SNAPSHOT_INTERVAL//60}m | '
          f'trades every {TRADES_INTERVAL}s | helius={"✓" if HELIUS_KEY else "✗ (set HELIUS_API_KEY)"}')

    HTTPServer(('0.0.0.0', port), Handler).serve_forever()
