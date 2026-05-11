"""REDACTED SWARM Volume Tracker — dashboard server with snapshots + live trade feed."""
import os
import json
import time
import base64
import struct
import threading
import urllib.request
from http.server import HTTPServer, SimpleHTTPRequestHandler

TOKEN         = '9a21gb7fWGm9dD2UFdZAzgFn5K1NwfmYkjyLbpAcKgnM'
V2_TOKEN      = '9mtKd1o8Ht7F1daumKgs5D8EdVyopWBfYQwNmMojpump'
HELIUS_KEY    = os.environ.get('HELIUS_API_KEY', '')
DEXSCREENER   = f'https://api.dexscreener.com/latest/dex/tokens/{TOKEN}'
DEXSCREENER_V2 = f'https://api.dexscreener.com/latest/dex/tokens/{V2_TOKEN}'
HELIUS_RPC    = 'https://mainnet.helius-rpc.com/?api-key={key}'
HELIUS_TXN    = 'https://api-mainnet.helius-rpc.com/v0/addresses/{addr}/transactions/?api-key={key}&type=SWAP&limit=30'

V1V2_POOL     = '8Jd4KxLXhSqJx3wx7WRujfLZ7hmddVQkoM4qJqg4cPHo'
ORCA_POOL_API = f'https://api.mainnet.orca.so/v1/whirlpool/{V1V2_POOL}'

# Pools that are always included regardless of DexScreener ranking
PINNED_POOLS  = [
    {'addr': V1V2_POOL, 'label': 'REDACTED (liquidity)/REDACTED (fees)', 'dex': 'orca'},
]

SNAPSHOT_INTERVAL   = 1800   # 30 min
TRADES_INTERVAL     = 30     # seconds
TOKEN_INFO_INTERVAL = 1800   # 30 min
MAX_SNAPSHOTS       = 336    # 7 days of 30-min snapshots
MAX_TRADES          = 100
TOP_POOLS_COUNT     = 5      # query top N pools for live trades

# ── Shared state ──────────────────────────────────────────────────────────────

snapshots      = []
snapshots_lock = threading.Lock()

trades_cache   = []
trades_lock    = threading.Lock()

top_pools      = []   # [{addr, label, dex}] — updated from DexScreener
top_pools_lock = threading.Lock()

token_info     = {}   # holder count, top holders, supply, authorities
token_info_lock = threading.Lock()

v2_snapshot    = {}   # latest v2 token market data
v2_lock        = threading.Lock()

v1v2_pool      = {}   # Orca Whirlpool data for the v1/v2 pair
v1v2_lock      = threading.Lock()

last_sigs      = {}   # pool_addr → newest sig seen (for incremental fetches)

# ── Helius RPC helper ─────────────────────────────────────────────────────────

def helius_rpc(method, params):
    if not HELIUS_KEY:
        return {}
    url  = HELIUS_RPC.format(key=HELIUS_KEY)
    body = json.dumps({'jsonrpc': '2.0', 'id': 1, 'method': method, 'params': params}).encode()
    req  = urllib.request.Request(url, data=body,
                                  headers={'Content-Type': 'application/json', 'User-Agent': 'Mozilla/5.0'})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read())
    except Exception as e:
        print(f'[helius rpc] {method}: {e}')
        return {}

# ── Helius token info ─────────────────────────────────────────────────────────

def _parse_mint_authorities(b64_data):
    """Parse SPL Token mint account layout to extract mint/freeze authority status."""
    try:
        raw = base64.b64decode(b64_data)
        # Layout: 4B coption + 32B mint_auth + 8B supply + 1B decimals + 1B init + 4B coption + 32B freeze_auth
        mint_revoked   = struct.unpack_from('<I', raw, 0)[0] == 0
        freeze_revoked = len(raw) >= 50 and struct.unpack_from('<I', raw, 46)[0] == 0
        return mint_revoked, freeze_revoked
    except Exception:
        return None, None

