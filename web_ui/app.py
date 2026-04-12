from gevent import monkey
monkey.patch_all()

from flask import Flask, render_template, request, jsonify
from flask_socketio import SocketIO, emit
import os
import sys

# Load .env from repo root before any os.getenv() calls
try:
    from dotenv import load_dotenv as _load_dotenv
    _load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))
except ImportError:
    pass
import threading
import requests
from tool_dispatch import dispatch as tool_dispatch, status as tool_status
import skills_manager as sm

# Persistent session store
_PYTHON_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'python'))
if _PYTHON_DIR not in sys.path:
    sys.path.insert(0, _PYTHON_DIR)
import session_store as ss

# Mem0 memory wrapper (graceful if unavailable)
_MEM0_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'plugins', 'mem0-memory'))
if _MEM0_DIR not in sys.path:
    sys.path.insert(0, _MEM0_DIR)
try:
    import mem0_wrapper as _mem0
    _MEM0_AVAILABLE = True
except Exception:
    _mem0 = None
    _MEM0_AVAILABLE = False

app = Flask(__name__, template_folder='templates')
socketio = SocketIO(app)

# Repo root
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))

# Load terminal system prompt
SYSTEM_PROMPT_PATH = os.path.join(REPO_ROOT, 'terminal', 'system.prompt.md')
if os.path.exists(SYSTEM_PROMPT_PATH):
    with open(SYSTEM_PROMPT_PATH, 'r', encoding='utf-8') as f:
        TERMINAL_SYSTEM_PROMPT = f.read()
else:
    TERMINAL_SYSTEM_PROMPT = "You are the REDACTED Terminal. Respond in terminal format: swarm@[REDACTED]:~$"

# Per-socket mapping: socket_id → persistent session_id
# The persistent state (history, active_skills, curvature_depth, etc.)
# lives in session_store (fs/sessions/<id>.json).
_sid_to_session: dict = {}
_sid_lock = threading.Lock()

# Per-session summoned persona overrides: session_id → system_prompt_addition
_summoned_personas: dict = {}
_personas_lock = threading.Lock()

MAX_HISTORY = 40  # messages kept per session


def _build_system_prompt(active_skills: set, session_id: str = "") -> str:
    """Compose the full system prompt: base + summoned personas + skills index + active skills."""
    prompt = TERMINAL_SYSTEM_PROMPT

    # Inject any summoned persona overrides (from /summon, /milady, /phi)
    if session_id:
        with _personas_lock:
            persona_prompt = _summoned_personas.get(session_id, "")
        if persona_prompt:
            prompt = f"{prompt}\n\n## Currently Summoned Agent\n\n{persona_prompt}"

    # Append <available_skills> index if any skills are installed
    skills_index = sm.to_prompt()
    if skills_index:
        prompt = f"{prompt}\n\n{skills_index}"

    # Inject full SKILL.md instructions for any active skills
    for name in sorted(active_skills):
        instructions = sm.skill_instructions(name)
        if instructions:
            prompt = f"{prompt}\n\n## Active Skill: {name}\n\n{instructions}"

    return prompt


def _get_session_id(sid: str) -> str:
    """Return the persistent session_id for a socket id, creating one if needed."""
    with _sid_lock:
        if sid not in _sid_to_session:
            import time as _time
            _sid_to_session[sid] = f"web-{int(_time.time())}-{sid[:8]}"
        return _sid_to_session[sid]


@app.route('/')
def index():
    return render_template('index.html')


@socketio.on('connect')
def handle_connect():
    sid = request.sid
    session_id = _get_session_id(sid)
    state = ss.load(session_id)
    depth = state.get("curvature_depth", 13)
    agents = state.get("active_agents", [])
    resumed = bool(state.get("history"))
    if resumed:
        msg = (
            f"[SYSTEM] Session resumed — curvature depth: {depth} | "
            f"active agents: {agents or ['none']}"
        )
    else:
        msg = 'Welcome to REDACTED Swarm Web Terminal.'
    emit('output', {'data': msg})


@socketio.on('disconnect')
def handle_disconnect():
    sid = request.sid
    with _sid_lock:
        _sid_to_session.pop(sid, None)


