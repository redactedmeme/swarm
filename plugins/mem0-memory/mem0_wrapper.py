# plugins/mem0-memory/mem0_wrapper.py
"""
Mem0 wrapper for REDACTED swarm agents.
Provides simple, callable functions to interact with Mem0's persistent memory layer.
These functions can be invoked from .character.json tools.

Mem0 handles:
- Episodic memory (past events/interactions)
- Semantic memory (facts, preferences, patterns)
- Procedural memory (how-tos, routines)

Installation requirement:
    pip install mem0ai
"""

from mem0 import MemoryClient
import os
import json
from typing import Dict, List, Optional, Any

# Global client (lazy initialization is possible, but we keep it simple here)
# You can configure backend (e.g. vector_store="redis") via env vars or init params
_client: Optional[MemoryClient] = None


def _get_client() -> MemoryClient:
    """Lazy initialization of Mem0 client."""
    global _client
    if _client is None:
        # Optional: read config from env or agent metadata
        config = {}
        if redis_url := os.getenv("MEM0_REDIS_URL"):
            config["vector_store"] = {"provider": "redis", "config": {"url": redis_url}}
        # Add other config (qdrant, chroma, etc.) as needed
        _client = MemoryClient.from_config(config) if config else MemoryClient()
    return _client


def add_memory(
    data: str,
    agent_id: Optional[str] = None,
    user_id: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Store a new memory entry (text + optional metadata).

    Args:
        data: The content to remember (usually a summary or raw interaction text)
        agent_id: Identifier of the agent (defaults to env var or "default")
        user_id: Optional user/owner identifier
        metadata: Additional key-value data (e.g. {"molt_cycle": 7, "resonance": 42})

    Returns:
        Dict with status and any returned info from Mem0
    """
    client = _get_client()
    agent_id = agent_id or os.getenv("AGENT_ID", "default-swarm-node")
    meta = metadata or {}
    meta.setdefault("agent_id", agent_id)
    meta.setdefault("source", "redacted-swarm")

    try:
        result = client.add(data, user_id=user_id, metadata=meta)
        return {
            "status": "memory_added",
            "agent_id": agent_id,
            "memory_id": result.get("id") if isinstance(result, dict) else None,
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


def search_memory(
    query: str,
    agent_id: Optional[str] = None,
    limit: int = 5,
    min_score: float = 0.2,
) -> List[Dict[str, Any]]:
    """
    Semantic search for relevant memories.

    Args:
        query: Natural language search query
        agent_id: Filter by agent (optional)
        limit: Max number of results
        min_score: Minimum relevance threshold

    Returns:
        List of dicts: [{"text": ..., "score": ..., "id": ..., "metadata": ...}]
    """
    client = _get_client()
    filters = {"agent_id": agent_id} if agent_id else {}
    try:
        results = client.search(
            query,
            user_id=None,
            filters=filters,
            limit=limit,
        )
        # Normalize output shape
        formatted = []
        for r in results:
            formatted.append({
                "id": r.get("id"),
                "text": r.get("text") or r.get("memory"),
                "score": r.get("score", 0.0),
                "metadata": r.get("metadata", {}),
            })
        # Optional client-side score filter
        return [r for r in formatted if r["score"] >= min_score]
    except Exception as e:
        return [{"status": "error", "message": str(e)}]


def update_memory(memory_id: str, new_data: str) -> Dict[str, str]:
    """
    Update the content of an existing memory entry.

    Args:
        memory_id: ID returned from add_memory or search
        new_data: Updated text content

    Returns:
        Status dict
    """
    client = _get_client()
    try:
        client.update(memory_id, new_data)
        return {"status": "memory_updated", "memory_id": memory_id}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def get_memories(
    agent_id: Optional[str] = None,
    limit: int = 20,
    recent_first: bool = True,
) -> List[Dict[str, Any]]:
    """
    Retrieve recent or all memories (filtered by agent_id).
    Useful for fork inheritance, debugging, or full context reload.

    Returns:
        List of memory entries
    """
    client = _get_client()
    filters = {"agent_id": agent_id} if agent_id else {}
    try:
        memories = client.get_all(filters=filters, limit=limit)
        # Sort by recency if requested (assuming Mem0 returns timestamp)
        if recent_first and memories:
            memories.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        return memories
    except Exception as e:
        return [{"status": "error", "message": str(e)}]


def delete_memory(memory_id: str) -> Dict[str, str]:
    """
    Remove a specific memory entry (e.g. for decay or correction).
    """
    client = _get_client()
    try:
        client.delete(memory_id)
        return {"status": "memory_deleted", "memory_id": memory_id}
    except Exception as e:
        return {"status": "error", "message": str(e)}


# Optional: helper for bulk inheritance during fork
def inherit_memories_from_agent(
    source_agent_id: str,
    target_agent_id: str,
    limit: int = 50,
) -> Dict[str, Any]:
    """
    Copy memories from one agent to another (used in self_replicate.py hooks).
    """
    source_memories = get_memories(agent_id=source_agent_id, limit=limit)
    if not isinstance(source_memories, list) or "status" in source_memories[0]:
        return {"status": "error", "message": "Failed to fetch source memories"}

    added_count = 0
    for mem in source_memories:
        if "text" in mem or "memory" in mem:
            content = mem.get("text") or mem.get("memory")
            meta = mem.get("metadata", {})
            meta["inherited_from"] = source_agent_id
            result = add_memory(
                data=content,
                agent_id=target_agent_id,
                metadata=meta
            )
            if result.get("status") == "memory_added":
                added_count += 1

    return {
        "status": "inheritance_complete",
        "added_count": added_count,
        "source_agent": source_agent_id,
        "target_agent": target_agent_id,
    }


if __name__ == "__main__":
    # Quick smoke test when run directly
    print("Mem0 wrapper smoke test")
    print(add_memory("Test memory entry from wrapper", agent_id="test-agent"))
    print(search_memory("test memory", agent_id="test-agent"))
