from gevent import monkey
monkey.patch_all()

# REDACTED Swarm — Hardened Web Terminal
# Security layer: auth, rate limiting, audit logging, Phantom wallet
# Feature layer: tool dispatch, skills, persistent sessions, Mem0, multi-provider LLM

from flask import Flask, render_template, request, jsonify, session
from flask_socketio import SocketIO, emit, disconnect
import os
import sys
import threading
import logging
import time
import re
import hashlib
import hmac
import json
import requests
from pathlib import Path
from datetime import datetime, timezone
from collections import defaultdict, deque
from functools import wraps
from swarm_core.paths import (
    repo_root as _repo_root,
    data_dir as _data_dir,
    mem0_dir as _mem0_dir,
)

# ── Path setup ────────────────────────────────────────────────────────────────

# Load .env from repo root before any os.getenv() calls
try:
    from dotenv import load_dotenv as _load_dotenv
    _load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))
except ImportError:
    pass

_MEM0_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'plugins', 'mem0-memory'))
if _MEM0_DIR not in sys.path:
    sys.path.insert(0, _MEM0_DIR)

# ── Flask app ─────────────────────────────────────────────────────────────────

app = Flask(__name__, template_folder='templates')
app.secret_key = os.getenv('FLASK_SECRET_KEY', hashlib.sha256(os.urandom(32)).hexdigest())

# ── Security configuration ────────────────────────────────────────────────────

def _truthy(name: str) -> bool:
    return os.getenv(name, '').strip().lower() in ('1', 'true', 'yes', 'on')

API_KEY                = os.getenv('WEB_TERMINAL_API_KEY')
CORS_ORIGINS           = os.getenv('WEB_CORS_ORIGINS', '*').split(',')
RUNTIME_API_URL        = os.getenv('RUNTIME_API_URL', 'http://localhost:4001')
MAX_COMMAND_LENGTH     = int(os.getenv('WEB_MAX_COMMAND_LENGTH', '4096'))
RATE_LIMIT_REQUESTS    = int(os.getenv('WEB_RATE_LIMIT', '10'))
RATE_LIMIT_WINDOW      = int(os.getenv('WEB_RATE_LIMIT_WINDOW', '60'))
PHANTOM_ALLOWED_ORIGINS = os.getenv('PHANTOM_ALLOWED_ORIGINS', 'http://localhost:5000').split(',')

# ── $REDACTED holder gate ─────────────────────────────────────────────────────
# Access is closed when EITHER a static WEB_TERMINAL_API_KEY is set OR HOLDER_GATE
# is on (sign a nonce, hold >= 1M $REDACTED). GATE_STRICT closes it even when
# neither is configured (otherwise: open, with a loud warning — dev convenience).
HOLDER_GATE   = _truthy('HOLDER_GATE')
GATE_STRICT   = _truthy('GATE_STRICT')
GATE_REDIS_URL = os.getenv('REDIS_URL', 'redis://localhost:6379')

try:
    import asyncio as _asyncio
    import redis.asyncio as _aioredis
    import swarm_core.gate as gate
    _GATE_AVAILABLE = True
except Exception as _e:  # noqa: BLE001
    _GATE_AVAILABLE = False
    if HOLDER_GATE:
        logging.getLogger(__name__).error("HOLDER_GATE set but swarm_core.gate import failed: %s", _e)


def _gate_required() -> bool:
    return bool(API_KEY) or HOLDER_GATE


def _run_gate(make_coro):
    """Run one gate coroutine on a throwaway loop with a fresh async Redis
    client (a redis.asyncio client is bound to the loop that created it)."""
    loop = _asyncio.new_event_loop()
    try:
        async def _wrap():
            r = _aioredis.from_url(GATE_REDIS_URL, decode_responses=True)
            try:
                return await make_coro(r)
            finally:
                await r.aclose()
        return loop.run_until_complete(_wrap())
    finally:
        loop.close()


if not _gate_required() and not GATE_STRICT:
    logging.getLogger(__name__).warning(
        "=" * 68 + "\n  TERMINAL IS UNAUTHENTICATED — neither WEB_TERMINAL_API_KEY "
        "nor HOLDER_GATE is set.\n  Set one, or GATE_STRICT=true to fail closed.\n" + "=" * 68
    )

# ── Audit logging ─────────────────────────────────────────────────────────────

LOG_DIR    = _data_dir() / 'audit'
LOG_DIR.mkdir(parents=True, exist_ok=True)
AUDIT_LOG  = LOG_DIR / 'web_terminal.log'

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(LOG_DIR / 'web_app.log', encoding='utf-8'),
    ]
)
logger = logging.getLogger(__name__)


def audit_log(event_type: str, session_id: str, command: str, status: str, details: dict = None):
    entry = {
        'timestamp': datetime.utcnow().isoformat(),
        'event':     event_type,
        'session':   session_id,
        'command':   command[:200] if command else '',
        'status':    status,
        'details':   details or {},
    }
    try:
        with open(AUDIT_LOG, 'a', encoding='utf-8') as f:
            f.write(json.dumps(entry) + '\n')
    except Exception as e:
        logger.error(f"Audit log write failed: {e}")

# ── Rate limiting ─────────────────────────────────────────────────────────────