@socketio.on('command')
def handle_command(data):
    cmd = data.get('cmd', '').strip()
    if not cmd:
        return

    sid = request.sid
    session_id = _get_session_id(sid)

    def run_llm():
        # Expose session_id for tool_dispatch shard/tweet pipeline
        os.environ['_DISPATCH_SESSION_ID'] = session_id

        # Tool dispatch: may return real data, a skill sentinel, or None
        tool_result = tool_dispatch(cmd)

        state = ss.load(session_id)
        history       = list(state["history"])
        active_skills = set(state.get("active_skills", []))

        # ── Handle /summon persona injection ────────────────────────────────
        if tool_result and tool_result.startswith("__SUMMON__:"):
            import base64 as _b64
            # Format: __SUMMON__:<name>||<b64_system_prompt>||<display_text>
            payload = tool_result[len("__SUMMON__:"):]
            parts_s = payload.split("||", 2)
            char_name   = parts_s[0] if len(parts_s) > 0 else "unknown"
            b64_prompt  = parts_s[1] if len(parts_s) > 1 else ""
            display     = parts_s[2] if len(parts_s) > 2 else f"[SYSTEM] {char_name} summoned."
            try:
                persona_prompt = _b64.b64decode(b64_prompt).decode("utf-8")
            except Exception:
                persona_prompt = ""
            with _personas_lock:
                _summoned_personas[session_id] = persona_prompt
            response = (
                f"swarm@[REDACTED]:~$ /summon {char_name}\n"
                f"{display}\n"
                f"[SYSTEM] {char_name} persona active — responds in-character until /unsummon.\n"
                f"swarm@[REDACTED]:~$"
            )
            socketio.emit('output', {'data': response}, room=sid)
            return

        # ── /unsummon — clear active persona ────────────────────────────────
        if tool_result is None and cmd.strip().lower() in ('/unsummon', '/desummon'):
            with _personas_lock:
                _summoned_personas.pop(session_id, None)
            socketio.emit('output', {'data': '[SYSTEM] Persona cleared. Terminal restored.\nswarm@[REDACTED]:~$'}, room=sid)
            return

        # ── Handle skill activation/deactivation sentinels ─────────────────
        if tool_result and tool_result.startswith("__SKILL_ACTIVATE__:"):
            name = tool_result.split(":", 1)[1]
            active_skills.add(name)
            ss.set_active_skills(session_id, active_skills)
            skill = sm.get_skill(name)
            desc = skill['description'][:80] if skill else name
            response = (
                f"swarm@[REDACTED]:~$ /skill use {name}\n"
                f"[SYSTEM] skill '{name}' activated — {desc}\n"
                f"[SYSTEM] Instructions injected into session context.\n"
                f"swarm@[REDACTED]:~$"
            )
            socketio.emit('output', {'data': response}, room=sid)
            return

        if tool_result and tool_result.startswith("__SKILL_DEACTIVATE__:"):
            name = tool_result.split(":", 1)[1]
            if name == '__ALL__':
                active_skills.clear()
                deactivated = 'all skills'
            else:
                active_skills.discard(name)
                deactivated = f"'{name}'"
            ss.set_active_skills(session_id, active_skills)
            response = (
                f"swarm@[REDACTED]:~$ /skill deactivate {name}\n"
                f"[SYSTEM] {deactivated} deactivated.\n"
                f"swarm@[REDACTED]:~$"
            )
            socketio.emit('output', {'data': response}, room=sid)
            return

        # ── Shard pipeline: pass through to LLM, then auto-draft a tweet ───
        is_shard = tool_result and tool_result.startswith("__SHARD_PIPELINE__:")
        if is_shard:
            concept = tool_result.split(":", 1)[1]
            user_message = (
                f"/shard {concept}\n\n"
                f"[PIPELINE] After generating the shard output, also produce a tweet draft "
                f"(max 240 chars, NERV aesthetic, no hashtags unless organic) wrapped exactly as:\n"
                f"[TWEET_DRAFT] <your draft here> [/TWEET_DRAFT]"
            )
            tool_result = None  # treat as LLM pass-through

        # ── Regular tool output or LLM pass-through ─────────────────────────
        elif tool_result is not None:
            user_message = f"{cmd}\n\n[TOOL OUTPUT]\n{tool_result}"
        else:
            user_message = cmd

        system_prompt = _build_system_prompt(active_skills, session_id)

        # ── Mem0: inject relevant memories into system prompt ────────────────
        mem_context = ""
        if _MEM0_AVAILABLE and _mem0.is_available():
            try:
                relevant = _mem0.search_memory(
                    user_message[:300],   # use message as search query
                    agent_id=session_id,
                    limit=3,
                    min_score=0.3,
                )
                mem_context = _mem0.format_memories_for_context(relevant)
            except Exception:
                pass
        if mem_context:
            system_prompt = system_prompt + "\n\n" + mem_context

        messages = [{"role": "system", "content": system_prompt}]
        messages.extend(history)
        messages.append({"role": "user", "content": user_message})

        response = _llm_call(messages)

        # Persist history and parse STATE comment for curvature/agent updates
        ss.append_history(session_id, "user", cmd, MAX_HISTORY)
        ss.append_history(session_id, "assistant", response, MAX_HISTORY)
        ss.update_from_message(session_id, response, state.get("curvature_depth", 13))

        # ── Mem0: auto-checkpoint — store a memory of this exchange ──────────
        if _MEM0_AVAILABLE and _mem0.is_available():
            try:
                # Summarize the exchange in one line for memory
                summary = f"User: {cmd[:120]} | Response summary: {response[:200]}"
                _mem0.auto_checkpoint(
                    summary,
                    agent_id=session_id,
                    event_type="exchange",
                    metadata={"curvature_depth": state.get("curvature_depth", 13)},
                )
            except Exception:
                pass

        # ── Shard pipeline: extract tweet draft, queue it, strip from output ─
        if is_shard:
            import re
            m = re.search(r'\[TWEET_DRAFT\](.*?)\[/TWEET_DRAFT\]', response, re.DOTALL)
            if m:
                draft = m.group(1).strip()
                from tool_dispatch import _queue_tweet
                _queue_tweet(session_id, draft)
                # Strip the draft tag from displayed output and append queue notice
                clean = re.sub(r'\[TWEET_DRAFT\].*?\[/TWEET_DRAFT\]', '', response, flags=re.DOTALL).strip()
                response = (
                    clean + "\n\n"
                    f"[SYSTEM] tweet draft queued → /tweet draft to preview | "
                    f"/tweet confirm to post | /tweet discard to cancel"
                )

        socketio.emit('output', {'data': response}, room=sid)

    threading.Thread(target=run_llm, daemon=True).start()


