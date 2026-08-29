"""Static file server for redacted.meme.

Serves the landing page and proxies one small piece of live data:

  GET /api/swarm  — agent heartbeats, fetched server-side from the swarm's own
                    status endpoint (SWARM_STATUS_URL) and cached briefly. Proxying
                    rather than fetching from the browser keeps the mesh's address out
                    of the page source, sidesteps CORS, and shields the node from page
                    traffic. Any failure degrades to {"agents": []}, which the front end
                    renders as an absent section rather than an error.
"""
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
    """Fetch and re-shape the upstream status payload. Never raises."""
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

    agents = raw.get('agents')
    if not isinstance(agents, list):
        return {'agents': []}

    # Re-project onto exactly the fields the page renders — anything the upstream
    # adds later stays off the public surface until it is deliberately allowed here.
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
    return {'agents': clean, 'ts': raw.get('ts')}


@app.route('/api/swarm')
def api_swarm():
    now = time.time()
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