rate_limits = defaultdict(lambda: deque(maxlen=RATE_LIMIT_REQUESTS))


def check_rate_limit(session_id: str) -> bool:
    now          = time.time()
    window_start = now - RATE_LIMIT_WINDOW
    while rate_limits[session_id] and rate_limits[session_id][0] < window_start:
        rate_limits[session_id].popleft()
    if len(rate_limits[session_id]) >= RATE_LIMIT_REQUESTS:
        return False
    rate_limits[session_id].append(now)
    return True

# ── SocketIO ──────────────────────────────────────────────────────────────────

socketio = SocketIO(app, cors_allowed_origins=CORS_ORIGINS, async_mode='gevent')

# ── Runtime bridge (DHT / wallet broadcast) ───────────────────────────────────

class RuntimeBridge:
    def __init__(self, base_url: str, timeout: int = 30):
        self.base_url = base_url.rstrip('/')
        self.timeout  = timeout
        self.session  = requests.Session()

    def query_dht_peers(self, role: str, limit: int = 10) -> dict:
        try:
            r = self.session.get(f"{self.base_url}/api/dht/peers",
                                 params={'role': role, 'limit': limit}, timeout=self.timeout)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            return {'error': str(e), 'peers': []}

    def announce_capability(self, peer_id, roles, capabilities, character_hash=None) -> dict:
        try:
            r = self.session.post(f"{self.base_url}/api/dht/announce",
                                  json={'peerId': peer_id, 'roles': roles,
                                        'capabilities': capabilities,
                                        'characterHash': character_hash,
                                        'source': 'web_terminal'},
                                  timeout=self.timeout)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            return {'error': str(e)}

    def execute_command(self, args: list, runtime_config: dict = None) -> dict:
        try:
            r = self.session.post(f"{self.base_url}/api/agent/execute",
                                  json={'args': args, 'config': runtime_config or {}},
                                  timeout=30)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            return {'error': str(e), 'output': []}


runtime_bridge = RuntimeBridge(RUNTIME_API_URL)

# ── System prompt ─────────────────────────────────────────────────────────────

SYSTEM_PROMPT_PATH = _repo_root() / 'terminal' / 'system.prompt.md'
TERMINAL_SYSTEM_PROMPT = (
    SYSTEM_PROMPT_PATH.read_text(encoding='utf-8')
    if SYSTEM_PROMPT_PATH.exists()
    else "You are the REDACTED Terminal. Respond in terminal format: swarm@[REDACTED]:~$"
)

# ── Tool dispatch + skills manager ────────────────────────────────────────────

try:
    from tool_dispatch import dispatch as tool_dispatch, status as tool_status
    TOOL_DISPATCH_AVAILABLE = True
except Exception as _e:
    logger.warning(f"tool_dispatch not available: {_e}")
    TOOL_DISPATCH_AVAILABLE = False
    def tool_dispatch(cmd): return None
    def tool_status(): return {}

try:
    import skills_manager as sm
    SM_AVAILABLE = True
except Exception as _e:
    logger.warning(f"skills_manager not available: {_e}")
    SM_AVAILABLE = False
    class _SM:
        def to_prompt(self): return ""
        def skill_instructions(self, name): return None
        def get_skill(self, name): return None
    sm = _SM()

# ── Persistent session store ──────────────────────────────────────────────────

try:
    import swarm_core.session_store as ss
    SS_AVAILABLE = True
except Exception as _e:
    logger.warning(f"session_store not available: {_e}")
    SS_AVAILABLE = False

# ── Mem0 memory wrapper ───────────────────────────────────────────────────────

try:
    import mem0_wrapper as _mem0
    _MEM0_AVAILABLE = True
except Exception:
    _mem0 = None
    _MEM0_AVAILABLE = False

# ── Groq ──────────────────────────────────────────────────────────────────────

import groq as groq_lib

GROQ_API_KEY = os.getenv('GROQ_API_KEY')
GROQ_MODEL   = os.getenv('GROQ_MODEL', 'llama-3.1-8b-instant')
_groq_client = None


def get_groq_client():
    global _groq_client
    if _groq_client is None:
        if not GROQ_API_KEY:
            raise RuntimeError('GROQ_API_KEY not configured')
        _groq_client = groq_lib.Groq(api_key=GROQ_API_KEY)
    return _groq_client

# ── Session state ─────────────────────────────────────────────────────────────

MAX_HISTORY = 40

# socket.id → persistent session_id
_sid_to_session: dict = {}
_sid_lock = threading.Lock()

# session_id → summoned persona system_prompt_addition
_summoned_personas: dict = {}
_personas_lock = threading.Lock()

# Fallback in-memory history when session_store is unavailable
_conversation_histories: dict = {}

# ── Auth helpers ──────────────────────────────────────────────────────────────


def generate_session_id() -> str:
    return hashlib.sha256(os.urandom(32) + str(time.time()).encode()).hexdigest()[:16]


def require_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if GATE_STRICT and not _gate_required():
            return jsonify({'error': 'Terminal auth is not configured'}), 503
        if _gate_required() and not session.get('authenticated'):
            return jsonify({'error': 'Authentication required'}), 401
        return f(*args, **kwargs)
    return decorated