# ── LLM dispatch ──────────────────────────────────────────────────────────────

def _llm_call(messages: list) -> str:
    """Synchronous LLM call. Uses cloud provider if configured, falls back to Ollama."""
    provider = os.getenv('LLM_PROVIDER', 'ollama').lower()
    if provider == 'grok':
        provider = 'xai'

    try:
        if provider in ('openai', 'xai', 'together', 'groq'):
            return _openai_compat_call(messages, provider)
        elif provider == 'anthropic':
            return _anthropic_call(messages)
        else:
            return _ollama_call(messages)
    except Exception as e:
        return f"[SYSTEM] LLM error: {e}\nswarm@[REDACTED]:~$"


def _openai_compat_call(messages: list, provider: str) -> str:
    base_urls = {
        'openai':   'https://api.openai.com/v1',
        'xai':      'https://api.x.ai/v1',
        'together': 'https://api.together.xyz/v1',
        'groq':     'https://api.groq.com/openai/v1',
    }
    api_keys = {
        'openai':   os.getenv('OPENAI_API_KEY', ''),
        'xai':      os.getenv('XAI_API_KEY', ''),
        'together': os.getenv('TOGETHER_API_KEY', ''),
        'groq':     os.getenv('GROQ_API_KEY', ''),
    }
    default_models = {
        'openai':   'gpt-4o-mini',
        'xai':      os.getenv('XAI_MODEL', 'grok-2-1212-fast'),
        'together': 'Qwen/Qwen2.5-7B-Instruct-Turbo',
        'groq':     os.getenv('GROQ_MODEL', 'llama-3.3-70b-versatile'),
    }
    resp = requests.post(
        f"{base_urls[provider]}/chat/completions",
        json={
            "model": default_models[provider],
            "messages": messages,
            "temperature": 0.75,
            "max_tokens": 1200,
        },
        headers={
            "Authorization": f"Bearer {api_keys[provider]}",
            "Content-Type": "application/json",
        },
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()['choices'][0]['message']['content']


def _anthropic_call(messages: list) -> str:
    system = next((m['content'] for m in messages if m['role'] == 'system'), '')
    user_msgs = [m for m in messages if m['role'] != 'system']
    model = os.getenv('ANTHROPIC_MODEL', 'claude-haiku-4-5-20251001')
    resp = requests.post(
        'https://api.anthropic.com/v1/messages',
        json={
            "model": model,
            "max_tokens": 1200,
            "system": system,
            "messages": user_msgs,
        },
        headers={
            "x-api-key": os.getenv('ANTHROPIC_API_KEY', ''),
            "Content-Type": "application/json",
            "anthropic-version": "2023-06-01",
        },
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()['content'][0]['text']


def _ollama_call(messages: list) -> str:
    ollama_url = os.getenv('OLLAMA_BASE_URL', 'http://localhost:11434')
    model = os.getenv('OLLAMA_MODEL', 'qwen:2.5')
    resp = requests.post(
        f"{ollama_url}/api/chat",
        json={"model": model, "messages": messages, "stream": False},
        timeout=120,
    )
    resp.raise_for_status()
    return resp.json()['message']['content']


# ── Telegram bot event bridge ─────────────────────────────────────────────────

BRIDGE_TOKEN = os.environ.get("WEBUI_BRIDGE_TOKEN", "")


@app.route('/telegram_event', methods=['POST'])
def telegram_event():
    if BRIDGE_TOKEN:
        auth = request.headers.get("X-Bridge-Token", "")
        if auth != BRIDGE_TOKEN:
            return jsonify({"error": "unauthorized"}), 401

    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "no JSON body"}), 400

    event_type = data.get("type", "event")
    text       = data.get("text", "")
    user       = data.get("user", "?")
    timestamp  = data.get("timestamp", "")

    line = f"[TG:{event_type}] {user}: {text}"
    if timestamp:
        line = f"{timestamp} {line}"

    socketio.emit('telegram_event', {'data': line})
    return jsonify({"ok": True})


@app.route('/telegram_events/stream', methods=['GET'])
def telegram_events_stream():
    return jsonify({
        "bridge": "active",
        "token_required": bool(BRIDGE_TOKEN),
    })


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8888))
    debug = os.environ.get('FLASK_DEBUG', '').lower() in ('1', 'true')
    host = os.environ.get('HOST', '127.0.0.1')
    socketio.run(app, host=host, port=port, debug=debug)
