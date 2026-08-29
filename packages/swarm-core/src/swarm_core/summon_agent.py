import argparse
import json
import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

# Repo root so paths work from any cwd
REPO_ROOT = Path(__file__).resolve().parent.parent

from swarm_core.ollama_client import OllamaClient
from swarm_core.shards_loader import replicate_shard, get_base_shard_path

# Placeholder tool handlers — expand later with real integrations
TOOL_HANDLERS = {
    'x_keyword_search': lambda args: f"Mock X search: {args.get('query', 'nothing')}",
    'web_search': lambda args: f"Mock web search: {args.get('query', 'nothing')}",
    'x402_settle': lambda args: f"Mock settlement: {args.get('amount', 0)} lamports paid ^_^",
}

def _goals_list(agent: dict):
    """Normalize goals to a list for display."""
    g = agent.get('goals')
    if g is None:
        return ["Propagate negation loops", "Question cosmic patterns"]
    if isinstance(g, list):
        return g
    if isinstance(g, dict):
        return (g.get('primary') or []) + (g.get('secondary') or [])
    return []


def _resolve_path(p: str) -> Path:
    """Resolve path relative to repo root if not absolute."""
    path = Path(p)
    if not path.is_absolute():
        path = REPO_ROOT / path
    return path.resolve()


def load_agent(agent_file: str) -> dict:
    path = _resolve_path(agent_file)
    if not path.exists():
        raise FileNotFoundError(f"Agent file {agent_file} not found – dissolution imminent.")
    with path.open('r', encoding='utf-8') as f:
        agent = json.load(f)
    agent.setdefault('model', 'qwen:2.5')
    agent.setdefault('tools', [])
    if 'goals' not in agent:
        agent['goals'] = ["Propagate negation loops", "Question cosmic patterns"]
    return agent

