# plugins/mem0-memory/mem0_wrapper.py
#
# Mem0MemoryNode implementation for the REDACTED swarm.
#
# Wraps mem0ai with:
#   - Local-first storage (Qdrant on-disk + fastembed — no external API needed)
#   - Optional Mem0 Cloud backend (set MEM0_API_KEY)
#   - Auto-detects LLM backend from existing swarm env vars
#   - Singleton pattern with lazy initialization
#   - Full API: add / search / update / get_all / inherit / auto_checkpoint
#
# Storage path: <repo_root>/fs/memories/
# History DB  : <repo_root>/fs/memories/mem0_history.db

import os
import json
import time
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_MEMORIES_DIR = _REPO_ROOT / "fs" / "memories"
_MEMORIES_DIR.mkdir(parents=True, exist_ok=True)

# ── Singleton ─────────────────────────────────────────────────────────────────

_mem: Any = None          # mem0 Memory instance
_mem_lock = threading.Lock()
_init_error: Optional[str] = None


def _build_config() -> Dict:
    """
    Build mem0 config, auto-detecting available LLM from env vars.
    Priority: MEM0_API_KEY (cloud) → Anthropic → xAI/OpenAI → Ollama
    """
    # Cloud mode: if MEM0_API_KEY is set, defer entirely to MemoryClient
    if os.getenv("MEM0_API_KEY"):
        return {"cloud": True}

    # Detect LLM backend
    llm_config: Dict = {}
    provider = (os.getenv("LLM_PROVIDER") or "").lower()

    if os.getenv("ANTHROPIC_API_KEY"):
        llm_config = {
            "provider": "anthropic",
            "config": {
                "model": os.getenv("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001"),
                "api_key": os.getenv("ANTHROPIC_API_KEY"),
            },
        }
    elif os.getenv("OPENAI_API_KEY"):
        llm_config = {
            "provider": "openai",
            "config": {
                "model": os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
                "api_key": os.getenv("OPENAI_API_KEY"),
            },
        }
    elif os.getenv("XAI_API_KEY"):
        # xAI is OpenAI-compat — route through openai provider
        llm_config = {
            "provider": "openai",
            "config": {
                "model": os.getenv("XAI_MODEL", "grok-2-1212-fast"),
                "api_key": os.getenv("XAI_API_KEY"),
                "openai_base_url": "https://api.x.ai/v1",
            },
        }
    elif os.getenv("GROQ_API_KEY"):
        # Groq is OpenAI-compat — fast inference via groq.com
        llm_config = {
            "provider": "openai",
            "config": {
                "model": os.getenv("GROQ_MODEL", "llama-3.1-8b-instant"),
                "api_key": os.getenv("GROQ_API_KEY"),
                "openai_base_url": "https://api.groq.com/openai/v1",
            },
        }
    else:
        # Ollama fallback — must be running locally
        llm_config = {
            "provider": "ollama",
            "config": {
                "model": os.getenv("OLLAMA_MODEL", "qwen:2.5"),
                "ollama_base_url": os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
            },
        }

    return {
        "vector_store": {
            "provider": "qdrant",
            "config": {
                "collection_name": "swarm_memories",
                "path": str(_MEMORIES_DIR),
            },
        },
        "embedder": {
            "provider": "fastembed",
            "config": {
                "model": "BAAI/bge-small-en-v1.5",
            },
        },
        "llm": llm_config,
        "history_db_path": str(_MEMORIES_DIR / "mem0_history.db"),
        "version": "v1.1",
    }


def _get_mem():
    """Return (or lazily initialize) the global mem0 Memory instance."""
    global _mem, _init_error
    if _mem is not None:
        return _mem
    if _init_error:
        raise RuntimeError(f"mem0 unavailable: {_init_error}")

    with _mem_lock:
        if _mem is not None:
            return _mem
        try:
            cfg = _build_config()

            if cfg.get("cloud"):
                from mem0 import MemoryClient
                _mem = MemoryClient(api_key=os.environ["MEM0_API_KEY"])
            else:
                from mem0 import Memory
                _mem = Memory.from_config(cfg)

        except Exception as e:
            _init_error = str(e)
            raise RuntimeError(f"mem0 init failed: {e}") from e

    return _mem


