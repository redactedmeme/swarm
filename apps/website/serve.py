"""Static file server for redacted.meme.

Serves the landing page and proxies one small piece of live data:

  GET /api/swarm  — agent heartbeats, fetched server-side from the swarm's own
                    status endpoint (SWARM_STATUS_URL) and cached briefly. Proxying
                    rather than fetching from the browser keeps the mesh's address out
                    of the page source, sidesteps CORS, and shields the node from page
                    traffic. Any failure degrades to {"agents": []}, which the front end
                    renders as an absent section rather than an error.
"""
import hmac
import json
import os
import pathlib
import threading
import time
import urllib.error
import urllib.request

from flask import Flask, Response, jsonify, request, send_from_directory

ROOT = pathlib.Path(__file__).resolve().parent

app = Flask(__name__, static_folder=None)

# ── Config ────────────────────────────────────────────────────────────────────

SWARM_STATUS_URL = os.environ.get('SWARM_STATUS_URL', '').strip()
SWARM_STATUS_TIMEOUT = float(os.environ.get('SWARM_STATUS_TIMEOUT', '4'))
SWARM_CACHE_TTL = float(os.environ.get('SWARM_CACHE_TTL', '30'))

SITE_ORIGIN = 'https://redacted.meme'

IMMUTABLE_EXT = ('.woff2', '.woff', '.ttf', '.png', '.jpg', '.svg', '.ico')

# Stylesheet and script are the two files that change on almost every deploy, and their
# filenames never do — so an hour-long cache means an hour of visitors on the old CSS
# against the new HTML. Kept short and revalidated instead. Fonts and images stay
# immutable: their content genuinely doesn't change.
VERSIONED_EXT = ('.css', '.js')

# Flask guesses application/octet-stream for .md, which makes browsers download it
# and tells an agent nothing. These are published documents - label them as such.
TEXT_TYPES = {
    '.md': 'text/markdown; charset=utf-8',
    '.txt': 'text/plain; charset=utf-8',
}

# Published for machines as much as for people: everything an agent might fetch is
# readable cross-origin, including from a browser-based one.
PUBLIC_EXT = ('.md', '.txt', '.json')

CSP = (
    "default-src 'self'; "
    "script-src 'self' 'unsafe-inline'; "
    "style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data:; "
    "font-src 'self'; "
    "connect-src 'self' https://api.dexscreener.com; "
    "frame-ancestors 'none'; "
    "base-uri 'self'; "
    "form-action 'none'"
)

# ── Swarm status proxy ────────────────────────────────────────────────────────

_cache_lock = threading.Lock()
_cache = {'ts': 0.0, 'payload': {'agents': []}}


def _fetch_swarm_status():
    """Fetch and re-shape the upstream status payload. Never raises.

    Only used when SWARM_STATUS_URL is set. The node has no inbound route from
    the internet, so the supported path is the push below; this pull remains for
    a deployment that can reach its node directly.
    """
    if not SWARM_STATUS_URL:
        return {'agents': []}
    try:
        req = urllib.request.Request(
            SWARM_STATUS_URL, headers={'User-Agent': 'redacted-website/1.0'}
        )
        with urllib.request.urlopen(req, timeout=SWARM_STATUS_TIMEOUT) as r:
            raw = json.loads(r.read().decode('utf-8'))
    except (urllib.error.URLError, OSError, ValueError, json.JSONDecodeError):
        return {'agents': []}
    return _project(raw)


def _project(raw):
    """Re-project an upstream payload onto exactly the fields this page renders.

    The same whitelist applies whether the payload was pulled or pushed —
    anything the upstream adds later stays off the public surface until it is
    deliberately allowed here.
    """
    agents = raw.get('agents')
    if not isinstance(agents, list):
        return {'agents': []}

    clean = []
    for a in agents:
        if not isinstance(a, dict) or not a.get('id'):
            continue
        entry = {
            'id': str(a['id'])[:40],
            'label': str(a.get('label') or a['id'])[:60],
            'online': bool(a.get('online')),
            'last_seen': str(a.get('last_seen_bucket') or a.get('last_seen') or '')[:40],
        }
        # Queue depth, when the upstream reports it. Coerced and clamped rather than
        # passed through, and simply omitted when absent or unparseable — the page
        # treats a missing field as "no reading", which is the honest render.
        pending = a.get('pending')
        if isinstance(pending, (int, float)) and not isinstance(pending, bool):
            entry['pending'] = max(0, min(int(pending), 10 ** 7))
        clean.append(entry)

    out = {'agents': clean, 'ts': raw.get('ts')}
    offers = _clean_offers(raw)
    if offers:
        out['offers'] = offers
    treasury = _clean_treasury(raw)
    if treasury:
        out['treasury'] = treasury
    return out


