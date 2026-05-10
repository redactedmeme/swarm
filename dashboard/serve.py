"""REDACTED SWARM Volume Tracker — dashboard server with snapshot history API."""
import os
import json
import time
import threading
import urllib.request
from http.server import HTTPServer, SimpleHTTPRequestHandler

TOKEN = '9a21gb7fWGm9dD2UFdZAzgFn5K1NwfmYkjyLbpAcKgnM'
DEXSCREENER_URL = f'https://api.dexscreener.com/latest/dex/tokens/{TOKEN}'
SNAPSHOT_INTERVAL = 1800  # 30 minutes
MAX_SNAPSHOTS = 336       # 7 days of 30-min snapshots

snapshots = []
snapshots_lock = threading.Lock()


def take_snapshot():
    try:
        req = urllib.request.Request(DEXSCREENER_URL, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())

        pairs = data.get('pairs', [])

        def vol(p, k): return (p.get('volume') or {}).get(k, 0) or 0
        def liq(p):    return ((p.get('liquidity') or {}).get('usd', 0) or 0)
        def txn(p, k): return (p.get('txns', {}).get('h24', {}).get(k, 0) or 0)

        entry = {
            'ts':     int(time.time()),
            'vol24h': sum(vol(p, 'h24') for p in pairs),
            'vol6h':  sum(vol(p, 'h6')  for p in pairs),
            'vol1h':  sum(vol(p, 'h1')  for p in pairs),
            'liq':    sum(liq(p)        for p in pairs),
            'buys':   sum(txn(p, 'buys') for p in pairs),
            'sells':  sum(txn(p, 'sells') for p in pairs),
            'price':  float(pairs[0].get('priceUsd', 0) or 0) if pairs else 0,
            'mcap':   float(pairs[0].get('marketCap') or pairs[0].get('fdv') or 0) if pairs else 0,
            'pools':  len(pairs),
        }

        with snapshots_lock:
            snapshots.append(entry)
            if len(snapshots) > MAX_SNAPSHOTS:
                snapshots.pop(0)

        print(f'[snapshot] {time.strftime("%H:%M")} vol24h=${entry["vol24h"]:.0f} '
              f'liq=${entry["liq"]:.0f} pools={entry["pools"]}')
    except Exception as e:
        print(f'[snapshot error] {e}')


def snapshot_loop():
    take_snapshot()
    while True:
        time.sleep(SNAPSHOT_INTERVAL)
        take_snapshot()


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=os.path.dirname(os.path.abspath(__file__)), **kwargs)

    def do_GET(self):
        if self.path == '/api/snapshots':
            with snapshots_lock:
                body = json.dumps(snapshots).encode()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.send_header('Cache-Control', 'no-cache')
            self.end_headers()
            self.wfile.write(body)
            return

        if self.path in ('/', ''):
            self.path = '/index.html'
        super().do_GET()

    def end_headers(self):
        if not self.path.startswith('/api/'):
            self.send_header('Cache-Control', 'no-cache, max-age=300')
        super().end_headers()

    def log_message(self, fmt, *args):
        # Silence noisy snapshot polling
        if args and str(args[0]).startswith('GET /api/snapshots'):
            return
        super().log_message(fmt, *args)


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 3001))

    t = threading.Thread(target=snapshot_loop, daemon=True)
    t.start()
    print(f'Dashboard running on port {port} — snapshots every {SNAPSHOT_INTERVAL // 60}m')

    server = HTTPServer(('0.0.0.0', port), Handler)
    server.serve_forever()