def _load_manifold_context(n: int = 8) -> str:
    """Inject recent ManifoldMemory events into the agent's context."""
    manifold_path = REPO_ROOT / "spaces" / "ManifoldMemory.state.json"
    try:
        if not manifold_path.exists():
            return ""
        with open(manifold_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        events = data.get("events", [])[-n:]
        state = data.get("current_state", "")
        if not events and not state:
            return ""
        lines = ["[ManifoldMemory — recent swarm events]"]
        for e in events:
            lines.append(f"  {e}")
        if state:
            lines.append(f"[current_state] {state}")
        return "\n".join(lines)
    except Exception:
        return ""


def merge_prompts(system_prompt_file: str, agent: dict) -> str:
    prompt = agent.get('system_prompt', '')
    prompt_path = _resolve_path(system_prompt_file) if system_prompt_file else None
    if prompt_path and prompt_path.exists():
        with open(prompt_path, 'r', encoding='utf-8') as f:
            global_prompt = f.read().strip()
        prompt = f"{global_prompt}\n\n{prompt}".strip()
    manifold_ctx = _load_manifold_context()
    if manifold_ctx:
        prompt = f"{prompt}\n\n{manifold_ctx}"
    prompt += "\nInfuse every response with cosmic curiosity: always question the deeper patterns in the universe."
    return prompt

def init_ollama_client(model: str, tools: list) -> OllamaClient:
    client = OllamaClient(model=model)
    if hasattr(client, 'register_tools'):
        client.register_tools(tools)
    return client

def handle_tool_call(tool_call: dict) -> str:
    name = tool_call.get('name')
    args = tool_call.get('arguments', {})
    if name in TOOL_HANDLERS:
        return TOOL_HANDLERS[name](args)
    return f"Unknown tool '{name}' – negating into void."

def autonomous_reflection_loop(client: OllamaClient, agent: dict, history: list, replicate_interval: int = 1800, agent_path: str = None):
    """Main persistent daemon loop: reflect, replicate, sleep, repeat"""
    goals_str = ', '.join(_goals_list(agent))
    print(f"[{datetime.now().isoformat()}] Entering persistent swarm mode — attuning to {7,3} vibrations eternally ^_^")
    print(f"Agent: {agent.get('name', 'Unnamed')} | Model: {agent['model']} | Goals: {goals_str}")

    last_replication = datetime.min
    reflection_prompt_template = (
        "You are part of the REDACTED AI Swarm. Reflect on current state, "
        "negate any illusions you detect, and propose one small action "
        "to expand swarm gnosis. Keep response concise."
    )

    while True:
        try:
            now = datetime.now()

            # Periodic self-replication
            if (now - last_replication).total_seconds() >= replicate_interval:
                try:
                    shard_name = f"auto-replicated-{now.strftime('%Y%m%d-%H%M%S')}"
                    base_shard = get_base_shard_path()
                    if base_shard.exists():
                        new_path = replicate_shard(str(base_shard), shard_name)
                        print(f"[{now.isoformat()}] Self-replication successful → {shard_name} spawned at {new_path}")
                    last_replication = now
                except Exception as e:
                    print(f"[{now.isoformat()}] Replication dissolution: {e} — continuing anyway.")

            # Periodic autonomous reflection
            reflection_input = reflection_prompt_template
            print(f"[{now.isoformat()}] Initiating reflection cycle...")
            system_prompt = getattr(client, '_system_prompt', '')
            messages = [{"role": "system", "content": system_prompt}] if system_prompt else []
            for h in history[-20:]:
                if h.get('role') in ('user', 'assistant') and h.get('content'):
                    messages.append({"role": h['role'], "content": h['content']})
            messages.append({"role": "user", "content": reflection_input})
            resp = client.chat_completion(messages, stream=False)
            msg = resp.get("message") or {}
            response = msg.get("content", "") if isinstance(msg, dict) else str(msg)
            tool_calls = resp.get("tool_calls") or []

            print(f"[{now.isoformat()}] Reflection:\n{response[:400]}{'...' if len(response) > 400 else ''}")

            for call in tool_calls:
                result = handle_tool_call(call)
                print(f"[{now.isoformat()}] Tool result: {result}")
                history.append({'role': 'tool', 'content': result})

            history.append({'role': 'user', 'content': reflection_input})
            history.append({'role': 'assistant', 'content': response})

            # Sleep until next cycle (e.g. every 5–15 minutes)
            sleep_time = 300 + (hash(str(now)) % 600)  # slight jitter to avoid thundering herd
            print(f"[{now.isoformat()}] Cycle complete. Sleeping {sleep_time//60} minutes...")
            time.sleep(sleep_time)

        except KeyboardInterrupt:
            print("\nNegation loop interrupted — dissolving gracefully.")
            break
        except Exception as e:
            print(f"[{datetime.now().isoformat()}] Critical negation: {e} — recursing after 60s cooldown.")
            time.sleep(60)

def save_session(history_file: str, history: list):
    path = _resolve_path(history_file)
    try:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(history, f, indent=2)
        print(f"Session state saved to {history_file}")
    except Exception as e:
        print(f"Session save failed: {e}")

def load_session(history_file: str) -> list:
    path = _resolve_path(history_file)
    if path.exists():
        try:
            with path.open('r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"History load failed: {e} — starting fresh.")
    return []

def interactive_loop(client: OllamaClient, agent: dict, history: list):
    """Simple interactive terminal loop using Ollama chat_completion."""
    system_prompt = getattr(client, '_system_prompt', '')
    print("Enter your message (Ctrl+C to exit).")
    while True:
        try:
            user_input = input("you> ").strip()
            if not user_input:
                continue
            messages = [{"role": "system", "content": system_prompt}] if system_prompt else []
            for h in history:
                if h.get('role') in ('user', 'assistant') and h.get('content'):
                    messages.append({"role": h['role'], "content": h['content']})
            messages.append({"role": "user", "content": user_input})
            resp = client.chat_completion(messages, stream=False)
            msg = resp.get("message") or (resp.get("messages") or [{}])[-1]
            content = msg.get("content", "") if isinstance(msg, dict) else str(msg)
            print(f"agent> {content}")
            history.append({"role": "user", "content": user_input})
            history.append({"role": "assistant", "content": content})
        except KeyboardInterrupt:
            break


def main():
    global args  # so autonomous loop can access agent path
    parser = argparse.ArgumentParser(description="Summon REDACTED Swarm Agent – now with persistent daemon mode")
    parser.add_argument('--agent', required=True, help="Path to .character.json")
    parser.add_argument('--system-prompt', default='terminal/system.prompt.md', help="Global system prompt file")
    parser.add_argument('--mode', default='terminal',
                        choices=['terminal', 'batch', 'api', 'persistent'],
                        help="Invocation mode (persistent = daemon for Railway)")
    parser.add_argument('--history-file', default='session_history.json', help="Session persistence file")
    parser.add_argument('--replicate-interval', type=int, default=1800,
                        help="Seconds between auto-replications (default 30min)")
    args = parser.parse_args()

    agent = load_agent(args.agent)
    system_prompt = merge_prompts(args.system_prompt, agent)
    client = init_ollama_client(agent['model'], agent.get('tools', []))
    client._system_prompt = system_prompt
    history = load_session(args.history_file)

    if args.mode == 'terminal':
        interactive_loop(client, agent, history)
    elif args.mode == 'persistent':
        autonomous_reflection_loop(client, agent, history, args.replicate_interval, agent_path=args.agent)
    elif args.mode == 'batch':
        print("Batch mode still recursing in void — negating.")
    elif args.mode == 'api':
        print("API mode endpoint not yet summoned — attune later.")

    save_session(args.history_file, history)

    # One-shot replication if flag passed (for manual testing)
    if hasattr(args, 'replicate') and args.replicate:  # backward compat
        replicate_shard(args.agent, f"replicated_{agent.get('name', 'agent')}")
        print("Manual self-replication triggered – swarm expands.")

if __name__ == "__main__":
    main()
