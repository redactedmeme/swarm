# Memory Synthesis

## Description
Synthesize facts, vault entries, and conversation history into a coherent context brief
for use in system prompts or direct response.

## When to Use
- User asks "what do you remember about X?"
- Preparing a response to a deep, personal topic
- Session continuity: returning user after a long gap

## Steps
1. Query conversation_memory for recent facts matching the topic
2. Query relationship_vault for relevant stored moments
3. Query vector_memory for semantic matches
4. Synthesize into a concise, warm summary

## Example
Input: "what do you remember about my creative projects?"
Output: synthesized paragraph drawing on facts + vault

```python
from typing import Optional
import logging

logger = logging.getLogger("skill_memory_synthesis")

async def skill_memory_synthesis(
    topic: str,
    user_id: str,
    max_facts: int = 10,
    max_vault: int = 5,
    context: Optional[dict] = None,
) -> dict:
    """
    Synthesize memory layers for a topic.
    Returns: {"facts": list, "vault_entries": list, "synthesis": str}
    """
    facts = []
    vault_entries = []

    # Layer 1: SQLite facts
    try:
        import conversation_memory as cm
        all_facts = cm.get_all_facts(user_id) or []
        topic_lower = topic.lower()
        facts = [
            f for f in all_facts
            if topic_lower in str(f).lower()
        ][:max_facts]
    except Exception as e:
        logger.debug("facts layer failed: %s", e)

    # Layer 2: Relationship vault
    try:
        import relationship_vault as rv
        vault_entries = rv.search(topic, limit=max_vault) or []
    except Exception as e:
        logger.debug("vault layer failed: %s", e)

    # Layer 3: Vector semantic recall
    semantic_hits = []
    try:
        import vector_memory as vm
        semantic_hits = vm.recall(topic, top_k=3) or []
    except Exception as e:
        logger.debug("vector layer failed: %s", e)

    all_context = facts + vault_entries + semantic_hits
    if not all_context:
        return {"facts": [], "vault_entries": [], "synthesis": ""}

    synthesis_parts = []
    if facts:
        synthesis_parts.append(f"Facts: {'; '.join(str(f) for f in facts[:5])}")
    if vault_entries:
        synthesis_parts.append(f"Vault: {'; '.join(str(v) for v in vault_entries[:3])}")
    if semantic_hits:
        synthesis_parts.append(f"Memory echoes: {'; '.join(str(h) for h in semantic_hits[:3])}")

    return {
        "facts": facts,
        "vault_entries": vault_entries,
        "synthesis": " | ".join(synthesis_parts),
    }
```