def _int0(v):
    """Non-negative int, or 0 — for counters that must never render negative."""
    try:
        return max(0, int(v))
    except (TypeError, ValueError):
        return 0


def _clean_offers(raw):
    """The price sheet, re-projected. Same discipline as the agent list: a
    whitelist of fields, strings capped, and a row with no price is still shown
    (it exists) but carries no number the page could misrender."""
    out = []
    for o in raw.get('offers') or []:
        if not isinstance(o, dict) or not o.get('id'):
            continue
        entry = {
            'id': str(o['id'])[:40],
            'agent': str(o.get('agent') or '')[:40],
            'title': str(o.get('title') or '')[:200],
            'kind': str(o.get('kind') or '')[:20],
            'open': bool(o.get('open')),
        }
        price = o.get('price')
        if isinstance(price, dict) and price.get('amount'):
            entry['price'] = {
                'amount': str(price['amount'])[:32],
                'asset': str(price.get('asset') or '')[:64],
            }
            dec = price.get('decimals')
            if isinstance(dec, int) and not isinstance(dec, bool):
                entry['price']['decimals'] = max(0, min(dec, 18))
        out.append(entry)
    return out


def _clean_treasury(raw):
    """Burn / settlement totals + the recent-settlement feed. Numbers stay as
    strings (they are base-unit-derived and can exceed JS safe-int); the feed
    drops the payer wallet and the exact timestamp — the upstream already sends
    a coarse age bucket."""
    t = raw.get('treasury')
    if not isinstance(t, dict):
        return None

    def s(k, cap=64):
        return str(t.get(k) or '')[:cap]

    # Base58 Solana signatures are ~88 chars — cap the sig fields well above that
    # so a real one is never truncated into a broken Solscan link.
    out = {
        'burned_total': s('burned_total') or '0',
        'burn_accrued': s('burn_accrued') or '0',
        'revenue_total': s('revenue_total') or '0',
        'settlements_24h': _int0(t.get('settlements_24h')),
        'settlements_total': _int0(t.get('settlements_total')),
        'last_settlement_sig': s('last_settlement_sig', 100) or None,
        'last_burn_sig': s('last_burn_sig', 100) or None,
    }
    rd = t.get('runway_days')
    if isinstance(rd, (int, float)) and not isinstance(rd, bool):
        out['runway_days'] = round(float(rd), 1)
    split = t.get('split')
    if isinstance(split, dict):
        out['split'] = {k: _int0(split.get(k)) for k in ('burn', 'compute', 'rewards')}

    recent = []
    for e in t.get('recent') or []:
        if not isinstance(e, dict) or not e.get('sig'):
            continue
        recent.append({
            'sig': str(e['sig'])[:100],
            'endpoint': str(e.get('endpoint') or '')[:40],
            'amount': str(e.get('amount') or '')[:32],
            'burn': str(e.get('burn') or '')[:32],
            'age': str(e.get('age') or '')[:40],
        })
        if len(recent) >= 20:
            break
    out['recent'] = recent
    return out


# ── Pushed status ─────────────────────────────────────────────────────────────
#
# The swarm node has no inbound route from the internet, and redacted.meme's DNS
# is not on Cloudflare, so a tunnelled hostname for the node is not available.
# The node therefore pushes: apps/status POSTs its payload here behind a shared
# secret, and this serves it.
#
# Freshness is the thing to get right. A pull that fails renders an absent
# section, which is honest. A push that stops would leave the last payload
# sitting here reading "online" forever, so anything older than STATUS_MAX_AGE
# is discarded and the page goes back to showing nothing.

STATUS_PUSH_TOKEN = os.environ.get('STATUS_PUSH_TOKEN', '').strip()
STATUS_MAX_AGE = float(os.environ.get('STATUS_MAX_AGE', '300'))

_pushed = {'ts': 0.0, 'payload': None}


@app.route('/api/swarm/publish', methods=['POST'])
def api_swarm_publish():
    if not STATUS_PUSH_TOKEN:
        return jsonify({'error': 'status publishing not configured'}), 404
    supplied = request.headers.get('X-Status-Token', '')
    if not hmac.compare_digest(supplied, STATUS_PUSH_TOKEN):
        return jsonify({'error': 'unauthorized'}), 401

    raw = request.get_json(silent=True)
    if not isinstance(raw, dict) or not isinstance(raw.get('agents'), list):
        return jsonify({'error': 'payload must carry an agents list'}), 400

    payload = _project(raw)
    with _cache_lock:
        _pushed['ts'] = time.time()
        _pushed['payload'] = payload
    return jsonify({'ok': True, 'agents': len(payload.get('agents') or [])})