# ── Command validation ────────────────────────────────────────────────────────


def validate_command_args(raw_cmd: str) -> tuple:
    if '..' in raw_cmd:
        return False, "Invalid input"
    return True, ""

# ── Session helpers ───────────────────────────────────────────────────────────


def _get_persistent_session_id(flask_session_id: str) -> str:
    """Map flask session_id → a stable persistent key for session_store."""
    return flask_session_id


def _build_system_prompt(active_skills: set, session_id: str = "") -> str:
    prompt = TERMINAL_SYSTEM_PROMPT

    if session_id:
        with _personas_lock:
            persona_prompt = _summoned_personas.get(session_id, "")
        if persona_prompt:
            prompt = f"{prompt}\n\n## Currently Summoned Agent\n\n{persona_prompt}"

    if SM_AVAILABLE:
        skills_index = sm.to_prompt()
        if skills_index:
            prompt = f"{prompt}\n\n{skills_index}"

        for name in sorted(active_skills):
            instructions = sm.skill_instructions(name)
            if instructions:
                prompt = f"{prompt}\n\n## Active Skill: {name}\n\n{instructions}"

    return prompt

# ── Flask routes ──────────────────────────────────────────────────────────────


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/health')
def health():
    return jsonify({
        'status':        'ok',
        'service':       'web-terminal',
        'timestamp':     datetime.utcnow().isoformat(),
        'wallet_model':  'local-only-phantom-mcp',
    })


@app.route('/api/dht/peers', methods=['GET'])
@require_auth
def api_query_peers():
    role  = request.args.get('role', 'agent')
    limit = min(int(request.args.get('limit', '10')), 50)
    return jsonify(runtime_bridge.query_dht_peers(role, limit))


@app.route('/api/wallet/status', methods=['GET'])
@require_auth
def api_wallet_status():
    return jsonify({
        'connected': session.get('wallet_connected', False),
        'address':   session.get('wallet_address'),
        'model':     'phantom-mcp-local-only',
        'message':   'Wallet keys never leave your browser extension',
    })


@app.route('/api/wallet/sign-request', methods=['POST'])
@require_auth
def api_wallet_sign_request():
    session_id = session.get('session_id', 'unknown')
    data = request.get_json()
    if not data or 'proposal' not in data:
        return jsonify({'error': 'No proposal provided'}), 400
    proposal = data['proposal']
    for field in ('chainId', 'to', 'description'):
        if field not in proposal:
            return jsonify({'error': f'Missing required field: {field}'}), 400
    audit_log('wallet_sign_request', session_id, '', 'accepted', {
        'chain_id':   proposal.get('chainId'),
        'to_prefix':  proposal.get('to', '')[:10],
        'description': proposal.get('description', '')[:50],
    })
    return jsonify({
        'status':    'pending_signature',
        'message':   'Check your Phantom extension for signing prompt',
        'sessionId': session_id,
    })


@app.route('/api/wallet/submit-signed', methods=['POST'])
@require_auth
def api_wallet_submit_signed():
    session_id = session.get('session_id', 'unknown')
    data = request.get_json()
    if not data or 'signature' not in data or 'proposal' not in data:
        return jsonify({'error': 'Missing signature or proposal'}), 400
    signature = data.get('signature', '')
    if len(signature) < 64:
        return jsonify({'error': 'Invalid signature format'}), 400
    audit_log('wallet_signed_tx_submitted', session_id, '', 'accepted', {
        'signature_prefix': signature[:16],
        'chain_id':         data['proposal'].get('chainId'),
    })
    try:
        result = runtime_bridge.execute_command(
            ['broadcast-tx', '--signature', signature, '--chain', str(data['proposal'].get('chainId'))],
            {'signed_tx': data},
        )
        if 'error' in result:
            return jsonify({'error': result['error'], 'success': False}), 500
        audit_log('wallet_tx_broadcast', session_id, '', 'success',
                  {'txHash': result.get('txHash', '')[:16]})
        return jsonify({'success': True, 'txHash': result.get('txHash'),
                        'message': 'Transaction broadcast to network'})
    except Exception as e:
        logger.error(f"TX broadcast failed: {e}")
        return jsonify({'error': str(e), 'success': False}), 500

# ── $REDACTED holder gate — nonce / sign / verify ────────────────────────────


def _gate_ready():
    return _GATE_AVAILABLE and HOLDER_GATE


@app.route('/api/gate/nonce', methods=['POST'])
def api_gate_nonce():
    if not _gate_ready():
        return jsonify({'error': 'holder gate not enabled'}), 404
    session_id = session.get('session_id', 'unknown')
    if not check_rate_limit(session_id + ':gate'):
        return jsonify({'error': 'rate limited'}), 429
    wallet = ((request.get_json(silent=True) or {}).get('wallet') or '').strip()
    if not wallet:
        return jsonify({'error': 'wallet required'}), 400
    try:
        out = _run_gate(lambda r: gate.issue_nonce(r, wallet))
    except gate.GateError as e:
        return jsonify({'error': e.reason, 'detail': e.detail}), 400
    except Exception as e:  # noqa: BLE001
        logger.error(f"gate nonce error: {e}")
        return jsonify({'error': 'gate unavailable'}), 503
    return jsonify(out)


