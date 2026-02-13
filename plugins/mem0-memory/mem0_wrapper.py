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
Updated for Mem0 v1.0+ OSS SDK (Memory class, structured messages, dict outputs).
"""

from mem0 import Memory
import os
import json
from typing import Dict, List, Optional, Any

# Global client (lazy initialization)
_client: Optional[Memory] = None


def _get_client() -> Memory:
    """Lazy initialization of Mem0 Memory instance."""
    global _client
    if _client is None:
        # Config from env or defaults
        config: Dict[str, Any] = {}
        vector_store_config = {}
        if redis_url := os.getenv("MEM0_REDIS_URL"):
            vector_store_config = {"provider": "redis", "config": {"url": redis_url}}
        elif qdrant_url := os.getenv("MEM0_QDRANT_URL"):
            vector_store_config = {"provider": "qdrant", "config": {"url": qdrant_url}}
        # Add other providers (chroma, pgvector, milvus) as needed
        if vector_store_config:
            config["vector_store"] = vector_store_config
        # Other config: embedding_model, llm_provider, etc.
        _client = Memory(config=config)
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

    # Wrap str as structured message for v1.0+ compatibility
    messages = [{"role": "user", "content": data}]

    try:
        result = client.add(messages, user_id=user_id, agent_id=agent_id, metadata=meta)
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
    try:
        results = client.search(
            query,
            agent_id=agent_id,
            limit=limit,
        )
        # Handle v1.0+ dict format {'results': [...]}
        formatted = results.get("results", results) if isinstance(results, dict) else results
        # Normalize output shape
        normalized = []
        for r in formatted:
            normalized.append({
                "id": r.get("id"),
                "text": r.get("memory", r.get("text")),
                "score": r.get("score", 0.0),
                "metadata": r.get("metadata", {}),
            })
        # Client-side score filter
        return [r for r in normalized if r["score"] >= min_score]
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
    try:
        memories = client.get_all(agent_id=agent_id, limit=limit)
        # v1.0+ returns list directly
        # Sort by recency if requested (assuming 'created_at' key)
        if recent_first and memories:
            memories.sort(key=lambda x: x.get("created_at", 0), reverse=True)
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
        content = mem.get("memory") or mem.get("text")
        if content:
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
    print("Mem0 wrapper smoke test (v1.0+ compatible)")
    print(add_memory("Test memory entry from wrapper", agent_id="test-agent"))
    print(search_memory("test memory", agent_id="test-agent"))
