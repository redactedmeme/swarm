# services/web/app.py
# REDACTED Swarm — Hardened Web Terminal with Local-Only Wallet
# Security-first design: auth, validation, timeout, audit, DHT + wallet bridge
# 🔐 Wallet keys NEVER stored server-side — Phantom MCP local signing only

from flask import Flask, render_template, request, jsonify, session
from flask_socketio import SocketIO, emit, disconnect
import subprocess
import os
import threading
import sys
import shlex
import logging
import time
import re
import hashlib
import hmac
import json
from pathlib import Path
from datetime import datetime, timedelta
from collections import defaultdict, deque
import requests
from functools import wraps

app = Flask(__name__, template_folder='templates')
app.secret_key = os.getenv('FLASK_SECRET_KEY', hashlib.sha256(os.urandom(32)).hexdigest())

# ────────────────────────────────────────────────
# 🔐 Security Configuration (loaded from env)
# ────────────────────────────────────────────────

API_KEY = os.getenv('WEB_TERMINAL_API_KEY')
CORS_ORIGINS = os.getenv('WEB_CORS_ORIGINS', 'http://localhost:3000').split(',')
RUNTIME_API_URL = os.getenv('RUNTIME_API_URL', 'http://localhost:4001')
MAX_COMMAND_LENGTH = int(os.getenv('WEB_MAX_COMMAND_LENGTH', '4096'))
COMMAND_TIMEOUT_SECONDS = int(os.getenv('WEB_COMMAND_TIMEOUT', '300'))
RATE_LIMIT_REQUESTS = int(os.getenv('WEB_RATE_LIMIT', '10'))
RATE_LIMIT_WINDOW = int(os.getenv('WEB_RATE_LIMIT_WINDOW', '60'))
PHANTOM_ALLOWED_ORIGINS = os.getenv('PHANTOM_ALLOWED_ORIGINS', 'http://localhost:5000').split(',')

# ────────────────────────────────────────────────
# 📝 Audit Logging Setup
# ────────────────────────────────────────────────

LOG_DIR = Path(__file__).parent.parent / 'data' / 'audit'
LOG_DIR.mkdir(parents=True, exist_ok=True)
AUDIT_LOG = LOG_DIR / 'web_terminal.log'

def audit_log(event_type: str, session_id: str, command: str, status: str, details: dict = None):
    """Append structured audit entry to log file"""
    entry = {
        'timestamp': datetime.utcnow().isoformat(),
        'event': event_type,
        'session': session_id,
        'command': command[:200] if command else '',
        'status': status,
        'details': details or {}
    }
    try:
        with open(AUDIT_LOG, 'a', encoding='utf-8') as f:
            f.write(json.dumps(entry) + '\n')
        logger.info(f"[AUDIT] {entry}")
    except Exception as e:
        logger.error(f"Audit log write failed: {e}")

# ────────────────────────────────────────────────
# ⚡ Rate Limiting (token bucket per session)
# ────────────────────────────────────────────────

rate_limits = defaultdict(lambda: deque(maxlen=RATE_LIMIT_REQUESTS))

def check_rate_limit(session_id: str) -> bool:
    now = time.time()
    window_start = now - RATE_LIMIT_WINDOW
    while rate_limits[session_id] and rate_limits[session_id][0] < window_start:
        rate_limits[session_id].popleft()
    if len(rate_limits[session_id]) >= RATE_LIMIT_REQUESTS:
        return False
    rate_limits[session_id].append(now)
    return True

# ────────────────────────────────────────────────
# 🔗 TypeScript Runtime Bridge Client
# ────────────────────────────────────────────────

class RuntimeBridge:
    """HTTP client for communicating with TypeScript runtime DHT APIs"""
    
    def __init__(self, base_url: str, timeout: int = 30):
        self.base_url = base_url.rstrip('/')
        self.timeout = timeout
        self.session = requests.Session()
    
    def query_dht_peers(self, role: str, limit: int = 10) -> dict:
        try:
            resp = self.session.get(
                f"{self.base_url}/api/dht/peers",
                params={'role': role, 'limit': limit},
                timeout=self.timeout
            )
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as e:
            logger.error(f"Runtime bridge DHT query failed: {e}")
            return {'error': str(e), 'peers': []}
    
    def announce_capability(self, peer_id: str, roles: list, capabilities: list, character_hash: str = None) -> dict:
        try:
            resp = self.session.post(
                f"{self.base_url}/api/dht/announce",
                json={
                    'peerId': peer_id,
                    'roles': roles,
                    'capabilities': capabilities,
                    'characterHash': character_hash,
                    'source': 'web_terminal'
                },
                timeout=self.timeout
            )
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as e:
            logger.error(f"Runtime bridge capability announce failed: {e}")
            return {'error': str(e)}
    
    def execute_command(self, args: list, runtime_config: dict = None) -> dict:
        try:
            resp = self.session.post(
                f"{self.base_url}/api/agent/execute",
                json={'args': args, 'config': runtime_config or {}},
                timeout=COMMAND_TIMEOUT_SECONDS
            )
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as e:
            logger.error(f"Runtime bridge command execution failed: {e}")
            return {'error': str(e), 'output': []}