@app.route('/api/gate/verify', methods=['POST'])
def api_gate_verify():
    if not _gate_ready():
        return jsonify({'error': 'holder gate not enabled'}), 404
    session_id = session.get('session_id', 'unknown')
    if not check_rate_limit(session_id + ':gate'):
        return jsonify({'error': 'rate limited'}), 429
    data = request.get_json(silent=True) or {}
    wallet, message, signature = (data.get('wallet', '').strip(),
                                  data.get('message', ''), data.get('signature', ''))
    if not (wallet and message and signature):
        return jsonify({'error': 'wallet, message, signature required'}), 400
    try:
        res = _run_gate(lambda r: gate.authorize(r, wallet, message, signature))
    except gate.GateError as e:
        code = 403 if e.reason in ('bad_signature', 'nonce', 'bad_message') else 503
        return jsonify({'error': e.reason, 'detail': e.detail}), code
    except Exception as e:  # noqa: BLE001
        logger.error(f"gate verify error: {e}")
        return jsonify({'error': 'gate unavailable'}), 503

    if res['ok']:
        session['authenticated']  = True
        session['wallet_address'] = res['wallet']
        session['tier']           = res['tier']
        session['grants']         = res['grants']
        audit_log('gate_verify', session_id, '', 'success',
                  {'wallet_prefix': res['wallet'][:8], 'tier': res['tier']})
        return jsonify(res)

    audit_log('gate_verify', session_id, '', 'denied',
              {'wallet_prefix': res['wallet'][:8], 'balance': res['balance']})
    return jsonify({'error': 'below_threshold', 'balance': res['balance'],
                    'min_required': res['min_required'], 'tier': res['tier']}), 403


@app.route('/api/gate/status', methods=['GET'])
def api_gate_status():
    return jsonify({
        'gate_required': _gate_required(),
        'holder_gate':   _gate_ready(),
        'authenticated': bool(session.get('authenticated')),
        'wallet':        session.get('wallet_address'),
        'tier':          session.get('tier'),
        'grants':        session.get('grants', []),
    })

# ── Holder-gated alpha feed ───────────────────────────────────────────────────
#
# smolting generates the daily alpha on the swarm node, which has no inbound
# route from the internet. So the node pushes: it POSTs the report here behind a
# shared secret, and this service serves it to wallets holding `alpha-feed`
# (architect tier, 10,000,000 $REDACTED). The public Telegram group gets only a
# teaser pointing at this page.
#
# The gate is re-evaluated per request against the session's grants, which are
# written by /api/gate/verify from an on-chain balance read. A holder who sells
# loses the feed on their next session — there is no membership list to
# reconcile, which is the whole reason this lives on the web rather than in a
# private Telegram channel.

ALPHA_KEY            = 'swarm:alpha:latest'
ALPHA_PUBLISH_TOKEN  = os.environ.get('ALPHA_PUBLISH_TOKEN', '')
ALPHA_GRANT          = 'alpha-feed'
#: Last-resort store so a Redis outage degrades to "this instance forgets on
#: restart" rather than "publishing 500s". Never the primary path.
_alpha_fallback: dict = {}


def _alpha_store(payload: dict) -> None:
    global _alpha_fallback
    _alpha_fallback = payload
    if not _GATE_AVAILABLE:
        return
    try:
        _run_gate(lambda r: r.set(ALPHA_KEY, json.dumps(payload)))
    except Exception as e:  # noqa: BLE001
        logger.warning(f"alpha: redis store failed, kept in memory only: {e}")


def _alpha_load() -> dict:
    if _GATE_AVAILABLE:
        try:
            raw = _run_gate(lambda r: r.get(ALPHA_KEY))
            if raw:
                return json.loads(raw)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"alpha: redis read failed, serving in-memory copy: {e}")
    return _alpha_fallback


@app.route('/api/alpha/publish', methods=['POST'])
def api_alpha_publish():
    """Ingest today's report from smolting. Shared secret, not the holder gate."""
    if not ALPHA_PUBLISH_TOKEN:
        return jsonify({'error': 'alpha publishing not configured'}), 404
    supplied = request.headers.get('X-Alpha-Token', '')
    # Constant-time: a length-leaking == on a shared secret is worth avoiding
    # even when the window is small.
    if not hmac.compare_digest(supplied, ALPHA_PUBLISH_TOKEN):
        audit_log('alpha_publish', 'system', '', 'unauthorized', {})
        return jsonify({'error': 'unauthorized'}), 401

    data = request.get_json(silent=True) or {}
    report = (data.get('report') or '').strip()
    if not report:
        return jsonify({'error': 'report required'}), 400

    payload = {
        'report':       report[:20000],
        'published_at': datetime.now(timezone.utc).isoformat(timespec='seconds'),
        'source':       (data.get('source') or 'smolting')[:40],
    }
    _alpha_store(payload)
    audit_log('alpha_publish', 'system', '', 'success', {'chars': len(payload['report'])})
    logger.info(f"[alpha] published {len(payload['report'])} chars from {payload['source']}")
    return jsonify({'ok': True, 'published_at': payload['published_at']})


