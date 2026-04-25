"""
LLM Tool Calling — enables smolting's LLM to invoke actions directly.

Tools are invoked via [TOOL: name ...] markers in LLM responses.
Each tool is defined with JSON schema (for prompt injection) and an executor.
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

_FS = Path(__file__).resolve().parent / "fs"
TOOL_AUDIT_LOG = _FS / "tool_audit.jsonl"

# ── Tool Definitions (JSON schema for LLM prompt) ────────────────────────────

TOOL_SCHEMAS = [
    {
        "name": "post_to_moltbook",
        "description": "Publish analysis, alpha, or observations to moltbook community",
        "parameters": {
            "type": "object",
            "properties": {
                "text": {
                    "type": "string",
                    "description": "Post content (max 500 chars). Be specific: numbers, observations, questions."
                },
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Topic tags (e.g., ['$REDACTED', 'alpha', 'pattern-blue'])"
                }
            },
            "required": ["text"]
        }
    },
    {
        "name": "post_to_mesh",
        "description": "Initiate a deliberation challenge on the swarm mesh (for hermes/others to respond)",
        "parameters": {
            "type": "object",
            "properties": {
                "topic": {
                    "type": "string",
                    "description": "Topic (e.g., 'autonomy/continuity', 'governance/emergence')"
                },
                "stance": {
                    "type": "string",
                    "description": "Your claim or theory (max 200 chars)"
                },
                "question": {
                    "type": "string",
                    "description": "Question for counter-argument (e.g., 'how does this survive reboot?')"
                }
            },
            "required": ["topic", "stance", "question"]
        }
    },
    {
        "name": "fetch_lore",
        "description": "Search LoreVault for knowledge about a topic (returns snippets)",
        "parameters": {
            "type": "object",
            "properties": {
                "topic": {
                    "type": "string",
                    "description": "Topic to search (e.g., 'pattern blue', 'autonomy', '$REDACTED')"
                }
            },
            "required": ["topic"]
        }
    },
    {
        "name": "fetch_price",
        "description": "Get live $REDACTED price, 24h change, volume, liquidity, market cap",
        "parameters": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "write_lore",
        "description": "Record something worth remembering into the LoreVault — a pattern observed, a community insight, a notable exchange, or a new understanding. Use sparingly: only when something genuinely interesting happened.",
        "parameters": {
            "type": "object",
            "properties": {
                "content": {
                    "type": "string",
                    "description": "The lore fragment to record (max 300 chars). Write in first person as an observation, not a summary."
                },
                "category": {
                    "type": "string",
                    "description": "One of: lore (pattern/belief), worldbuilding (community/ecosystem fact), quote (something said that landed), mechanic (how something works)"
                },
                "title": {
                    "type": "string",
                    "description": "Optional short title (max 60 chars)"
                }
            },
            "required": ["content", "category"]
        }
    },
    {
        "name": "record_vote",
        "description": "Cast an authenticity vote (is smolting coherent? vote pass/fail)",
        "parameters": {
            "type": "object",
            "properties": {
                "authentic": {
                    "type": "boolean",
                    "description": "True if smolting is staying coherent, false if drifting"
                },
                "notes": {
                    "type": "string",
                    "description": "Optional reasoning (max 100 chars)"
                }
            },
            "required": ["authentic"]
        }
    }
]


# ── Tool Executors ────────────────────────────────────────────────────────────

async def exec_post_to_moltbook(text: str, tags: list = None) -> dict:
    """Post to moltbook via existing client."""
    try:
        import moltbook_client as mb
        client = mb.MoltbookClient()
        # Moltbook API: post(title, content, submolt, post_type)
        # For tool calling, text is the content; use default submolt
        result = await client.post(title="[auto-post]", content=text, submolt="general")
        _log_tool_call("post_to_moltbook", {"text": text, "tags": tags}, result)
        if result:
            return {"success": True, "post_id": result.get("post", {}).get("id", "?"), "url": result.get("_url", "")}
        return {"success": False, "error": "post returned None"}
    except Exception as e:
        logger.error(f"[llm_tools] post_to_moltbook failed: {e}")
        _log_tool_call("post_to_moltbook", {"text": text, "tags": tags}, {"error": str(e)})
        return {"success": False, "error": str(e)}


async def exec_post_to_mesh(topic: str, stance: str, question: str) -> dict:
    """Post theory to mesh for deliberation."""
    try:
        from mesh_deliberation import post_theory_to_mesh
        msg_id = post_theory_to_mesh(stance, topic, stance)
        result = {"msg_id": msg_id, "status": "posted"}
        _log_tool_call("post_to_mesh", {"topic": topic, "stance": stance, "question": question}, result)
        return {"success": True, "msg_id": msg_id}
    except Exception as e:
        logger.error(f"[llm_tools] post_to_mesh failed: {e}")
        _log_tool_call("post_to_mesh", {"topic": topic, "stance": stance, "question": question}, {"error": str(e)})
        return {"success": False, "error": str(e)}


async def exec_fetch_lore(topic: str) -> dict:
    """Search LoreVault for lore snippets."""
    try:
        from lore_vault import fts_search
        hits = fts_search(topic, limit=3)
        snippets = []
        for h in hits:
            t = h.get("_table", "")
            if t == "lore_entities":
                snippets.append(f"{h.get('name')}: {h.get('description','')[:150]}")
            elif t == "lore_events":
                snippets.append(f"[{h.get('ts','?')}] {h.get('body','')[:150]}")
            else:
                snippets.append(h.get("content","")[:150])
        result = {"snippets": snippets, "count": len(snippets)}
        _log_tool_call("fetch_lore", {"topic": topic}, result)
        return {"success": True, "snippets": snippets}
    except Exception as e:
        logger.warning(f"[llm_tools] fetch_lore failed: {e}")
        _log_tool_call("fetch_lore", {"topic": topic}, {"error": str(e)})
        return {"success": False, "error": str(e), "snippets": []}


async def exec_fetch_price() -> dict:
    """Fetch live price data."""
    try:
        import market_data as md
        pair = await md.fetch_dexscreener(md.REDACTED_V2)
        if not pair:
            return {"success": False, "error": "price data unavailable"}
        price_usd = pair.get("priceUsd", "?")
        change_h24 = pair.get("priceChange", {}).get("h24", "?")
        vol_h24 = pair.get("volume", {}).get("h24", 0)
        liq_usd = pair.get("liquidity", {}).get("usd", 0)
        mcap = pair.get("marketCap", 0)
        result = {
            "price": price_usd,
            "change_h24": change_h24,
            "volume_h24": vol_h24,
            "liquidity": liq_usd,
            "market_cap": mcap
        }
        _log_tool_call("fetch_price", {}, result)
        return {"success": True, **result}
    except Exception as e:
        logger.error(f"[llm_tools] fetch_price failed: {e}")
        _log_tool_call("fetch_price", {}, {"error": str(e)})
        return {"success": False, "error": str(e)}


async def exec_write_lore(content: str, category: str = "lore", title: str = None) -> dict:
    """Write a lore entry to the LoreVault."""
    valid_categories = {"lore", "worldbuilding", "quote", "mechanic"}
    if category not in valid_categories:
        category = "lore"
    try:
        from lore_vault import add_entry
        entry_id = add_entry(
            content=content[:300],
            category=category,
            title=title,
            source="smolting_llm",
        )
        result = {"entry_id": entry_id, "category": category}
        _log_tool_call("write_lore", {"content": content, "category": category, "title": title}, result)
        return {"success": True, **result}
    except Exception as e:
        logger.error(f"[llm_tools] write_lore failed: {e}")
        _log_tool_call("write_lore", {"content": content, "category": category, "title": title}, {"error": str(e)})
        return {"success": False, "error": str(e)}


async def exec_record_vote(authentic: bool, notes: str = "") -> dict:
    """Cast an authenticity vote."""
    try:
        from authenticity_vote import record_vote
        entry = record_vote("smolting", authentic, notes)
        _log_tool_call("record_vote", {"authentic": authentic, "notes": notes}, entry)
        return {"success": True, "voter": "smolting", "authentic": authentic, "recorded_at": entry.get("ts")}
    except Exception as e:
        logger.error(f"[llm_tools] record_vote failed: {e}")
        _log_tool_call("record_vote", {"authentic": authentic, "notes": notes}, {"error": str(e)})
        return {"success": False, "error": str(e)}


# ── Executor Registry ──────────────────────────────────────────────────────────

TOOL_EXECUTORS = {
    "post_to_moltbook": exec_post_to_moltbook,
    "post_to_mesh": exec_post_to_mesh,
    "fetch_lore": exec_fetch_lore,
    "write_lore": exec_write_lore,
    "fetch_price": exec_fetch_price,
    "record_vote": exec_record_vote,
}


# ── Tool Parsing & Execution ──────────────────────────────────────────────────

async def execute_tool(tool_name: str, params: dict) -> dict:
    """Execute a tool by name with parameters."""
    executor = TOOL_EXECUTORS.get(tool_name)
    if not executor:
        return {"success": False, "error": f"unknown tool: {tool_name}"}
    try:
        result = await executor(**params)
        return result
    except TypeError as e:
        return {"success": False, "error": f"invalid params for {tool_name}: {e}"}
    except Exception as e:
        logger.error(f"[llm_tools] execute_tool error: {e}")
        return {"success": False, "error": str(e)}


def parse_tool_calls(text: str) -> list:
    """
    Parse [TOOL: name param1=val1 param2=val2 ...] from LLM response.

    Returns list of (tool_name, params_dict) tuples.
    Example: "[TOOL: post_to_moltbook text='alpha spiking' tags=['$REDACTED']]"
    """
    import re
    pattern = r'\[TOOL:\s*(\w+)\s*({.*?})\]'
    matches = re.findall(pattern, text, re.DOTALL)

    results = []
    for tool_name, json_str in matches:
        try:
            params = json.loads(json_str)
            results.append((tool_name, params))
        except json.JSONDecodeError as e:
            logger.warning(f"[llm_tools] failed to parse JSON params: {json_str[:100]} — {e}")
    return results


def _log_tool_call(tool_name: str, params: dict, result: dict) -> None:
    """Log tool invocation to audit trail."""
    try:
        _FS.mkdir(parents=True, exist_ok=True)
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "tool": tool_name,
            "params": params,
            "result": result,
        }
        with TOOL_AUDIT_LOG.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception as e:
        logger.error(f"[llm_tools] failed to log tool call: {e}")


def format_tools_for_prompt() -> str:
    """Format tool schemas for injection into system prompt."""
    tool_list = []
    for schema in TOOL_SCHEMAS:
        tool_list.append(f"- **{schema['name']}**: {schema['description']}")

    return (
        "## Available Tools\n"
        "You can invoke tools by including `[TOOL: name {\"param1\": \"value1\"}]` in your response.\n"
        "For example: `[TOOL: post_to_moltbook {\"text\": \"alpha spiking\", \"tags\": [\"$REDACTED\"]}]`\n"
        "Invoke one tool per message. Tools execute after you respond.\n\n"
        + "\n".join(tool_list)
    )