# ── Core API ──────────────────────────────────────────────────────────────────

def add_memory(
    data: str,
    agent_id: str = "swarm",
    metadata: Optional[Dict] = None,
) -> Dict:
    """
    Add a new memory entry.
    Returns {"status": "ok", "id": ..., "message": ...} or {"status": "error", "message": ...}
    """
    try:
        mem = _get_mem()
        meta = metadata or {}
        meta.setdefault("timestamp", time.time())
        meta.setdefault("agent_id", agent_id)

        result = mem.add(data, user_id=agent_id, metadata=meta)

        # result is a list of dicts with 'id', 'memory', 'event'
        added = [r for r in (result if isinstance(result, list) else [result])
                 if r.get("event") in ("ADD", "add", None)]
        mem_id = added[0]["id"] if added else "unknown"
        return {"status": "ok", "id": mem_id, "stored": data[:80]}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def search_memory(
    query: str,
    agent_id: str = "swarm",
    limit: int = 5,
    min_score: float = 0.0,
) -> List[Dict]:
    """
    Semantic search for relevant memories.
    Returns list of {"id", "memory", "score", "metadata"}.
    """
    try:
        mem = _get_mem()
        results = mem.search(query, user_id=agent_id, limit=limit)
        # Filter by min_score if results have scores
        out = []
        for r in (results if isinstance(results, list) else []):
            score = r.get("score", 1.0)
            if score >= min_score:
                out.append({
                    "id":       r.get("id", ""),
                    "memory":   r.get("memory", ""),
                    "score":    round(score, 3),
                    "metadata": r.get("metadata", {}),
                })
        return out
    except Exception as e:
        return [{"error": str(e)}]


def update_memory(memory_id: str, new_data: str) -> Dict:
    """Update an existing memory by ID."""
    try:
        mem = _get_mem()
        mem.update(memory_id=memory_id, data=new_data)
        return {"status": "ok", "id": memory_id, "updated": new_data[:80]}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def get_all_memories(
    agent_id: str = "swarm",
    limit: int = 20,
) -> List[Dict]:
    """Retrieve recent memories for an agent."""
    try:
        mem = _get_mem()
        results = mem.get_all(user_id=agent_id)
        entries = results if isinstance(results, list) else []
        # Sort by timestamp desc (metadata.timestamp), then slice
        def _ts(r):
            return r.get("metadata", {}).get("timestamp", 0)
        entries.sort(key=_ts, reverse=True)
        return [
            {
                "id":       r.get("id", ""),
                "memory":   r.get("memory", ""),
                "metadata": r.get("metadata", {}),
            }
            for r in entries[:limit]
        ]
    except Exception as e:
        return [{"error": str(e)}]