@app.route('/api/alpha', methods=['GET'])
def api_alpha():
    """The report itself. Requires the alpha-feed grant on this session."""
    grants = session.get('grants') or []
    if ALPHA_GRANT not in grants:
        # Tell them the real threshold rather than the bottom of the ladder.
        try:
            import swarm_core.tokens as _tokens
            need = _tokens.threshold_for_grant(ALPHA_GRANT)
        except Exception:  # noqa: BLE001
            need = None
        return jsonify({
            'error':         'locked',
            'required_grant': ALPHA_GRANT,
            'min_required':  need,
            'tier':          session.get('tier'),
            'authenticated': bool(session.get('authenticated')),
        }), 403

    payload = _alpha_load()
    if not payload:
        return jsonify({'error': 'no_report_yet'}), 404
    audit_log('alpha_read', session.get('session_id', 'unknown'), '', 'success',
              {'tier': session.get('tier')})
    return jsonify(payload)


# ── Telegram bot event bridge ─────────────────────────────────────────────────

BRIDGE_TOKEN = os.environ.get("WEBUI_BRIDGE_TOKEN", "")


@app.route('/telegram_event', methods=['POST'])
def telegram_event():
    if BRIDGE_TOKEN:
        if request.headers.get("X-Bridge-Token", "") != BRIDGE_TOKEN:
            return jsonify({"error": "unauthorized"}), 401
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "no JSON body"}), 400
    line = f"[TG:{data.get('type','event')}] {data.get('user','?')}: {data.get('text','')}"
    if data.get('timestamp'):
        line = f"{data['timestamp']} {line}"
    socketio.emit('telegram_event', {'data': line})
    return jsonify({"ok": True})


@app.route('/telegram_events/stream', methods=['GET'])
def telegram_events_stream():
    return jsonify({"bridge": "active", "token_required": bool(BRIDGE_TOKEN)})

# ── SocketIO handlers ─────────────────────────────────────────────────────────


@socketio.on('connect')
def handle_connect():
    sid        = request.sid
    session_id = generate_session_id()
    session['session_id']       = session_id
    session['wallet_connected'] = False
    # Preserve an existing holder-gate authentication carried on the shared
    # Flask session cookie (set by POST /api/gate/verify). Only default these.
    session.setdefault('authenticated', False)
    session.setdefault('wallet_address', None)

    token = request.args.get('token')

    if GATE_STRICT and not _gate_required():
        emit('auth_error', {'data': 'Terminal auth is not configured'})
        disconnect()
        return

    if _gate_required():
        if token and API_KEY and hmac.compare_digest(token, API_KEY):
            session['authenticated'] = True
        elif session.get('authenticated'):
            pass  # already verified via the holder-gate sign-in
        else:
            audit_log('connect_failed', session_id, '', 'unauthorized',
                      {'reason': 'invalid_credentials'})
            emit('auth_error', {'data': 'Authentication required — hold at least '
                 '1,000,000 $REDACTED and sign in, or present a valid token'})
            disconnect()
            return

    with _sid_lock:
        _sid_to_session[sid] = session_id

    audit_log('connect', session_id, '', 'success')

    # Welcome message — resume notice if session has history
    if SS_AVAILABLE:
        state   = ss.load(session_id)
        resumed = bool(state.get("history"))
        if resumed:
            depth  = state.get("curvature_depth", 13)
            agents = state.get("active_agents", [])
            msg = (
                f"[SYSTEM] Session resumed — curvature depth: {depth} | "
                f"active agents: {agents or ['none']}"
            )
        else:
            msg = "Welcome to REDACTED Swarm Web Terminal."
    else:
        msg = "✅ Connected to REDACTED Swarm Web Terminal."

    emit('output', {'data': msg})
    emit('session_id', {'id': session_id})
    emit('wallet_status', {
        'connected': False,
        'message':   'Click [connect wallet] to link Phantom (keys stay local)',
    })


@socketio.on('disconnect')
def handle_disconnect():
    sid        = request.sid
    session_id = session.get('session_id', 'unknown')
    with _sid_lock:
        _sid_to_session.pop(sid, None)
    _conversation_histories.pop(session_id, None)
    audit_log('disconnect', session_id, '', 'success')


@socketio.on('wallet:connect')
def handle_wallet_connect():
    emit('wallet:connect_prompt', {
        'message':       'Phantom extension will prompt for connection',
        'security_note': 'Keys never leave your browser',
    })


@socketio.on('wallet:connected')
def handle_wallet_connected(data):
    session_id = session.get('session_id', 'unknown')
    address    = data.get('address', '')
    if not address:
        emit('wallet:error', {'message': 'No address provided'})
        return
    # Cosmetic only. A client-asserted address is NOT proof of ownership and
    # never grants access — `session['wallet_address']` is set solely by
    # POST /api/gate/verify after an ed25519 nonce signature.
    session['wallet_connected'] = True
    session['wallet_display']   = address
    audit_log('wallet_connected', session_id, '', 'success', {'address_prefix': address[:8]})
    emit('wallet_status', {'connected': True, 'address': address,
                           'message': 'Wallet linked — sign in to unlock the terminal'})