@app.route('/api/swarm')
def api_swarm():
    now = time.time()

    # A fresh push always wins; it is the only path that works for the node.
    with _cache_lock:
        pushed, pushed_ts = _pushed['payload'], _pushed['ts']
    if pushed is not None and now - pushed_ts < STATUS_MAX_AGE:
        resp = jsonify(pushed)
        resp.headers['Cache-Control'] = 'public, max-age=30'
        resp.headers['Access-Control-Allow-Origin'] = '*'
        return resp

    with _cache_lock:
        fresh = now - _cache['ts'] < SWARM_CACHE_TTL
        payload = _cache['payload']
    if not fresh:
        payload = _fetch_swarm_status()
        with _cache_lock:
            _cache['ts'] = now
            _cache['payload'] = payload
    resp = jsonify(payload)
    resp.headers['Cache-Control'] = 'public, max-age=30'
    resp.headers['Access-Control-Allow-Origin'] = '*'
    return resp


# ── Meta routes ───────────────────────────────────────────────────────────────

@app.route('/healthz')
def healthz():
    return jsonify(status='ok')


@app.route('/robots.txt')
def robots():
    body = (
        "User-agent: *\n"
        "Allow: /\n"
        "\n"
        "# Agents: /llms.txt indexes every published artifact; /llms-full.txt returns\n"
        "# the same index with the system prompt and skill inlined, in one request.\n"
        f"Sitemap: {SITE_ORIGIN}/sitemap.xml\n"
    )
    return Response(body, mimetype='text/plain')


@app.route('/sitemap.xml')
def sitemap():
    body = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f'  <url><loc>{SITE_ORIGIN}/</loc><changefreq>weekly</changefreq><priority>1.0</priority></url>\n'
        f'  <url><loc>{SITE_ORIGIN}/docs</loc><changefreq>weekly</changefreq><priority>0.9</priority></url>\n'
        f'  <url><loc>{SITE_ORIGIN}/token</loc><changefreq>weekly</changefreq><priority>0.9</priority></url>\n'
        f'  <url><loc>{SITE_ORIGIN}/llms.txt</loc><changefreq>weekly</changefreq><priority>0.8</priority></url>\n'
        f'  <url><loc>{SITE_ORIGIN}/llms-full.txt</loc><changefreq>weekly</changefreq><priority>0.5</priority></url>\n'
        f'  <url><loc>{SITE_ORIGIN}/system.prompt.md</loc><changefreq>weekly</changefreq><priority>0.8</priority></url>\n'
        f'  <url><loc>{SITE_ORIGIN}/skill.md</loc><changefreq>weekly</changefreq><priority>0.8</priority></url>\n'
        '</urlset>\n'
    )
    return Response(body, mimetype='application/xml')


# ── Static ────────────────────────────────────────────────────────────────────

@app.route('/')
def index():
    return send_from_directory(ROOT, 'index.html')


# The plain-language pages. Served extensionless so the published URLs are
# /token and /docs; the catch-all below would 404 those, since it only maps a
# path onto a file that literally exists.
@app.route('/token')
def token_page():
    return send_from_directory(ROOT, 'token.html')


@app.route('/docs')
def docs_page():
    return send_from_directory(ROOT, 'docs.html')


@app.route('/<path:path>')
def static_files(path):
    return send_from_directory(ROOT, path)


@app.after_request
def add_headers(resp):
    resp.headers.setdefault('X-Content-Type-Options', 'nosniff')
    resp.headers.setdefault('Referrer-Policy', 'strict-origin-when-cross-origin')
    resp.headers.setdefault('X-Frame-Options', 'DENY')
    resp.headers.setdefault('Content-Security-Policy', CSP)
    # send_from_directory sets 'no-cache' by default, so static responses are
    # overridden rather than defaulted.
    if request.endpoint in ('index', 'static_files'):
        path = request.path.lower()
        for ext, ctype in TEXT_TYPES.items():
            if path.endswith(ext):
                resp.headers['Content-Type'] = ctype
                break
        if path.endswith(PUBLIC_EXT):
            resp.headers['Access-Control-Allow-Origin'] = '*'
        lower = request.path.lower()
        if lower.endswith(IMMUTABLE_EXT):
            resp.headers['Cache-Control'] = 'public, max-age=31536000, immutable'
        elif lower.endswith(VERSIONED_EXT):
            resp.headers['Cache-Control'] = 'public, max-age=60, must-revalidate'
        elif resp.headers.get('Content-Type', '').startswith('text/html'):
            resp.headers['Cache-Control'] = 'public, max-age=300'
        else:
            resp.headers['Cache-Control'] = 'public, max-age=3600'
    return resp


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port, debug=False)