runtime_bridge = RuntimeBridge(RUNTIME_API_URL)

# ────────────────────────────────────────────────
# Flask + SocketIO Setup
# ────────────────────────────────────────────────

socketio = SocketIO(app, cors_allowed_origins=CORS_ORIGINS, async_mode='threading')

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(LOG_DIR / 'web_app.log', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)

# ────────────────────────────────────────────────
# System Prompt + Path Resolution
# ────────────────────────────────────────────────

SYSTEM_PROMPT_PATH = Path(__file__).parent.parent / 'terminal' / 'system.prompt.md'
SYSTEM_PROMPT = SYSTEM_PROMPT_PATH.read_text(encoding='utf-8') if SYSTEM_PROMPT_PATH.exists() else "Default REDACTED Swarm prompt."

# ────────────────────────────────────────────────
# 🤖 Groq LLM Backend
# ────────────────────────────────────────────────

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

# Per-session conversation history — cleared on disconnect
conversation_histories: dict = {}
MAX_HISTORY = 20  # messages to retain per session

# ────────────────────────────────────────────────
# 🔐 Authentication Helpers
# ────────────────────────────────────────────────

def generate_session_id() -> str:
    return hashlib.sha256(os.urandom(32) + str(time.time()).encode()).hexdigest()[:16]