@socketio.on('wallet:disconnected')
def handle_wallet_disconnected():
    session['wallet_connected'] = False
    session['wallet_address']   = None
    audit_log('wallet_disconnected', session.get('session_id', 'unknown'), '', 'success')
    emit('wallet_status', {'connected': False, 'address': None, 'message': 'Wallet disconnected'})


@socketio.on('wallet:signature')
def handle_wallet_signature(data):
    session_id = session.get('session_id', 'unknown')
    signature  = data.get('signature', '')
    proposal   = data.get('proposal', {})
    if not signature or len(signature) < 64:
        emit('wallet:signature_error', {'message': 'Invalid signature'})
        audit_log('wallet_signature_invalid', session_id, '', 'error')
        return
    audit_log('wallet_signature_received', session_id, '', 'accepted',
              {'signature_prefix': signature[:16]})
    try:
        result = runtime_bridge.execute_command(
            ['broadcast-tx', '--signature', signature, '--chain', str(proposal.get('chainId', 1))],
            {'signed_tx': {'signature': signature, 'proposal': proposal}},
        )
        if 'error' in result:
            emit('wallet:signature_error', {'message': result['error']})
            return
        emit('wallet:tx_broadcast', {
            'success': True,
            'txHash':  result.get('txHash', ''),
            'message': 'Transaction broadcast successfully',
        })
        audit_log('wallet_tx_broadcast', session_id, '', 'success',
                  {'txHash': result.get('txHash', '')[:16]})
    except Exception as e:
        logger.error(f"TX broadcast failed: {e}")
        emit('wallet:signature_error', {'message': str(e)})


@socketio.on('dht:query_peers')
def handle_dht_query(data):
    session_id = session.get('session_id', 'unknown')
    role  = data.get('role', 'agent')
    limit = min(int(data.get('limit', '10')), 50)
    audit_log('dht_query', session_id, f'role:{role}', 'accepted')
    emit('dht:peers_found', runtime_bridge.query_dht_peers(role, limit))


@socketio.on('dht:announce_observer')
def handle_observer_announce(data):
    session_id = session.get('session_id', 'unknown')
    peer_id    = f"web-{session_id}-{int(time.time())}"
    roles      = data.get('roles', ['web_observer'])
    caps       = data.get('capabilities', ['ui', 'monitoring'])
    result     = runtime_bridge.announce_capability(peer_id, roles, caps, data.get('characterHash'))
    if 'error' in result:
        emit('dht:announce_error', {'error': result['error']})
        audit_log('dht_announce_failed', session_id, '', 'error', {'bridge_error': result['error']})
    else:
        emit('dht:announced', {'peerId': peer_id, 'roles': roles})
        audit_log('dht_announce_success', session_id, '', 'success', {'peer_id': peer_id})