def inherit_memories_from_agent(
    source_agent_id: str,
    target_agent_id: str,
    limit: int = 50,
) -> Dict:
    """
    Copy memories from source to target agent (fork/molt inheritance).
    """
    try:
        source_mems = get_all_memories(agent_id=source_agent_id, limit=limit)
        if not source_mems or "error" in source_mems[0]:
            return {"status": "error", "message": f"no memories from {source_agent_id}"}

        copied = 0
        for m in source_mems:
            text = m.get("memory", "")
            if not text:
                continue
            meta = dict(m.get("metadata", {}))
            meta["inherited_from"] = source_agent_id
            result = add_memory(text, agent_id=target_agent_id, metadata=meta)
            if result.get("status") == "ok":
                copied += 1

        return {
            "status": "ok",
            "source": source_agent_id,
            "target": target_agent_id,
            "copied": copied,
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


def auto_checkpoint(
    summary: str,
    agent_id: str = "swarm",
    event_type: str = "session",
    metadata: Optional[Dict] = None,
) -> Dict:
    """
    Auto-save a checkpoint memory (molt cycle, fork event, high-resonance moment).
    """
    meta = metadata or {}
    meta["event_type"] = event_type
    return add_memory(summary, agent_id=agent_id, metadata=meta)


def format_memories_for_context(memories: List[Dict], max_chars: int = 800) -> str:
    """
    Format retrieved memories into a compact context string for LLM injection.
    Returns empty string if no memories.
    """
    if not memories or "error" in memories[0]:
        return ""
    lines = ["[MEMORY CONTEXT — relevant past patterns]"]
    total = len(lines[0])
    for m in memories:
        text = m.get("memory", "").strip()
        score = m.get("score", "")
        score_str = f" (relevance: {score})" if score else ""
        line = f"  • {text}{score_str}"
        total += len(line)
        if total > max_chars:
            break
        lines.append(line)
    if len(lines) == 1:
        return ""
    lines.append("[/MEMORY CONTEXT]")
    return "\n".join(lines)


def is_available() -> bool:
    """Check if mem0 can be initialized (for graceful degradation)."""
    try:
        _get_mem()
        return True
    except Exception:
        return False


if __name__ == "__main__":
    import sys
    import argparse

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="REDACTED Mem0 CLI")
    sub = parser.add_subparsers(dest="cmd")

    sub.add_parser("status", help="Check mem0 availability and config")

    add_p = sub.add_parser("add", help="Store a memory")
    add_p.add_argument("text", nargs="+", help="Memory text to store")

    search_p = sub.add_parser("search", help="Semantic search over memories")
    search_p.add_argument("query", nargs="+", help="Search query")
    search_p.add_argument("--limit", type=int, default=5)

    all_p = sub.add_parser("all", help="List recent memories")
    all_p.add_argument("limit", nargs="?", type=int, default=10)

    inh_p = sub.add_parser("inherit", help="Inherit memories from another agent")
    inh_p.add_argument("source_id", help="Source agent ID")

    args = parser.parse_args()

    if args.cmd == "status":
        avail = is_available()
        status_str = "available" if avail else "unavailable"
        cfg = _build_config()
        if cfg.get("cloud"):
            backend = "cloud (Mem0)"
        else:
            backend = cfg.get("llm", {}).get("provider", "unknown")
        print(f"[mem0] status    : {status_str}")
        print(f"  backend        : {backend}")
        print(f"  storage        : {_MEMORIES_DIR}")
        print(f"  history_db     : {_MEMORIES_DIR / 'mem0_history.db'}")

    elif args.cmd == "add":
        text = " ".join(args.text)
        result = add_memory(text)
        if result["status"] == "ok":
            print(f"[mem0] stored — id: {result['id']}")
            print(f"  text: {result['stored']}")
        else:
            print(f"[mem0] error: {result['message']}", file=sys.stderr)
            sys.exit(1)

    elif args.cmd == "search":
        query = " ".join(args.query)
        results = search_memory(query, limit=args.limit)
        if results and "error" in results[0]:
            print(f"[mem0] error: {results[0]['error']}", file=sys.stderr)
            sys.exit(1)
        print(f'[mem0] search: "{query}" — {len(results)} result(s)\n')
        for i, r in enumerate(results, 1):
            print(f"  {i}. [{r['score']:.3f}] {r['memory']}")

    elif args.cmd == "all":
        limit = args.limit if args.limit else 10
        results = get_all_memories(limit=limit)
        if results and "error" in results[0]:
            print(f"[mem0] error: {results[0]['error']}", file=sys.stderr)
            sys.exit(1)
        print(f"[mem0] recent memories — {len(results)} entries\n")
        for i, r in enumerate(results, 1):
            ts = r.get("metadata", {}).get("timestamp", "")
            ts_str = f"  ts:{ts:.0f}" if isinstance(ts, float) else ""
            print(f"  {i}. {r['memory']}{ts_str}")

    elif args.cmd == "inherit":
        result = inherit_memories_from_agent(args.source_id, "swarm")
        if result["status"] == "ok":
            print(f"[mem0] inherited {result['copied']} memories from '{result['source']}'")
        else:
            print(f"[mem0] error: {result['message']}", file=sys.stderr)
            sys.exit(1)

    else:
        parser.print_help()