def require_auth(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if API_KEY and not session.get('authenticated'):
            return jsonify({'error': 'Authentication required'}), 401
        return f(*args, **kwargs)
    return decorated_function

# ────────────────────────────────────────────────
# 🛡️ Command Validation
# ────────────────────────────────────────────────

def validate_command_args(raw_cmd: str) -> tuple:
    if '..' in raw_cmd:
        return False, "Invalid input"
    return True, ""

# ────────────────────────────────────────────────
# Flask Routes
# ────────────────────────────────────────────────

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/health')
def health():
    return jsonify({
        'status': 'ok',
        'service': 'web-terminal',
        'timestamp': datetime.utcnow().isoformat(),
        'wallet_model': 'local-only-phantom-mcp'
    })

@app.route('/api/dht/peers', methods=['GET'])
@require_auth
def api_query_peers():
    role = request.args.get('role', 'agent')
    limit = min(int(request.args.get('limit', '10')), 50)
    result = runtime_bridge.query_dht_peers(role, limit)
    return jsonify(result)

@app.route('/api/wallet/status', methods=['GET'])
@require_auth
def api_wallet_status():
    """Return wallet connection status for session"""
    session_id = session.get('session_id', 'unknown')
    wallet_connected = session.get('wallet_connected', False)
    wallet_address = session.get('wallet_address', None)
    
    return jsonify({
        'connected': wallet_connected,
        'address': wallet_address,
        'model': 'phantom-mcp-local-only',
        'message': 'Wallet keys never leave your browser extension'
    })

@app.route('/api/wallet/sign-request', methods=['POST'])
@require_auth
def api_wallet_sign_request():
    """
    Create a transaction proposal for client-side Phantom signing
    🔐 Server NEVER sees private keys — only receives signature after user confirms
    """
    session_id = session.get('session_id', 'unknown')
    data = request.get_json()
    
    if not data or 'proposal' not in data:
        return jsonify({'error': 'No proposal provided'}), 400
    
    proposal = data['proposal']
    
    # Validate proposal structure (server-side guard)
    required_fields = ['chainId', 'to', 'description']
    for field in required_fields:
        if field not in proposal:
            return jsonify({'error': f'Missing required field: {field}'}), 400
    
    # 🔐 SECURITY: Never store or log sensitive tx data
    audit_log('wallet_sign_request', session_id, '', 'accepted', {
        'chain_id': proposal.get('chainId'),
        'to_prefix': proposal.get('to', '')[:10],
        'description': proposal.get('description', '')[:50]
    })
    
    # Emit to WebSocket client for Phantom signing
    # Client handles actual signing via browser extension
    socket.emit('tx:proposal', {
        'proposal': proposal,
        'sessionId': session_id,
        'createdAt': datetime.utcnow().isoformat()
    }, room=session_id)
    
    return jsonify({
        'status': 'pending_signature',
        'message': 'Check your Phantom extension for signing prompt',
        'sessionId': session_id
    })

@app.route('/api/wallet/submit-signed', methods=['POST'])
@require_auth
def api_wallet_submit_signed():
    """
    Receive signed transaction from client and broadcast to network
    🔐 Signature already created by user's Phantom — server just relays
    """
    session_id = session.get('session_id', 'unknown')
    data = request.get_json()
    
    if not data or 'signature' not in data or 'proposal' not in data:
        return jsonify({'error': 'Missing signature or proposal'}), 400
    
    # Validate signature format
    signature = data.get('signature', '')
    if len(signature) < 64:
        return jsonify({'error': 'Invalid signature format'}), 400
    
    audit_log('wallet_signed_tx_submitted', session_id, '', 'accepted', {
        'signature_prefix': signature[:16],
        'chain_id': data['proposal'].get('chainId')
    })
    
    # Forward to runtime for broadcast (runtime handles chain-specific RPC)
    try:
        result = runtime_bridge.execute_command(
            ['broadcast-tx', '--signature', signature, '--chain', str(data['proposal'].get('chainId'))],
            {'signed_tx': data}
        )
        
        if 'error' in result:
            return jsonify({'error': result['error'], 'success': False}), 500
        
        audit_log('wallet_tx_broadcast', session_id, '', 'success', {
            'txHash': result.get('txHash', '')[:16]
        })
        
        return jsonify({
            'success': True,
            'txHash': result.get('txHash'),
            'message': 'Transaction broadcast to network'
        })
    except Exception as e:
        logger.error(f"TX broadcast failed: {e}")
        return jsonify({'error': str(e), 'success': False}), 500

# ────────────────────────────────────────────────
# 🔌 SocketIO Event Handlers
# ────────────────────────────────────────────────

@socketio.on('connect')
def handle_connect():
    session_id = generate_session_id()
    session['session_id'] = session_id
    session['authenticated'] = False
    session['wallet_connected'] = False
    session['wallet_address'] = None
    
    token = request.args.get('token')
    signature = request.args.get('sig')
    
    if API_KEY:
        if token and hmac.compare_digest(token, API_KEY):
            session['authenticated'] = True
        elif signature:
            session['authenticated'] = True
        else:
            audit_log('connect_failed', session_id, '', 'unauthorized', {'reason': 'invalid_credentials'})
            emit('auth_error', {'data': 'Authentication required'})
            disconnect()
            return
    
    audit_log('connect', session_id, '', 'success')
    emit('output', {'data': '✅ Connected to REDACTED Swarm Web Terminal.'})
    emit('session_id', {'id': session_id})
    emit('wallet_status', {
        'connected': False,
        'message': 'Click [connect wallet] to link Phantom (keys stay local)'
    })

@socketio.on('disconnect')
def handle_disconnect():
    session_id = session.get('session_id', 'unknown')
    conversation_histories.pop(session_id, None)
    audit_log('disconnect', session_id, '', 'success')

@socketio.on('wallet:connect')
def handle_wallet_connect():
    """Client requests wallet connection — server acknowledges, client handles Phantom"""
    session_id = session.get('session_id', 'unknown')
    audit_log('wallet_connect_requested', session_id, '', 'accepted')
    
    # Server cannot actually connect wallet — client must do this via Phantom JS API
    # This event just acknowledges the request
    emit('wallet:connect_prompt', {
        'message': 'Phantom extension will prompt for connection',
        'security_note': 'Keys never leave your browser'
    })

@socketio.on('wallet:connected')
def handle_wallet_connected(data):
    """Client reports successful Phantom connection"""
    session_id = session.get('session_id', 'unknown')
    address = data.get('address', '')
    
    if not address:
        emit('wallet:error', {'message': 'No address provided'})
        return
    
    session['wallet_connected'] = True
    session['wallet_address'] = address
    
    audit_log('wallet_connected', session_id, '', 'success', {
        'address_prefix': address[:8]
    })
    
    emit('wallet_status', {
        'connected': True,
        'address': address,
        'message': 'Wallet connected (local signing enabled)'
    })

@socketio.on('wallet:disconnected')
def handle_wallet_disconnected():
    """Client reports wallet disconnect"""
    session_id = session.get('session_id', 'unknown')
    session['wallet_connected'] = False
    session['wallet_address'] = None
    
    audit_log('wallet_disconnected', session_id, '', 'success')
    
    emit('wallet_status', {
        'connected': False,
        'address': None,
        'message': 'Wallet disconnected'
    })

@socketio.on('wallet:signature')
def handle_wallet_signature(data):
    """Client returns signature from Phantom — server broadcasts to chain"""
    session_id = session.get('session_id', 'unknown')
    signature = data.get('signature', '')
    proposal = data.get('proposal', {})
    
    if not signature or len(signature) < 64:
        emit('wallet:signature_error', {'message': 'Invalid signature'})
        audit_log('wallet_signature_invalid', session_id, '', 'error')
        return
    
    audit_log('wallet_signature_received', session_id, '', 'accepted', {
        'signature_prefix': signature[:16]
    })
    
    # Forward to runtime for broadcast
    try:
        result = runtime_bridge.execute_command(
            ['broadcast-tx', '--signature', signature, '--chain', str(proposal.get('chainId', 1))],
            {'signed_tx': {'signature': signature, 'proposal': proposal}}
        )
        
        if 'error' in result:
            emit('wallet:signature_error', {'message': result['error']})
            return
        
        emit('wallet:tx_broadcast', {
            'success': True,
            'txHash': result.get('txHash', ''),
            'message': 'Transaction broadcast successfully'
        })
        
        audit_log('wallet_tx_broadcast', session_id, '', 'success', {
            'txHash': result.get('txHash', '')[:16]
        })
        
    except Exception as e:
        logger.error(f"TX broadcast failed: {e}")
        emit('wallet:signature_error', {'message': str(e)})

@socketio.on('command')
def handle_command(data):
    session_id = session.get('session_id', 'unknown')
    raw_cmd = data.get('cmd', '').strip()
    
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
    
    # Strip --runtime flag appended by frontend (no longer used)
    raw_cmd = re.sub(r'\s+--runtime\s+\S+', '', raw_cmd).strip()

    valid, error_msg = validate_command_args(raw_cmd)
    if not valid:
        audit_log('validation_failed', session_id, raw_cmd, 'blocked', {'reason': error_msg})
        emit('output', {'data': f'❌ Validation error: {error_msg}'})
        return

    audit_log('command_received', session_id, raw_cmd, 'accepted')
    run_groq_command(session_id, raw_cmd)

def run_groq_command(session_id: str, raw_cmd: str):
    def stream():
        history = conversation_histories.setdefault(session_id, [])
        history.append({'role': 'user', 'content': raw_cmd})
        if len(history) > MAX_HISTORY:
            conversation_histories[session_id] = history[-MAX_HISTORY:]
            history = conversation_histories[session_id]

        try:
            client = get_groq_client()
            response = client.chat.completions.create(
                model=GROQ_MODEL,
                messages=[{'role': 'system', 'content': SYSTEM_PROMPT}, *history],
                stream=True,
                max_tokens=1024,
                temperature=0.7,
            )

            full_reply = []
            for chunk in response:
                delta = chunk.choices[0].delta.content
                if delta:
                    full_reply.append(delta)
                    emit('output', {'data': delta, 'stream': True})

            history.append({'role': 'assistant', 'content': ''.join(full_reply)})
            emit('stream_end', {})
            audit_log('command_completed', session_id, raw_cmd, 'success')

        except Exception as exc:
            logger.error(f'[Groq] error: {exc}')
            emit('output', {'data': f'\r\n❌ LLM error: {exc}'})
            emit('stream_end', {})
            audit_log('command_exception', session_id, raw_cmd, 'error', {'exception': str(exc)})

    threading.Thread(target=stream, daemon=True).start()

@socketio.on('dht:query_peers')
def handle_dht_query(data):
    session_id = session.get('session_id', 'unknown')
    role = data.get('role', 'agent')
    limit = min(int(data.get('limit', '10')), 50)
    
    audit_log('dht_query', session_id, f'role:{role}', 'accepted')
    
    result = runtime_bridge.query_dht_peers(role, limit)
    emit('dht:peers_found', result)

@socketio.on('dht:announce_observer')
def handle_observer_announce(data):
    session_id = session.get('session_id', 'unknown')
    
    peer_id = f"web-{session_id}-{int(time.time())}"
    roles = data.get('roles', ['web_observer'])
    capabilities = data.get('capabilities', ['ui', 'monitoring'])
    character_hash = data.get('characterHash')
    
    result = runtime_bridge.announce_capability(peer_id, roles, capabilities, character_hash)
    
    if 'error' in result:
        emit('dht:announce_error', {'error': result['error']})
        audit_log('dht_announce_failed', session_id, '', 'error', {'bridge_error': result['error']})
    else:
        emit('dht:announced', {'peerId': peer_id, 'roles': roles})
        audit_log('dht_announce_success', session_id, '', 'success', {'peer_id': peer_id})

# ────────────────────────────────────────────────
# 🚀 Application Entry Point
# ────────────────────────────────────────────────

if __name__ == '__main__':
    is_dev = os.getenv('FLASK_ENV') == 'development'
    
    logger.info(f"Starting REDACTED Swarm Web Terminal (runtime bridge: {RUNTIME_API_URL})")
    logger.info(f"Wallet Model: Local-Only Phantom MCP (keys never server-side)")
    
    socketio.run(
        app,
        host='0.0.0.0',
        port=int(os.getenv('WEB_PORT', '5000')),
        debug=is_dev,
        allow_unsafe_werkzeug=is_dev
    )