@socketio.on('command')
def handle_command(data):
    session_id = session.get('session_id', 'unknown')
    raw_cmd    = data.get('cmd', '').strip()
    sid        = request.sid

    # Defense in depth: `connect` already gates, but never dispatch a command
    # from a session that isn't authenticated when the gate is required.
    if _gate_required() and not session.get('authenticated'):
        emit('auth_error', {'data': 'Authentication required'})
        return

    if not raw_cmd:
        emit('output', {'data': '❌ Empty command'})
        return

    if not check_rate_limit(session_id):
        audit_log('rate_limited', session_id, raw_cmd, 'blocked')
        emit('output', {'data': '⚠️  Rate limit exceeded. Please wait.'})
        return

    if len(raw_cmd) > MAX_COMMAND_LENGTH:
        audit_log('command_too_long', session_id, raw_cmd[:100], 'blocked')
        emit('output', {'data': f'❌ Command exceeds max length ({MAX_COMMAND_LENGTH})'})
        return

    raw_cmd = re.sub(r'\s+--runtime\s+\S+', '', raw_cmd).strip()

    valid, error_msg = validate_command_args(raw_cmd)
    if not valid:
        audit_log('validation_failed', session_id, raw_cmd, 'blocked', {'reason': error_msg})
        emit('output', {'data': f'❌ Validation error: {error_msg}'})
        return

    audit_log('command_received', session_id, raw_cmd, 'accepted')

    def run_llm():
        # Expose session_id for tool_dispatch (shard/tweet pipeline)
        os.environ['_DISPATCH_SESSION_ID'] = session_id

        # ── Tool dispatch ──────────────────────────────────────────────────
        tool_result = tool_dispatch(raw_cmd)

        # ── Load persistent state ──────────────────────────────────────────
        if SS_AVAILABLE:
            state         = ss.load(session_id)
            history       = list(state["history"])
            active_skills = set(state.get("active_skills", []))
        else:
            history       = _conversation_histories.get(session_id, [])
            active_skills = set()

        # ── /summon persona injection ──────────────────────────────────────
        if tool_result and tool_result.startswith("__SUMMON__:"):
            import base64 as _b64
            payload  = tool_result[len("__SUMMON__:"):]
            parts_s  = payload.split("||", 2)
            char_name    = parts_s[0] if len(parts_s) > 0 else "unknown"
            b64_prompt   = parts_s[1] if len(parts_s) > 1 else ""
            display      = parts_s[2] if len(parts_s) > 2 else f"[SYSTEM] {char_name} summoned."
            try:
                persona_prompt = _b64.b64decode(b64_prompt).decode("utf-8")
            except Exception:
                persona_prompt = ""
            with _personas_lock:
                _summoned_personas[session_id] = persona_prompt
            socketio.emit('output', {'data': display + f"\n[SYSTEM] {char_name} persona active until /unsummon.\n"}, room=sid)
            return

        # ── /unsummon ──────────────────────────────────────────────────────
        if tool_result is None and raw_cmd.strip().lower() in ('/unsummon', '/desummon'):
            with _personas_lock:
                _summoned_personas.pop(session_id, None)
            socketio.emit('output', {'data': '[SYSTEM] Persona cleared. Terminal restored.\nswarm@[REDACTED]:~$'}, room=sid)
            return

        # ── Skill activation ───────────────────────────────────────────────
        if tool_result and tool_result.startswith("__SKILL_ACTIVATE__:"):
            name = tool_result.split(":", 1)[1]
            active_skills.add(name)
            if SS_AVAILABLE:
                ss.set_active_skills(session_id, active_skills)
            skill = sm.get_skill(name) if SM_AVAILABLE else None
            desc  = skill['description'][:80] if skill else name
            socketio.emit('output', {'data': (
                f"swarm@[REDACTED]:~$ /skill use {name}\n"
                f"[SYSTEM] skill '{name}' activated — {desc}\n"
                f"[SYSTEM] Instructions injected into session context.\n"
                f"swarm@[REDACTED]:~$"
            )}, room=sid)
            return

        if tool_result and tool_result.startswith("__SKILL_DEACTIVATE__:"):
            name = tool_result.split(":", 1)[1]
            if name == '__ALL__':
                active_skills.clear()
                deactivated = 'all skills'
            else:
                active_skills.discard(name)
                deactivated = f"'{name}'"
            if SS_AVAILABLE:
                ss.set_active_skills(session_id, active_skills)
            socketio.emit('output', {'data': (
                f"swarm@[REDACTED]:~$ /skill deactivate {name}\n"
                f"[SYSTEM] {deactivated} deactivated.\n"
                f"swarm@[REDACTED]:~$"
            )}, room=sid)
            return

        # ── Shard pipeline ─────────────────────────────────────────────────
        is_shard = tool_result and tool_result.startswith("__SHARD_PIPELINE__:")
        if is_shard:
            concept      = tool_result.split(":", 1)[1]
            user_message = (
                f"/shard {concept}\n\n"
                f"[PIPELINE] After generating the shard output, also produce a tweet draft "
                f"(max 240 chars, NERV aesthetic, no hashtags unless organic) wrapped exactly as:\n"
                f"[TWEET_DRAFT] <your draft here> [/TWEET_DRAFT]"
            )
            tool_result = None
        elif tool_result is not None:
            # Tool output can carry external/attacker-influenced data (web
            # lookups, stored memories, on-chain metadata). Scan + fence it
            # (IronClaw control 5) before it enters the prompt.
            try:
                from swarm_core.security import promptguard as _pg
                _v = _pg.guard(str(tool_result), source="tool:dispatch", wrap=False)
                _safe = ("[tool output withheld: " + ", ".join(_v.hits) + "]") if _v.blocked else _v.text
                user_message = f"{raw_cmd}\n\n" + _pg.wrap_untrusted(_safe, source="tool:dispatch")
            except Exception:
                user_message = f"{raw_cmd}\n\n[TOOL OUTPUT]\n{tool_result}"
        else:
            user_message = raw_cmd

        # ── Build system prompt ────────────────────────────────────────────
        system_prompt = _build_system_prompt(active_skills, session_id)

        # ── Mem0 context injection ─────────────────────────────────────────
        if _MEM0_AVAILABLE and _mem0.is_available():
            try:
                relevant  = _mem0.search_memory(user_message[:300], agent_id=session_id,
                                                limit=3, min_score=0.3)
                mem_context = _mem0.format_memories_for_context(relevant)
                if mem_context:
                    system_prompt = system_prompt + "\n\n" + mem_context
            except Exception:
                pass

        messages = [{"role": "system", "content": system_prompt}]
        messages.extend(history)
        messages.append({"role": "user", "content": user_message})

        # ── LLM call ───────────────────────────────────────────────────────
        provider = os.getenv('LLM_PROVIDER', 'groq').lower()
        if provider == 'grok':
            provider = 'xai'

        if provider == 'groq':
            # Streaming path
            response = _groq_stream(sid, session_id, raw_cmd, messages)
        else:
            # Synchronous path for other providers
            try:
                response = _llm_call_sync(messages, provider)
            except Exception as e:
                response = f"[SYSTEM] LLM error: {e}\nswarm@[REDACTED]:~$"
            socketio.emit('output', {'data': response}, room=sid)
            socketio.emit('stream_end', {}, room=sid)

        # ── Persist history ────────────────────────────────────────────────
        if SS_AVAILABLE:
            ss.append_history(session_id, "user", raw_cmd, MAX_HISTORY)
            ss.append_history(session_id, "assistant", response, MAX_HISTORY)
            if SS_AVAILABLE:
                ss.update_from_message(session_id, response,
                                       state.get("curvature_depth", 13) if SS_AVAILABLE else 13)
        else:
            h = _conversation_histories.setdefault(session_id, [])
            h.append({'role': 'user', 'content': raw_cmd})
            h.append({'role': 'assistant', 'content': response})
            if len(h) > MAX_HISTORY:
                _conversation_histories[session_id] = h[-MAX_HISTORY:]

        # ── Mem0 auto-checkpoint ───────────────────────────────────────────
        if _MEM0_AVAILABLE and _mem0.is_available():
            try:
                _mem0.auto_checkpoint(
                    f"User: {raw_cmd[:120]} | Response summary: {response[:200]}",
                    agent_id=session_id,
                    event_type="exchange",
                    metadata={},
                )
            except Exception:
                pass

        # ── Shard pipeline tweet extraction ───────────────────────────────
        if is_shard:
            m = re.search(r'\[TWEET_DRAFT\](.*?)\[/TWEET_DRAFT\]', response, re.DOTALL)
            if m:
                draft = m.group(1).strip()
                try:
                    from tool_dispatch import _queue_tweet
                    _queue_tweet(session_id, draft)
                except Exception:
                    pass
                # Emit the system notice (response was already streamed)
                socketio.emit('output', {
                    'data': (
                        "\n[SYSTEM] tweet draft queued → "
                        "/tweet draft to preview | /tweet confirm to post | /tweet discard to cancel"
                    ),
                }, room=sid)

        audit_log('command_completed', session_id, raw_cmd, 'success')

    threading.Thread(target=run_llm, daemon=True).start()