def fetch_token_info():
    if not HELIUS_KEY:
        return

    info = {}

    # 1. Supply
    resp = helius_rpc('getTokenSupply', [TOKEN])
    val  = (resp.get('result') or {}).get('value') or {}
    info['supply']   = int(val.get('amount', 0))
    info['decimals'] = int(val.get('decimals', 6))
    info['supply_ui'] = float(val.get('uiAmount') or 0)

    # 2. Mint account — authorities
    resp = helius_rpc('getAccountInfo', [TOKEN, {'encoding': 'base64'}])
    acct = ((resp.get('result') or {}).get('value') or {})
    acct_data = (acct.get('data') or [None])[0]
    mint_rev, freeze_rev = _parse_mint_authorities(acct_data) if acct_data else (None, None)
    info['mint_authority_revoked']   = mint_rev
    info['freeze_authority_revoked'] = freeze_rev

    # 3. Largest accounts — top holder concentration
    resp     = helius_rpc('getTokenLargestAccounts', [TOKEN])
    accounts = (resp.get('result') or {}).get('value') or []
    supply_ui = info['supply_ui'] or 1
    top10_amt = sum(float(a.get('uiAmount') or 0) for a in accounts[:10])
    info['top10_pct']     = round(top10_amt / supply_ui * 100, 2) if supply_ui else None
    info['top_holders']   = [
        {'address': a.get('address',''), 'pct': round(float(a.get('uiAmount') or 0) / supply_ui * 100, 4)}
        for a in accounts[:10]
    ]

    # 4. Holder count via getTokenAccounts (paginated, cap at 10 pages)
    holder_count = 0
    page = 1
    while page <= 10:
        resp = helius_rpc('getTokenAccounts', {'mint': TOKEN, 'limit': 1000, 'page': page})
        result   = (resp.get('result') or {})
        accounts_page = result.get('token_accounts') or []
        holder_count += len(accounts_page)
        if len(accounts_page) < 1000:
            break
        page += 1
    info['holder_count'] = holder_count
    info['holder_count_capped'] = page > 10  # True if we stopped early

    # 5. Token image via Helius DAS getAsset
    resp = helius_rpc('getAsset', {'id': TOKEN})
    das  = resp.get('result') or {}
    info['image_url'] = (das.get('content') or {}).get('links', {}).get('image', '')

    with token_info_lock:
        token_info.clear()
        token_info.update(info)

    print(f'[token info] holders={holder_count} top10={info.get("top10_pct")}% '
          f'mint_rev={mint_rev} freeze_rev={freeze_rev}')

