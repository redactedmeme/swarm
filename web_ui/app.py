from flask import Flask, render_template
from flask_socketio import SocketIO, emit
import subprocess
import os
import threading
import sys

app = Flask(__name__, template_folder='templates')
socketio = SocketIO(app)

# Load system prompt
SYSTEM_PROMPT_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'terminal', 'system.prompt.md'))
if os.path.exists(SYSTEM_PROMPT_PATH):
    with open(SYSTEM_PROMPT_PATH, 'r') as f:
        SYSTEM_PROMPT = f.read()
else:
    SYSTEM_PROMPT = "Default REDACTED Swarm prompt."

@app.route('/')
def index():
    return render_template('index.html')

@socketio.on('connect')
def handle_connect():
    emit('output', {'data': 'Welcome to REDACTED Swarm Web Terminal.'})

@socketio.on('command')
def handle_command(data):
    cmd = data.get('cmd', '').strip()
    if not cmd:
        return

    args = cmd.split()
    full_cmd = [sys.executable, os.path.join(os.path.dirname(__file__), '..', 'python', 'run_with_ollama.py')]
    full_cmd.extend(['--prompt', SYSTEM_PROMPT])
    full_cmd.extend(args)

    def run_process():
        try:
            process = subprocess.Popen(full_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, cwd=os.path.dirname(__file__))
            for line in iter(process.stdout.readline, ''):
                emit('output', {'data': line.strip()})
            process.stdout.close()
            stderr = process.stderr.read().strip()
            if stderr:
                emit('output', {'data': f"Error: {stderr}"})
            process.wait()
        except Exception as e:
            emit('output', {'data': f"Error: {str(e)}"})

    threading.Thread(target=run_process).start()

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=5000, debug=True)