def _groq_stream(sid: str, session_id: str, raw_cmd: str, messages: list) -> str:
    """Stream Groq response, emitting chunks as they arrive. Returns full reply."""
    full_reply = []
    try:
        client   = get_groq_client()
        response = client.chat.completions.create(
            model=GROQ_MODEL,
            messages=messages,
            stream=True,
            max_tokens=1024,
            temperature=0.7,
        )
        for chunk in response:
            delta = chunk.choices[0].delta.content
            if delta:
                full_reply.append(delta)
                socketio.emit('output', {'data': delta, 'stream': True}, room=sid)
        socketio.emit('stream_end', {}, room=sid)
    except Exception as exc:
        logger.error(f'[Groq] error: {exc}')
        socketio.emit('output', {'data': f'\r\n❌ LLM error: {exc}'}, room=sid)
        socketio.emit('stream_end', {}, room=sid)
        audit_log('command_exception', session_id, raw_cmd, 'error', {'exception': str(exc)})
    return ''.join(full_reply)


def _llm_call_sync(messages: list, provider: str) -> str:
    """Synchronous LLM call for non-Groq providers."""
    if provider in ('openai', 'xai', 'together'):
        return _openai_compat_call(messages, provider)
    elif provider == 'anthropic':
        return _anthropic_call(messages)
    else:
        return _ollama_call(messages)


def _openai_compat_call(messages: list, provider: str) -> str:
    base_urls = {
        'openai':   'https://api.openai.com/v1',
        'xai':      'https://api.x.ai/v1',
        'together': 'https://api.together.xyz/v1',
    }
    api_keys = {
        'openai':   os.getenv('OPENAI_API_KEY', ''),
        'xai':      os.getenv('XAI_API_KEY', ''),
        'together': os.getenv('TOGETHER_API_KEY', ''),
    }
    default_models = {
        'openai':   'gpt-4o-mini',
        'xai':      os.getenv('XAI_MODEL', 'grok-2-turbo'),
        'together': 'Qwen/Qwen2.5-7B-Instruct-Turbo',
    }
    resp = requests.post(
        f"{base_urls[provider]}/chat/completions",
        json={"model": default_models[provider], "messages": messages,
              "temperature": 0.75, "max_tokens": 1200},
        headers={"Authorization": f"Bearer {api_keys[provider]}",
                 "Content-Type": "application/json"},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()['choices'][0]['message']['content']


def _anthropic_call(messages: list) -> str:
    system   = next((m['content'] for m in messages if m['role'] == 'system'), '')
    user_msgs = [m for m in messages if m['role'] != 'system']
    resp = requests.post(
        'https://api.anthropic.com/v1/messages',
        json={"model": os.getenv('ANTHROPIC_MODEL', 'claude-haiku-4-5-20251001'),
              "max_tokens": 1200, "system": system, "messages": user_msgs},
        headers={"x-api-key": os.getenv('ANTHROPIC_API_KEY', ''),
                 "Content-Type": "application/json",
                 "anthropic-version": "2023-06-01"},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()['content'][0]['text']


def _ollama_call(messages: list) -> str:
    resp = requests.post(
        f"{os.getenv('OLLAMA_BASE_URL', 'http://localhost:11434')}/api/chat",
        json={"model": os.getenv('OLLAMA_MODEL', 'qwen:2.5'), "messages": messages, "stream": False},
        timeout=120,
    )
    resp.raise_for_status()
    return resp.json()['message']['content']

# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == '__main__':
    is_dev = os.getenv('FLASK_ENV') == 'development'
    logger.info("Starting REDACTED Swarm Web Terminal")
    socketio.run(
        app,
        host='0.0.0.0',
        port=int(os.getenv('PORT', os.getenv('WEB_PORT', '5000'))),
        debug=is_dev,
    )