def token_info_loop():
    fetch_token_info()
    while True:
        time.sleep(TOKEN_INFO_INTERVAL)
        fetch_token_info()

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
            'mcap':      float(pairs[0].get('marketCap') or pairs[0].get('fdv') or 0) if pairs else 0,
            'pools':     len(pairs),
            'image_url': (pairs[0].get('info') or {}).get('imageUrl', '') if pairs else '',
        }

        with snapshots_lock:
            snapshots.append(entry)
            if len(snapshots) > MAX_SNAPSHOTS:
                snapshots.pop(0)

        # Update top pool list for trade fetching (DexScreener top N + pinned)
        known_addrs = {p['addr'] for p in PINNED_POOLS}
        with top_pools_lock:
            top_pools.clear()
            top_pools.extend(PINNED_POOLS)
            for p in pairs[:TOP_POOLS_COUNT]:
                addr  = p.get('pairAddress', '')
                if addr in known_addrs:
                    continue  # already pinned
                base  = (p.get('baseToken')  or {}).get('symbol', '?')
                quote = (p.get('quoteToken') or {}).get('symbol', '?')
                top_pools.append({
                    'addr':  addr,
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

# ── v2 token snapshot ─────────────────────────────────────────────────────────

def fetch_v2_data():
    try:
        req = urllib.request.Request(DEXSCREENER_V2, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())

        pairs = data.get('pairs') or []
        pairs.sort(key=lambda p: (p.get('volume') or {}).get('h24', 0) or 0, reverse=True)
        if not pairs:
            return

        def v(p, k): return (p.get('volume') or {}).get(k, 0) or 0
        def liq(p):  return (p.get('liquidity') or {}).get('usd', 0) or 0

        entry = {
            'ts':          int(time.time()),
            'price':       float(pairs[0].get('priceUsd') or 0),
            'mcap':        float(pairs[0].get('marketCap') or pairs[0].get('fdv') or 0),
            'vol24h':      sum(v(p, 'h24') for p in pairs),
            'vol6h':       sum(v(p, 'h6')  for p in pairs),
            'vol1h':       sum(v(p, 'h1')  for p in pairs),
            'liq':         sum(liq(p)      for p in pairs),
            'pools':       len(pairs),
            'priceChange': {
                'h1':  pairs[0].get('priceChange', {}).get('h1'),
                'h6':  pairs[0].get('priceChange', {}).get('h6'),
                'h24': pairs[0].get('priceChange', {}).get('h24'),
            },
            'image_url': (pairs[0].get('info') or {}).get('imageUrl', ''),
        }

        with v2_lock:
            v2_snapshot.clear()
            v2_snapshot.update(entry)

        print(f'[v2] price=${entry["price"]:.8f} mcap=${entry["mcap"]:.0f} vol24h=${entry["vol24h"]:.0f}')
    except Exception as e:
        print(f'[v2 error] {e}')

def v2_loop():
    fetch_v2_data()
    while True:
        time.sleep(SNAPSHOT_INTERVAL)
        fetch_v2_data()

# ── Orca v1/v2 pool ───────────────────────────────────────────────────────────

def fetch_v1v2_pool():
    try:
        req = urllib.request.Request(ORCA_POOL_API, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())

        entry = {
            'ts':       int(time.time()),
            'price':    float(data.get('price', 0)),          # v1 per v2
            'tvl':      float(data.get('tvlUsdc', 0)),
            'vol24h':   float(data.get('volume', {}).get('day', 0)),
            'vol7d':    float(data.get('volume', {}).get('week', 0)),
            'fee_rate': float(data.get('lpFeeRate', 0)),
            'tick_spacing': data.get('tickSpacing'),
            'liq_usd':  float(data.get('tvlUsdc', 0)),
        }

        with v1v2_lock:
            v1v2_pool.clear()
            v1v2_pool.update(entry)

        print(f'[v1v2 pool] price={entry["price"]:.6f} tvl=${entry["tvl"]:.0f} vol24h=${entry["vol24h"]:.0f}')
    except Exception as e:
        print(f'[v1v2 pool error] {e}')

def v1v2_loop():
    fetch_v1v2_pool()
    while True:
        time.sleep(SNAPSHOT_INTERVAL)
        fetch_v1v2_pool()

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

        if self.path == '/api/token':
            with token_info_lock:
                body = json.dumps(token_info).encode()
            self._json(body)
            return

        if self.path == '/api/v2':
            with v2_lock:
                body = json.dumps(v2_snapshot).encode()
            self._json(body)
            return

        if self.path == '/api/v1v2pool':
            with v1v2_lock:
                body = json.dumps(v1v2_pool).encode()
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
        if args and str(args[0]).startswith(('GET /api/snapshots', 'GET /api/trades', 'GET /api/token', 'GET /api/v2', 'GET /api/v1v2pool')):
            return
        super().log_message(fmt, *args)


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 3001))

    threading.Thread(target=snapshot_loop,    daemon=True).start()
    threading.Thread(target=trades_loop,      daemon=True).start()
    threading.Thread(target=token_info_loop,  daemon=True).start()
    threading.Thread(target=v2_loop,          daemon=True).start()
    threading.Thread(target=v1v2_loop,        daemon=True).start()

    print(f'Dashboard on port {port} | snapshots every {SNAPSHOT_INTERVAL//60}m | '
          f'trades every {TRADES_INTERVAL}s | helius={"✓" if HELIUS_KEY else "✗ (set HELIUS_API_KEY)"}')

    HTTPServer(('0.0.0.0', port), Handler).serve_forever()
